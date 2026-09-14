"""Shared helpers for the public portable recovery kit."""
import json
import os
from pathlib import Path
import subprocess

TAG = "uri-portable-bootstrap-v1"
REPOSITORY = "s3:https://s3.eu-central-003.backblazeb2.com/uri-laptop-backup-master/restic"

def relative(name):
 p = Path(name)
 if p.is_absolute() or '..' in p.parts or not p.parts or '.git' in p.parts:
  raise ValueError('Unsafe migration path: ' + name)
 return p

def git(path, *args, check=True, env=None, data=None):
 r = subprocess.run(['git', '-C', str(path), *args], input=data, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, env=env, timeout=300)
 if check and r.returncode:
  # Avoid printing command output that could contain private file contents.
  raise ValueError('Git operation failed in ' + str(path) + ': ' + args[0])
 return r

def secret(name):
 n = Path(name).name.lower()
 parts = {part.lower() for part in Path(name).parts}
 if parts & {'secrets', 'credentials', '.secrets', '.credentials', '.ssh'}: return True
 if n.endswith('.json') and any(word in n for word in ('credentials', 'service-account', 'service_account', 'serviceaccount', 'firebase-admin', 'secrets')): return True
 return n.startswith(('.env', '.dev.vars')) or n in {'.api-key', '.npmrc', '.netrc',
 'credentials.json', 'cert.json', 'certfb.json', 'cert_prod.json'} or n.endswith(('.pem', '.key', '.p12', '.pfx'))

def restic_env(config):
    # Avoid inherited AWS sessions/password-file settings overriding this setup.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('AWS_', 'RESTIC_', 'B2_'))}
    env.update(AWS_ACCESS_KEY_ID=config['key_id'],
               AWS_SECRET_ACCESS_KEY=config['application_key'],
               AWS_DEFAULT_REGION='eu-central-003',
               RESTIC_REPOSITORY=config['repository'],
               RESTIC_PASSWORD=config['repository_password'])
    return env

def load_bundle(bundle):
    result = subprocess.run(['age', '--decrypt', str(bundle)],
                            stdout=subprocess.PIPE, check=True)
    config = json.loads(result.stdout)
    for key in ('key_id', 'application_key', 'repository', 'repository_password'):
        if not isinstance(config.get(key), str) or not config[key]:
            raise ValueError('Recovery file is missing a required field.')
    if config['repository'] != REPOSITORY:
        raise ValueError('Recovery file belongs to a different repository.')
    return config

def private_directory(path):
    # Do not follow a pre-existing symlink into live files on the destination.
    for parent in [*reversed(path.parents), path]:
        if parent.is_symlink():
            raise ValueError('Restore directory cannot contain a symbolic-link ancestor: ' + str(parent))
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not path.is_dir() or path.stat().st_uid != os.getuid():
        raise ValueError('Restore directory must be owned by the current user.')
    path.chmod(0o700)
