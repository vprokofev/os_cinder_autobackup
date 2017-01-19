#!/usr/bin/python
from datetime import *

## define 'print with timestamp' function
def printwts(text):
    print (datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f") + " " + text)

## loading necessary libraries
printwts("Starting backup script. Loading libararies...")
import os
import time
import ConfigParser
from keystoneauth1.identity import v3
from keystoneauth1 import loading
from keystoneauth1 import session
from keystoneclient.v3 import client as keystoneclient
from cinderclient import client as cinderclient
printwts("Loaded.")

config = ConfigParser.ConfigParser()
config.read('/usr/local/etc/autobackup.conf')
_auth_url = config.get("authcred", "auth_url")
_username = config.get("authcred", "username")
_password = config.get("authcred", "password")
_project_name = config.get("authcred", "project_name")
_project_domain_name = config.get("authcred", "project_domain_name")
_user_domain_name = config.get("authcred", "user_domain_name")

## creating list of projects to backup
auth = v3.Password(auth_url=_auth_url,
                   username=_username,
                   password=_password,
                   project_name=_project_name,
                   project_domain_name=_project_domain_name,
                   user_domain_name=_user_domain_name)
sess = session.Session(auth=auth)
keystone = keystoneclient.Client(session=sess)

userlist = keystone.users.list()
for user in userlist:
    if user.name == _username:
        jobuserid = user.id

projectsuserin = keystone.role_assignments.list(user=jobuserid)
projects_to_backup = []
for projects in projectsuserin:
    projects_to_backup.append(projects.scope['project']['id'])

## creating backups for each project
loader = loading.get_plugin_loader('password')
for project in projects_to_backup:
    auth = loader.load_from_options(auth_url=_auth_url,
                                    username=_username,
                                    password=_password,
                                    project_id=project,
                                    project_domain_name=_project_domain_name,
                                    user_domain_name=_user_domain_name)

    sess = session.Session(auth=auth)
    cinder = cinderclient.Client('2', session=sess)

    printwts("Creating list of volumes to backup for project %s" % (project))
    volumes_to_backup = []
    list1 = cinder.volumes.list(search_opts = {'project_id': project})
    for volume in list1:
        volumes_to_backup.append(volume.id)

    for volume in volumes_to_backup:
        printwts("Creating backup for volume %s" % volume)
        backup_req = cinder.backups.create(volume_id = volume, name='autobackup_' + datetime.now().strftime("%Y%m%d%H%M%S"), description='Automated backup of volume UUID %s, created at %s' % (volume, datetime.now().strftime("%Y-%m-%d %H:%M:%S")), force=True)
        time.sleep(5)
        backup = cinder.backups.get(backup_req.id)
        while backup.status == 'creating':
            printwts("Waiting for backup to create: " + backup.status)
            time.sleep(5)
            backup = cinder.backups.get(backup_req.id)
        else:
            if backup.status == 'available':
                printwts("Backup for volume %s created successfully" % (volume))
                availablebackups = cinder.backups.list(search_opts = {'volume_id': volume})
                printwts('Checking for backups older than 7 days')
                for availablebackup in availablebackups:
                    created_timestamp = datetime.strptime(availablebackup.created_at, '%Y-%m-%dT%H:%M:%S.%f')
                    if (datetime.now() - created_timestamp).days > 7:
                        printwts('Backup %s is older than 7 days, deleting' % (availablebackup))
                        cinder.backups.delete(availablebackup)
                printwts('Check complete')
            elif backup.status == 'error':
                printwts("Error creating backup for volume %s" % (volume))
            else:
                printwts("Unknown error creating backup for volume %s" % (volume))

printwts("Job completed.")