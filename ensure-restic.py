#!/usr/bin/env python3
"""Use an official restic binary when the distribution package is too old."""
import bz2
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tempfile
import urllib.request


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'uri-laptop-restore'})
    with urllib.request.urlopen(req, timeout=120) as response:
        return response.read()


def compatible():
    result = subprocess.run(['restic', 'restore', '--help'], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    return result.returncode == 0 and all(flag in result.stdout for flag in ('--verify', '--overwrite', '--exclude-xattr'))


def main():
    if compatible():
        return
    arch = {'x86_64': 'amd64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(platform.machine())
    if platform.system() != 'Linux' or not arch:
        raise ValueError('Automatic restic upgrade supports x64 and ARM64 Linux.')
    print('The distribution restic is too old. Installing an official release into ~/.local/bin.')
    release = json.loads(fetch('https://api.github.com/repos/restic/restic/releases/latest'))
    version = release['tag_name'].removeprefix('v')
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Unexpected restic release version.')
    name = 'restic_' + version + '_linux_' + arch + '.bz2'
    assets = {item['name']: item['browser_download_url'] for item in release['assets']}
    for key in (name, 'SHA256SUMS'):
        if not assets[key].startswith('https://github.com/restic/restic/releases/download/'):
            raise ValueError('Unexpected release asset URL.')
    sums = fetch(assets['SHA256SUMS']).decode()
    expected = None
    for line in sums.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip('*') == name:
            expected = parts[0]
    content = fetch(assets[name])
    if expected is None or hashlib.sha256(content).hexdigest() != expected:
        raise ValueError('Restic download checksum mismatch.')
    directory = Path.home() / '.local' / 'bin'
    directory.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.restic-', dir=directory)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(bz2.decompress(content))
        os.chmod(temporary, 0o755)
        subprocess.run([temporary, 'version'], check=True)
        os.replace(temporary, directory / 'restic')
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    if not compatible():
        raise ValueError('Updated restic is not available in PATH.')


if __name__ == '__main__':
    main()
