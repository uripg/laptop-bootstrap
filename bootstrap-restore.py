#!/usr/bin/env python3
"""Restore a portable setup into a home directory, preserving overwritten files."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
from bootstrap_common import TAG, relative, git, secret, load_bundle, restic_env, private_directory
from terminal_ui import banner, stage, done


def checked_path(base, name):
 p = base / relative(name)
 for parent in p.parents:
  if parent == base: break
  if parent.is_symlink(): raise ValueError('Linked parent directory requires manual review: ' + str(parent))
 if not p.parent.resolve().is_relative_to(base.resolve()): raise ValueError('Path escapes the restore destination')
 return p


def write_state(path, record):
 temp = path.with_suffix('.tmp'); temp.write_text(json.dumps(record, indent=2) + '\n'); os.replace(temp, path)


def preserve(path, target, previous):
 if path.exists() or path.is_symlink():
  dest = previous / path.relative_to(target)
  dest.parent.mkdir(parents=True, exist_ok=True)
  if dest.exists() or dest.is_symlink(): dest = dest.with_name(dest.name + '.' + uuid.uuid4().hex)
  shutil.move(str(path), str(dest))


def reusable_clone(dest, project, target, state_dir):
 marker = dest / '.git/uri-portable-restore.json'
 if not marker.is_file() or dest.is_symlink(): return False
 try:
  owned = json.loads(marker.read_text())
  sid = owned.get('snapshot', '')
  if owned.get('path') != project['path'] or not re.fullmatch(r'[0-9a-f]{64}', sid): return False
  prior = json.loads((state_dir.parent / sid / 'progress.json').read_text())
  if prior.get('complete') or prior.get('target') != str(target): return False
  if git(dest, 'rev-parse', 'HEAD').stdout.decode().strip() != project['commit']: return False
  if git(dest, 'remote', 'get-url', 'origin').stdout.decode().strip() != 'https://github.com/' + project['repository'] + '.git': return False
  return not git(dest, 'status', '--porcelain', '--untracked-files=all').stdout.strip()
 except (ValueError, OSError): return False


def apply_manifest(payload, target, state_dir, snapshot):
 manifest = json.loads((payload / 'manifest.json').read_text())
 if manifest.get('version') != 1: raise ValueError('Unsupported portable manifest version')
 record_file = state_dir / 'progress.json'; previous = state_dir / 'previous-files'
 projects = sorted(manifest['projects'], key=lambda p: len(Path(p['path']).parts))
 if record_file.exists():
  record = json.loads(record_file.read_text())
  if record.get('snapshot') != snapshot or record.get('target') != str(target): raise ValueError('Restore state belongs to another destination')
  if record.get('complete'): print('This setup snapshot was already restored.'); return
 else:
  # Inspect all destinations before claiming or writing any project directory.
  for project in projects:
   dest = checked_path(target, project['path'])
   if (dest.exists() or dest.is_symlink()) and not reusable_clone(dest, project, target, state_dir): raise ValueError('Project already exists; use a fresh --home destination: ' + str(dest))
  record = {'snapshot': snapshot, 'target': str(target), 'cloned': [], 'complete': False}
  write_state(record_file, record)
 for name in manifest['files']:
  checked_path(target, name)
 helper = state_dir / 'github-credential.py'
 helper.write_text('''import os, sys
from pathlib import Path
fields = dict(line.rstrip('\\n').split('=', 1) for line in sys.stdin if '=' in line)
if sys.argv[-1] == 'get' and fields.get('protocol') == 'https' and fields.get('host') == 'github.com':
    print('username=x-access-token')
    print('password=' + Path(os.environ['PORTABLE_TOKEN_PATH']).read_text().strip())
''')
 env = dict(os.environ, PORTABLE_TOKEN_PATH=str(payload / 'github-token'), GIT_TERMINAL_PROMPT='0')
 credential = '!' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(helper))
 def run(path, *args, check=True):
  result = git(path, '-c', 'credential.helper=', '-c', 'credential.helper=' + credential, *args, env=env, check=False)
  if check and result.returncode:
   # Report the operation, never raw stderr or credential-bearing arguments.
   detail = ''
   if args[0] == 'fetch' and len(args) > 2 and args[1] == 'origin':
    detail = ' Saved commit is unavailable on GitHub. Create a fresh portable backup on the Mac with the updated scripts.'
   raise ValueError('Git ' + args[0] + ' failed for ' + name + ' (exit ' + str(result.returncode) + ').' + detail)
  return result
 for index, project in enumerate(projects, 1):
  name = project['path']; dest = checked_path(target, name)
  repo = project['repository']; commit = project['commit']; branch = project['branch']
  if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo) or not re.fullmatch(r'[0-9a-f]{40,64}', commit): raise ValueError('Invalid project manifest')
  if branch and git(target, 'check-ref-format', '--branch', branch, check=False).returncode: raise ValueError('Invalid saved branch')
  stage(index, len(projects), 'Restore ' + name)
  marker = dest / '.git/uri-portable-restore.json'
  if name not in record['cloned'] and marker.is_file():
   owned = json.loads(marker.read_text())
   if owned == {'snapshot': snapshot, 'path': name} or reusable_clone(dest, project, target, state_dir):
    record['cloned'].append(name); write_state(record_file, record)
  if name in record['cloned']:
   current = run(dest, 'rev-parse', 'HEAD').stdout.decode().strip()
   if current != commit: raise ValueError('Project changed since partial restore; refusing to reset it: ' + name)
   done('Clone already restored'); continue
  if dest.exists() or dest.is_symlink(): raise ValueError('Unexpected project folder; preserve it and choose another --home: ' + name)
  dest.parent.mkdir(parents=True, exist_ok=True)
  with tempfile.TemporaryDirectory(prefix='.uri-clone-', dir=dest.parent) as temp:
   clone = Path(temp) / 'checkout'
   run(dest.parent, 'clone', '--no-checkout', 'https://github.com/' + repo + '.git', str(clone))
   for bundle in sorted((payload / 'git-bundles').glob(project['group'] + '*.bundle')):
    # Avoid group "1" also matching group "10".
    if bundle.name != project['group'] + '.bundle' and not bundle.name.startswith(project['group'] + '-detached-'): continue
    if '-detached-' in bundle.name: run(clone, 'fetch', str(bundle), 'HEAD')
    else: run(clone, 'fetch', str(bundle), '+refs/heads/*:refs/remotes/mac-backup/*', '+refs/tags/*:refs/tags/*')
   for ref in run(clone, 'for-each-ref', '--format=%(refname) %(objectname)', 'refs/remotes/mac-backup/').stdout.decode().splitlines():
    saved_ref, saved_oid = ref.split()
    run(clone, 'update-ref', 'refs/heads/' + saved_ref.removeprefix('refs/remotes/mac-backup/'), saved_oid)
   if run(clone, 'cat-file', '-e', commit + '^{commit}', check=False).returncode:
    run(clone, 'fetch', 'origin', commit)
   run(clone, 'checkout', *(['-B', branch, commit] if branch else ['--detach', commit]))
   if branch and run(clone, 'show-ref', '--verify', '--quiet', 'refs/remotes/origin/' + branch, check=False).returncode == 0:
    run(clone, 'branch', '--set-upstream-to=origin/' + branch, branch)
   (clone / '.git/uri-portable-restore.json').write_text(json.dumps({'snapshot': snapshot, 'path': name}))
   os.rename(clone, dest)
  record['cloned'].append(name); write_state(record_file, record); done('Branch and saved commit restored')
 print('\nRestoring local changes, secrets and settings…', flush=True)
 previous.mkdir(mode=0o700, exist_ok=True)
 reference_prefixes = ('Library/',)
 reference_files = {'secrets-archive.zip', 'system-config-archive.tar.gz.enc', '.gitconfig', '.zshrc', '.zprofile', '.zshenv', '.bashrc', '.bash_profile', '.profile', '.p10k.zsh'}
 for name in manifest['files']:
  src = checked_path(payload / 'home', name)
  # Mac Keychain and Mac app preference files remain available as references.
  # Portable app preferences can be imported after installing the Linux app.
  dest = checked_path(state_dir / 'mac-settings-reference', name) if (name.startswith(reference_prefixes) or name in reference_files) else checked_path(target, name)
  base = state_dir / 'mac-settings-reference' if (name.startswith(reference_prefixes) or name in reference_files) else target
  if not src.exists() and not src.is_symlink(): raise ValueError('Overlay file missing: ' + name)
  dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
  if dest.is_file() and not dest.is_symlink() and src.is_file() and not src.is_symlink() and dest.read_bytes() == src.read_bytes(): continue
  if base == target: preserve(dest, target, previous)
  elif dest.exists() or dest.is_symlink(): dest.unlink()
  if src.is_symlink(): dest.symlink_to(os.readlink(src))
  else:
   shutil.copy2(src, dest)
   if secret(name) or not any(name.startswith(p['path'] + '/') for p in projects): dest.chmod(0o600)
 for project in projects:
  for name in project['deletions']:
   p = checked_path(target, name)
   if p.exists() or p.is_symlink(): preserve(p, target, previous)
 # Linux OpenSSH does not recognize Apple's UseKeychain setting. Preserve original.
 ssh = target / '.ssh/config'
 if ssh.is_file() and not ssh.is_symlink():
  text = ssh.read_text(); adapted = re.sub(r'(?im)^(\s*)(UseKeychain\s+.*)$', r'\1# Mac-only: \2', text)
  adapted = adapted.replace(manifest['source_home'] + '/', str(target) + '/')
  if adapted != text: preserve(ssh, target, previous); ssh.write_text(adapted); ssh.chmod(0o600)
 # All SSH directories must remain private, not only their key files.
 if (target / '.ssh').is_dir() and not (target / '.ssh').is_symlink():
  for root, dirs, files in os.walk(target / '.ssh', followlinks=False): Path(root).chmod(0o700)
 # Import portable Git identity; keep Mac-specific helpers/signing commands as references.
 original_gitconfig = state_dir / 'mac-settings-reference/.gitconfig'
 if original_gitconfig.is_file():
  for key in ('user.name', 'user.email'):
   value = git(target, 'config', '-f', str(original_gitconfig), '--get', key, check=False)
   if value.returncode == 0: git(target, 'config', '--global', key, value.stdout.decode().strip(), env=dict(os.environ, HOME=str(target), XDG_CONFIG_HOME=str(target / '.config')))
 if shutil.which('gh'):
  auth = subprocess.run(['gh', 'auth', 'login', '--hostname', 'github.com', '--git-protocol', 'https', '--with-token'], input=(payload / 'github-token').read_bytes(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=dict(os.environ, HOME=str(target), XDG_CONFIG_HOME=str(target / '.config')))
  if auth.returncode: raise ValueError('GitHub login could not be saved. State is restored; rerun to retry authentication.')
  subprocess.run(['gh', 'auth', 'setup-git', '--hostname', 'github.com'], check=True, stdout=subprocess.DEVNULL, env=dict(os.environ, HOME=str(target), XDG_CONFIG_HOME=str(target / '.config')))
 record['complete'] = True; write_state(record_file, record)
 (payload / 'github-token').unlink(missing_ok=True)
 print('\nPORTABLE RESTORE COMPLETE.', flush=True)
 print('Projects, saved branches, local edits, keys and selected settings restored to: ' + str(target))
 print('Any replaced files were preserved in: ' + str(previous))
 print('Mac-specific settings and Keychain references: ' + str(state_dir / 'mac-settings-reference'))
 print('Documents, photos, local databases and large untracked data remain in the separate full backup.')


def main():
 parser = argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--recovery', type=Path, default=Path(__file__).with_name('recovery.age'))
 parser.add_argument('--home', type=Path, default=Path.home())
 parser.add_argument('--snapshot')
 args = parser.parse_args(); os.umask(0o077)
 if os.geteuid() == 0 or not sys.stdin.isatty(): raise ValueError('Run in Terminal as your normal user.')
 banner('Restore your portable setup')
 config = load_bundle(args.recovery); env = restic_env(config)
 snapshots = json.loads(subprocess.check_output(['restic', 'snapshots', '--json', '--tag', TAG], env=env))
 if args.snapshot: snapshots = [s for s in snapshots if s['id'].startswith(args.snapshot)]
 if not snapshots: raise ValueError('No portable snapshot exists yet. Run bootstrap-backup.command on the Mac first.')
 if args.snapshot and len(snapshots) != 1: raise ValueError('Snapshot ID is ambiguous')
 selected = max(snapshots, key=lambda s: datetime.fromisoformat(s['time'].replace('Z', '+00:00')))
 sid = selected['id']
 if not re.fullmatch(r'[0-9a-f]{64}', sid): raise ValueError('Invalid snapshot ID')
 target = args.home.expanduser().absolute(); target.mkdir(parents=True, exist_ok=True)
 private_directory(target / '.local/state/uri-portable')
 state = target / '.local/state/uri-portable' / sid; private_directory(state)
 progress = state / 'progress.json'
 if progress.exists() and json.loads(progress.read_text()).get('complete'):
  print('This portable setup is already restored.'); return 0
 payload = state / 'payload'; private_directory(payload)
 stage(1, 2, 'Download and verify the encrypted setup bundle')
 subprocess.run(['restic', 'restore', sid, '--target', str(payload), '--verify', '--overwrite', 'always', '--exclude-xattr', '*'], env=env, check=True)
 stage(2, 2, 'Clone projects and apply saved state')
 apply_manifest(payload, target, state, sid)
 return 0

if __name__ == '__main__':
 try: sys.exit(main())
 except (ValueError, OSError, subprocess.CalledProcessError, KeyboardInterrupt) as e:
  print('\nPortable restore stopped: ' + str(e), file=sys.stderr)
  print('Completed clones and progress were retained. Rerun with the same snapshot to resume.', file=sys.stderr)
  sys.exit(1)
