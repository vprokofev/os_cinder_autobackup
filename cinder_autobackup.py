#!/usr/bin/python

import logging
import argparse
import ConfigParser
from time import sleep
from datetime import datetime
from keystoneauth1.identity import v3
from keystoneauth1 import loading
from keystoneauth1 import session
from keystoneclient.v3 import client as keystoneclient
from cinderclient import client as cinderclient

parser = argparse.ArgumentParser()
parser.add_argument('--config_file', type = str,
		    default = '/usr/local/etc/autobackup.conf',
                    help = 'path to configuration file')
parser.add_argument('--log_file', type = str,
		    default = '/var/log/autobackup.log',
		    help = 'path to log file')
args = parser.parse_args()

logging.basicConfig(level = logging.INFO, format = u'[%(asctime)s]  %(message)s', filename = args.log_file)

logging.debug(u'Loaded libraries.')

config = ConfigParser.ConfigParser()
config.read(args.config_file)
ksargs = {}
ksargs['auth_url'] = config.get("authcred", "auth_url")
ksargs['username'] = config.get("authcred", "username")
ksargs['password'] = config.get("authcred", "password")
ksargs['project_name'] = config.get("authcred", "project_name")
ksargs['project_domain_name'] = config.get("authcred", "project_domain_name")
ksargs['user_domain_name'] = config.get("authcred", "user_domain_name")

## creating list of projects to backup
auth = v3.Password(**ksargs)
sess = session.Session(auth = auth)
keystone = keystoneclient.Client(session = sess)

userlist = keystone.users.list()
for user in userlist:
    if user.name == ksargs['username']:
        jobuserid = user.id

projectsuserin = keystone.role_assignments.list(user=jobuserid)
projects_to_backup = []
for projects in projectsuserin:
    projects_to_backup.append(projects.scope['project']['id'])

## creating backups for each project
loader = loading.get_plugin_loader('password')
ksargs.pop('project_name', None)
for project in projects_to_backup:
    ksargs['project_id'] = project
    auth = loader.load_from_options(**ksargs)
    sess = session.Session(auth=auth)
    cinder = cinderclient.Client('2', session=sess)

    logging.info(u'Creating list of volumes to backup for project %s' % (project))
    volumes_to_backup = []
    list1 = cinder.volumes.list(search_opts = {'project_id': project})
    for volume in list1:
        volumes_to_backup.append(volume.id)

    for volume in volumes_to_backup:
        logging.info(u'Creating backup for volume %s' % volume)
        backup_req = cinder.backups.create(volume_id = volume,
					   name='autobackup_' + datetime.now().strftime("%Y%m%d%H%M%S"),
					   description='Automated backup of volume UUID %s, created at %s' % (volume, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
					   force=True)
        sleep(5)
        backup = cinder.backups.get(backup_req.id)
        while backup.status == 'creating':
            logging.info(u'Waiting for backup to create: ' + backup.status)
            sleep(5)
            backup = cinder.backups.get(backup_req.id)
        else:
            if backup.status == 'available':
                logging.info(u'Backup for volume %s created successfully' % (volume))
                availablebackups = cinder.backups.list(search_opts = {'volume_id': volume})
                logging.info(u'Checking for backups older than 7 days')
                for availablebackup in availablebackups:
                    created_timestamp = datetime.strptime(availablebackup.created_at, '%Y-%m-%dT%H:%M:%S.%f')
                    if (datetime.now() - created_timestamp).days > 7:
                        logging.info(u'Backup %s is %s days old, which is greater than 7 days, deleting' % (availablebackup, (datetime.now() - created_timestamp).days))
                        cinder.backups.delete(availablebackup)
		    else:
			logging.info(u'Backup %s is %s days old, which is less than 7 days, not deleting' % (availablebackup, (datetime.now() - created_timestamp).days))
                logging.info(u'Check complete.')
            elif backup.status == 'error':
                logging.critical(u'Error creating backup for volume %s' % (volume))
            else:
                logging.critical(u'Unknown error creating backup for volume %s' % (volume))

logging.info(u'Job complete.')
