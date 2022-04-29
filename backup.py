#!/usr/bin/env python3

import argparse
from email.message import EmailMessage
import logging
import smtplib
import sys
from time import sleep
import openstack
import yaml


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", metavar="PATH",
                        default="config.yaml",
                        help="config file")
    parser.add_argument("-l", "--log_file", metavar="PATH",
                        help="log file")
    parser.add_argument("-L", "--log_level",
                        help="log level")
    parser.add_argument("-p", "--poll", metavar="SECONDS",
                        default=1, type=int,
                        help="poll interval in seconds")
    args = parser.parse_args()
    return args


def create_logger(log_level=None, log_file=None):
    formatter = logging.Formatter(u"[%(asctime)s] - %(filename)s - "
                                  "%(levelname)s - %(message)s")
    if log_level is None:
        log_level = "INFO"
    level = getattr(logging, log_level.upper(), None)
    logger = logging.getLogger(__name__)
    logger.setLevel(level)
    live = logging.StreamHandler(sys.stdout)
    live.setLevel(level)
    live.setFormatter(formatter)
    logger.addHandler(live)
    if log_file:
        fileh = logging.FileHandler(log_file)
        fileh.setLevel(level)
        fileh.setFormatter(formatter)
        logger.addHandler(fileh)
    return logger


def create_connection():
    conn = openstack.connect()
    return conn


def create_backup(conn, log, volume_id, poll):
    log.info(f"backing up volume {volume_id}")
    try:
        backup = conn.volume.create_backup(volume_id=volume_id, force=True,
                                           name="backup",
                                           description="backup")
    except Exception as e:
        log.warning(f"{e}")
        return False
    backup = conn.volume.get_backup(backup)
    while backup.status == "creating":
        log.debug(f"{backup.id}: {backup.status}")
        sleep(poll)
        backup = conn.volume.get_backup(backup)
    if backup.status != "available":
        log.warning(f"{backup.id}: {backup.status} -- check cinder logs")
        return False
    log.info(f"volume {volume_id} backup complete")
    return backup


def prep_delete(conn, log, volume_id, depth):
    dlist = []
    # sort backups by creation time in descending order(new first, oldest last)
    # this is the default but we explicitly set it here just in case
    backups_gen = conn.volume.backups(volume_id=volume_id,
                                      sort_key="created_at",
                                      sort_dir="desc",
                                      all_tenants=True)
    i = 0
    for backup in backups_gen:
        if i >= depth:
            dlist.append(backup.id)
        i += 1
    log.debug(f"backups to remove for volume {volume_id}: {dlist}")
    return dlist


def delete_backups(conn, log, dlist):
    for backup_id in dlist:
        log.info(f"removing backup {backup_id}")
        conn.volume.delete_backup(backup_id)


def report(rcfg, log, created, deleted, failed):
    mdata = (f"backups created: {created}\n"
             f"backups deleted: {deleted}\n")
    if failed != 0:
        mdata += f"backups failed: {failed}"
    msg = EmailMessage()
    msg["From"] = rcfg["mail_from"]
    msg["To"] = rcfg["mail_to"]
    msg["Subject"] = "backup report"
    msg.set_content(mdata)
    s = smtplib.SMTP(rcfg["smtp_server"])
    try:
        s.send_message(msg)
    except Exception as e:
        log.warning(f"{e}")

def main():
    args = parse_args()
    conn = create_connection()
    log = create_logger(args.log_level, args.log_file)
    dlist = []
    created = 0
    failed = 0
    with open(args.config, "r") as config:
        cfg = yaml.load(config, Loader=yaml.FullLoader)
        plan = cfg["plan"]
        for volume in plan:
            backup = create_backup(conn, log, volume["id"], args.poll)
            if backup:
                created += 1
                plist = prep_delete(conn, log, volume["id"], volume["depth"])
                dlist.extend(plist)
            else:
                failed += 1
        delete_backups(conn, log, dlist)
        deleted = len(dlist)
        try:
            rcfg = cfg["report"]
            report(rcfg, log, created, deleted, failed)
        except KeyError:
            log.warning("no report section in configuration, skipping")


if __name__ == "__main__":
    main()
