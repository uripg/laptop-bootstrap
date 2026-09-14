"""Development and communication tools approved for Uri's Linux laptop."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile


class DeveloperTools:
    def download(self, url, destination):
        self.run('curl', '--proto', '=https', '--proto-redir', '=https', '-fsSL', '--retry', '3', url, '-o', destination)

    def apt_source(self, name, key_url, line, dearmor=False):
        with tempfile.TemporaryDirectory(prefix='uri-repository-') as tmp:
            key = Path(tmp) / 'key.asc'
            self.download(key_url, key)
            if dearmor:
                binary = Path(tmp) / 'key.gpg'
                self.run('gpg', '--batch', '--yes', '--dearmor', '--output', binary, key)
                key = binary
            suffix = 'gpg' if dearmor else 'asc'
            self.run('sudo', 'install', '-d', '-m', '755', '/etc/apt/keyrings')
            self.run('sudo', 'install', '-m', '644', key, '/etc/apt/keyrings/' + name + '.' + suffix)
            self.run('sudo', 'tee', '/etc/apt/sources.list.d/' + name + '.list',
                     input=line + '\n', text=True, stdout=subprocess.DEVNULL)
        self.run('sudo', 'apt-get', 'update')

    def node(self):
        # A separate native Linux installation, independent of the excluded Hermes runtime.
        nvm = self.home / '.nvm' / 'nvm.sh'
        if not nvm.is_file():
            self.vendor_script('https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.7/install.sh', shell='bash')
        self.run('bash', '-c', 'set -e; export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh"; nvm install 24; nvm alias default 24')
        result = self.run('bash', '-c', 'export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh"; nvm which 24',
                          stdout=subprocess.PIPE, text=True)
        binary = Path(result.stdout.strip())
        if not binary.is_file() or binary.name != 'node':
            raise ValueError('Could not locate the installed Linux Node.js binary.')
        os.environ['PATH'] = str(binary.parent) + ':' + os.environ['PATH']
        self.run('node', '--version')
        self.run('npm', '--version')

    def npm_tools(self):
        if not shutil.which('npm'):
            raise ValueError('Node/npm must be installed before pnpm, Wrangler and Clerk.')
        self.run('npm', 'install', '--global', '--prefix', self.home / '.local', 'pnpm@10', 'wrangler', 'clerk')
        for name in ('pnpm', 'wrangler', 'clerk'):
            self.run(self.home / '.local' / 'bin' / name, '--version')

    def bun(self):
        if not shutil.which('bun'):
            self.vendor_script('https://bun.sh/install', shell='bash')
        self.run('bun', '--version')

    def deno(self):
        if not shutil.which('deno'):
            self.vendor_script('https://deno.land/install.sh')
        self.run('deno', '--version')

    def python_tools(self):
        if not shutil.which('uv'):
            self.vendor_script('https://astral.sh/uv/install.sh')
        self.run('uv', '--version')
        self.run('uv', 'python', 'install', '3.11', '3.13', '3.14')

    def rust(self):
        if not shutil.which('rustc'):
            self.vendor_script('https://sh.rustup.rs', args=('-y', '--profile', 'minimal'))
        self.run('rustc', '--version')
        self.run('cargo', '--version')

    def java(self):
        self.packages('jdk17-openjdk' if self.family == 'arch' else 'openjdk-17-jdk')

    def github_cli(self):
        if not shutil.which('gh'):
            self.packages('github-cli' if self.family == 'arch' else 'gh')
        self.run('gh', '--version')

    def cloudflared(self):
        if not shutil.which('cloudflared'):
            if self.family == 'arch':
                self.packages('cloudflared')
            else:
                # The provider publishes this key in binary OpenPGP format.
                with tempfile.TemporaryDirectory(prefix='uri-cloudflared-') as tmp:
                    key = Path(tmp) / 'cloudflare-main.gpg'
                    self.download('https://pkg.cloudflare.com/cloudflare-main.gpg', key)
                    self.run('sudo', 'install', '-m', '644', key, '/usr/share/keyrings/cloudflare-main.gpg')
                line = 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main\n'
                self.run('sudo', 'tee', '/etc/apt/sources.list.d/cloudflared.list', input=line, text=True, stdout=subprocess.DEVNULL)
                self.run('sudo', 'apt-get', 'update')
                self.packages('cloudflared')
        self.run('cloudflared', '--version')

    def github_release(self, repository, directory):
        meta = directory / 'release.json'
        self.download('https://api.github.com/repos/' + repository + '/releases/latest', meta)
        return json.loads(meta.read_text())

    def supabase(self):
        if not shutil.which('supabase'):
            with tempfile.TemporaryDirectory(prefix='uri-supabase-') as tmp:
                tmp = Path(tmp)
                release = self.github_release('supabase/cli', tmp)
                assets = [a for a in release['assets'] if a['name'] == 'supabase_linux_amd64.tar.gz']
                if len(assets) != 1:
                    raise ValueError('Could not identify the official Supabase Linux download.')
                asset = assets[0]
                if not asset['browser_download_url'].startswith('https://github.com/supabase/cli/releases/download/'):
                    raise ValueError('Unexpected Supabase download URL.')
                digest = asset.get('digest') or ''
                if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
                    raise ValueError('Supabase release does not provide a SHA-256 digest.')
                archive = tmp / 'supabase.tar.gz'
                self.download(asset['browser_download_url'], archive)
                if hashlib.sha256(archive.read_bytes()).hexdigest() != digest[7:]:
                    raise ValueError('Supabase checksum mismatch.')
                with tarfile.open(archive) as tar:
                    members = [m for m in tar.getmembers() if m.name in ('supabase', './supabase') and m.isfile()]
                    if len(members) != 1:
                        raise ValueError('Supabase archive has no unique executable.')
                    binary = tmp / 'supabase'
                    binary.write_bytes(tar.extractfile(members[0]).read())
                binary.chmod(0o755)
                self.run(binary, '--version')
                self.run('install', '-m', '755', binary, self.home / '.local' / 'bin' / 'supabase')
        self.run('supabase', '--version')

    def docker(self):
        if self.family == 'arch':
            self.packages('docker', 'docker-compose', 'docker-buildx')
        elif not shutil.which('docker'):
            upstream = 'debian' if self.info.get('ID') == 'debian' else 'ubuntu'
            codename = self.info.get('UBUNTU_CODENAME') or self.info.get('VERSION_CODENAME')
            if not codename or not re.fullmatch(r'[a-z]+', codename):
                raise ValueError('Cannot determine the upstream release for Docker packages.')
            key = 'https://download.docker.com/linux/' + upstream + '/gpg'
            line = 'deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/' + upstream + ' ' + codename + ' stable'
            self.apt_source('docker', key, line)
            self.packages('docker-ce', 'docker-ce-cli', 'containerd.io', 'docker-buildx-plugin', 'docker-compose-plugin')
        self.run('docker', '--version')
        self.run('docker', 'compose', 'version')
        self.run('sudo', 'systemctl', 'enable', '--now', 'docker.service')
        self.run('sudo', 'usermod', '-aG', 'docker', subprocess.check_output(['id', '-un'], text=True).strip())
        return 'Docker Engine and Compose ready. Log out/back in for Docker group access. Colima data is not migrated.'

    def media_tools(self):
        self.packages('ffmpeg', 'tesseract' if self.family == 'arch' else 'tesseract-ocr', 'ripgrep')
        if not shutil.which('uv'):
            raise ValueError('uv is needed to install yt-dlp.')
        self.run('uv', 'tool', 'install', 'yt-dlp')

    def whisper(self):
        if shutil.which('whisper-cli'):
            return
        self.packages(*(['cmake', 'base-devel'] if self.family == 'arch' else ['cmake', 'build-essential']))
        with tempfile.TemporaryDirectory(prefix='uri-whisper-') as tmp:
            tmp = Path(tmp)
            release = self.github_release('ggml-org/whisper.cpp', tmp)
            tag = release['tag_name']
            if not re.fullmatch(r'v\d+\.\d+\.\d+', tag):
                raise ValueError('Unexpected whisper.cpp release tag.')
            source = tmp / 'source'
            self.run('git', 'clone', '--depth', '1', '--branch', tag, 'https://github.com/ggml-org/whisper.cpp.git', source)
            self.run('cmake', '-S', source, '-B', source / 'build', '-DCMAKE_BUILD_TYPE=Release',
                     '-DBUILD_SHARED_LIBS=OFF', '-DWHISPER_BUILD_TESTS=OFF', '-DGGML_NATIVE=OFF')
            self.run('cmake', '--build', source / 'build', '--config', 'Release', '--target', 'whisper-cli', '-j', '2')
            self.run('install', '-m', '755', source / 'build/bin/whisper-cli', self.home / '.local/bin/whisper-cli')
        return 'whisper-cli installed. Speech models are downloaded separately when needed.'

    def slack(self):
        if not shutil.which('slack'):
            self.snap_package('slack')

    def discord(self):
        if shutil.which('discord'):
            return
        if self.family == 'arch':
            self.packages('discord')
        else:
            with tempfile.TemporaryDirectory(prefix='uri-discord-') as tmp:
                package = Path(tmp) / 'discord.deb'
                self.download('https://discord.com/api/download?platform=linux&format=deb', package)
                self.run('sudo', 'apt-get', 'install', '-y', package)

    def signal(self):
        if shutil.which('signal-desktop'):
            return
        if self.family == 'arch':
            self.packages('signal-desktop')
        else:
            with tempfile.TemporaryDirectory(prefix='uri-signal-') as tmp:
                tmp = Path(tmp)
                self.download('https://updates.signal.org/desktop/apt/keys.asc', tmp / 'key.asc')
                self.run('gpg', '--batch', '--yes', '--dearmor', '--output', tmp / 'key.gpg', tmp / 'key.asc')
                self.run('sudo', 'install', '-m', '644', tmp / 'key.gpg', '/usr/share/keyrings/signal-desktop-keyring.gpg')
                self.download('https://updates.signal.org/static/desktop/apt/signal-desktop.sources', tmp / 'signal.sources')
                self.run('sudo', 'install', '-m', '644', tmp / 'signal.sources', '/etc/apt/sources.list.d/signal-desktop.sources')
            self.run('sudo', 'apt-get', 'update')
            self.packages('signal-desktop')

    def telegram(self):
        if shutil.which('telegram-desktop') or shutil.which('Telegram'):
            return
        if self.family == 'arch':
            self.packages('telegram-desktop')
        else:
            self.snap_package('telegram-desktop')
