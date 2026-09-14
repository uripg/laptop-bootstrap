#!/usr/bin/env python3
"""Install Uri's apps on Omarchy/Arch or Ubuntu/Pop!_OS/Debian desktops."""
import argparse
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import tempfile
import time
from terminal_ui import banner, stage, done, paint, duration
from datetime import datetime, timezone
from developer_tools import DeveloperTools


def distro(text):
    values = {}
    for line in text.splitlines():
        if '=' in line and not line.startswith('#'):
            key, value = line.split('=', 1)
            parts = shlex.split(value)
            values[key] = parts[0] if parts else ''
    ids = set((values.get('ID', '') + ' ' + values.get('ID_LIKE', '')).split())
    if 'arch' in ids:
        return 'arch', values
    if ids & {'ubuntu', 'pop', 'debian', 'linuxmint'}:
        return 'apt', values
    raise ValueError('Supported targets: Omarchy/Arch, Pop!_OS, Ubuntu, Debian and Ubuntu-based Mint.')


class Installer(DeveloperTools):
    def __init__(self, family, info):
        self.family, self.info = family, info
        self.home = Path.home()
        self.snap_ready = False

    def run(self, *args, **kwargs):
        print('+ ' + shlex.join(str(a) for a in args), flush=True)
        return subprocess.run([str(a) for a in args], check=True, **kwargs)

    def packages(self, *names):
        if self.family == 'arch':
            self.run('sudo', 'pacman', '-S', '--needed', '--noconfirm', *names)
        else:
            self.run('sudo', 'apt-get', 'install', '-y', *names)

    def aur(self, *names):
        helper = shutil.which('yay') or shutil.which('paru')
        if not helper:
            raise ValueError('An AUR helper (yay or paru) is required for these apps. Omarchy normally includes yay.')
        self.run(helper, '-S', '--needed', '--noconfirm', *names)

    def vendor_script(self, url, shell='sh', args=()):
        with tempfile.TemporaryDirectory(prefix='uri-app-install-') as tmp:
            script = Path(tmp) / 'install.sh'
            self.run('curl', '--proto', '=https', '--proto-redir', '=https', '-fsSL', '--retry', '3', url, '-o', script)
            self.run(shell, script, *args)

    def prerequisites(self):
        if self.family == 'apt':
            self.run('sudo', 'apt-get', 'update')
            self.packages('curl', 'ca-certificates', 'gnupg', 'git', 'xz-utils',
                          'unzip', 'gnome-keyring', 'libsecret-1-0', 'libvulkan1', 'xdg-utils')
        else:
            self.packages('curl', 'ca-certificates', 'gnupg', 'git', 'xz',
                          'unzip', 'gnome-keyring', 'libsecret', 'vulkan-icd-loader', 'xdg-utils', 'base-devel')
        (self.home / '.local' / 'bin').mkdir(parents=True, exist_ok=True)

    def snap(self):
        if self.snap_ready:
            return
        if not shutil.which('snap'):
            if self.family == 'arch':
                self.aur('snapd')
            else:
                self.packages('snapd')
        self.run('sudo', 'systemctl', 'enable', '--now', 'snapd.socket')
        apparmor = Path('/sys/module/apparmor/parameters/enabled')
        if apparmor.exists() and apparmor.read_text().strip() == 'Y':
            self.run('sudo', 'systemctl', 'enable', '--now', 'snapd.apparmor.service')
        if not Path('/snap').exists() and not Path('/snap').is_symlink():
            self.run('sudo', 'ln', '-s', '/var/lib/snapd/snap', '/snap')
        self.run('sudo', 'snap', 'wait', 'system', 'seed.loaded')
        self.snap_ready = True

    def snap_package(self, name, classic=False):
        self.snap()
        exists = subprocess.run(['snap', 'list', name], stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL).returncode == 0
        if not exists:
            self.run('sudo', 'snap', 'install', name, *(['--classic'] if classic else []))

    def codex(self):
        if not shutil.which('codex'):
            self.vendor_script('https://chatgpt.com/codex/install.sh')
        self.run('codex', '--version')

    def codex_desktop(self):
        # The official desktop preview has no Arch package. Pop is an Ubuntu derivative.
        supported = self.family == 'apt' and (
            self.info.get('UBUNTU_CODENAME') in {'noble', 'resolute'} or
            (self.info.get('ID') == 'ubuntu' and self.info.get('VERSION_ID') in {'24.04', '26.04'}) or
            (self.info.get('ID') == 'debian' and self.info.get('VERSION_ID') == '13') or
            (self.info.get('ID') == 'pop' and self.info.get('VERSION_ID') in {'24.04', '26.04'}))
        if not supported:
            return 'Desktop preview has no supported package for this distribution/version. Use Codex CLI.'
        if not shutil.which('chatgpt'):
            with tempfile.TemporaryDirectory(prefix='uri-chatgpt-') as tmp:
                package = Path(tmp) / 'chatgpt_amd64.deb'
                self.run('curl', '--proto', '=https', '--proto-redir', '=https', '-fsSL', '--retry', '3',
                         'https://persistent.oaistatic.com/codex-app-prod/linux/deb/latest/chatgpt_amd64.deb', '-o', package)
                self.run('sudo', 'apt-get', 'install', '-y', package)
        return 'Desktop preview installed. Pop!_OS/Mint derivatives are not formally supported by OpenAI.'

    def claude(self):
        if not shutil.which('claude'):
            self.vendor_script('https://claude.ai/install.sh', shell='bash')
        self.run('claude', '--version')

    def cursor(self):
        if shutil.which('cursor'):
            return
        if self.family == 'arch':
            self.aur('cursor-bin')
        else:
            with tempfile.TemporaryDirectory(prefix='uri-cursor-') as tmp:
                key = Path(tmp) / 'anysphere.asc'
                self.run('curl', '--proto', '=https', '--proto-redir', '=https', '-fsSL',
                         'https://downloads.cursor.com/keys/anysphere.asc', '-o', key)
                self.run('sudo', 'install', '-d', '-m', '755', '/etc/apt/keyrings')
                self.run('sudo', 'install', '-m', '644', key, '/etc/apt/keyrings/cursor.asc')
                line = 'deb [arch=amd64 signed-by=/etc/apt/keyrings/cursor.asc] https://downloads.cursor.com/aptrepo stable main\n'
                self.run('sudo', 'tee', '/etc/apt/sources.list.d/cursor.list', input=line, text=True,
                         stdout=subprocess.DEVNULL)
            self.run('sudo', 'apt-get', 'update')
            self.packages('cursor')
        if not shutil.which('cursor'):
            raise ValueError('Cursor installation did not provide its launcher.')

    def zed(self):
        if not (shutil.which('zed') or shutil.which('zeditor')):
            self.vendor_script('https://zed.dev/install.sh')
        binary = shutil.which('zed') or shutil.which('zeditor')
        if not binary:
            raise ValueError('Zed launcher was not found after installation.')
        self.run(binary, '--version')

    def nordpass(self):
        self.snap_package('nordpass')
        self.run('sudo', 'snap', 'connect', 'nordpass:password-manager-service')

    def brave(self):
        if shutil.which('brave') or shutil.which('brave-browser'):
            return
        if self.family == 'arch':
            self.aur('brave-bin')
        else:
            self.vendor_script('https://dl.brave.com/install.sh')
        if not (shutil.which('brave') or shutil.which('brave-browser')):
            raise ValueError('Brave launcher was not found after installation.')

    def nordvpn(self):
        if self.family == 'arch':
            self.aur('nordvpn-bin', 'nordvpn-gui-bin')
        else:
            self.vendor_script('https://downloads.nordcdn.com/apps/linux/install.sh', args=('-n', '-p', 'nordvpn-gui'))
        self.run('sudo', 'systemctl', 'enable', '--now', 'nordvpnd.service')
        if subprocess.run(['getent', 'group', 'nordvpn'], stdout=subprocess.DEVNULL).returncode == 0:
            self.run('sudo', 'usermod', '-aG', 'nordvpn', subprocess.check_output(['id', '-un'], text=True).strip())
        self.run('nordvpn', '--version')
        return 'Installed. Log out/back in before login. No VPN connection or autoconnect was enabled.'

    def ghostty(self):
        if shutil.which('ghostty'):
            return
        if self.family == 'arch':
            self.packages('ghostty')
        else:
            policy = subprocess.run(['apt-cache', 'policy', 'ghostty'], stdout=subprocess.PIPE, text=True, env=dict(os.environ, LC_ALL='C'))
            candidate = any(line.strip().startswith('Candidate:') and '(none)' not in line for line in policy.stdout.splitlines())
            if candidate:
                self.packages('ghostty')
            else:
                self.snap_package('ghostty', classic=True)
        if not (shutil.which('ghostty') or Path('/snap/bin/ghostty').exists()):
            raise ValueError('Ghostty launcher was not found after installation.')

    def shell_path(self):
        block = '\n# uri-laptop-setup: developer launchers v2\nexport PATH="$HOME/.local/bin:$HOME/.bun/bin:$HOME/.deno/bin:$HOME/.cargo/bin:/snap/bin:$PATH"\n'
        for name in ('.profile', '.bashrc', '.zshrc'):
            path = self.home / name
            if name == '.zshrc' and not path.exists():
                continue
            if path.is_symlink():
                print('Skipping linked shell config: ' + str(path))
                continue
            text = path.read_text() if path.exists() else ''
            if '# uri-laptop-setup: developer launchers v2' not in text:
                with path.open('a') as output:
                    output.write(block)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', action='store_true', help='Show the chosen package routes without installing anything.')
    args = parser.parse_args()
    family, info = distro(Path('/etc/os-release').read_text())
    banner('Set up your Linux laptop')
    print('System: ' + info.get('PRETTY_NAME', info.get('ID', 'Linux')))
    print('Apps: Codex CLI, Claude Code, Cursor, Zed, NordPass, Brave, NordVPN GUI/CLI, Ghostty.')
    print('Also: Slack, Discord, Signal, Telegram and the approved development/media tools.')
    print('Excluded: Tailscale, Android tools/Studio, Unity Hub, RustDesk, Blender, Hermes, T3, OpenCode and Colima.')
    print('Codex desktop preview is additionally attempted on compatible Ubuntu/Debian bases.')
    print('Arch uses AUR packages for Cursor, Brave, NordVPN and Snap. NordPass uses Snap.')
    if args.plan:
        return 0
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise ValueError('This complete app set currently targets Intel/AMD 64-bit Linux laptops.')
    if os.geteuid() == 0:
        raise ValueError('Run as your normal user, without sudo. Individual package commands use sudo.')
    os.environ['PATH'] = ':'.join(str(Path.home() / p) for p in ('.local/bin', '.bun/bin', '.deno/bin', '.cargo/bin')) + ':/snap/bin:' + os.environ['PATH']
    installer = Installer(family, info)
    stage(1, 28, 'Prepare system requirements')
    print('Your Linux password may be requested by sudo. Package progress and prompts appear below.', flush=True)
    installer.prerequisites()
    results = []
    tasks = [('Codex CLI', installer.codex), ('Codex desktop', installer.codex_desktop),
             ('Claude Code', installer.claude), ('Cursor', installer.cursor), ('Zed', installer.zed),
             ('NordPass', installer.nordpass), ('Brave', installer.brave),
             ('NordVPN', installer.nordvpn), ('Ghostty', installer.ghostty),
             ('Slack', installer.slack), ('Discord', installer.discord), ('Signal', installer.signal), ('Telegram', installer.telegram),
             ('Node.js 24', installer.node), ('pnpm / Wrangler / Clerk', installer.npm_tools),
             ('Bun', installer.bun), ('Deno', installer.deno), ('Python / uv', installer.python_tools),
             ('Rust / Cargo', installer.rust), ('Java 17', installer.java), ('GitHub CLI', installer.github_cli),
             ('cloudflared', installer.cloudflared), ('Supabase CLI', installer.supabase), ('Docker / Compose', installer.docker),
             ('FFmpeg / Tesseract / yt-dlp / ripgrep', installer.media_tools), ('whisper.cpp', installer.whisper),
             ('Shell path', installer.shell_path)]
    started_all = time.monotonic()
    for index, (name, task) in enumerate(tasks, start=2):
        stage(index, len(tasks) + 1, name)
        started = time.monotonic()
        try:
            note = task() or 'Installed or already present.'
            status = 'unavailable' if name == 'Codex desktop' and note.startswith('Desktop preview has no supported') else 'ok'
            results.append(dict(app=name, status=status, note=note))
            if status == 'ok':
                done(name, started)
            else:
                print(paint('  SKIP  ' + note, '33'), flush=True)
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            results.append(dict(app=name, status='failed', note=str(error)))
            print(paint('  FAILED  ' + name + ': ' + str(error), '31'), flush=True)
            print('Continuing with the remaining apps.', flush=True)
    state = Path.home() / '.local' / 'state' / 'uri-laptop-setup'
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    (state / 'apps.json').write_text(json.dumps(dict(date=datetime.now(timezone.utc).isoformat(), results=results), indent=2) + '\n')
    banner('App setup results')
    counts = {status: sum(item['status'] == status for item in results) for status in ('ok', 'unavailable', 'failed')}
    print(f"{counts['ok']} ready · {counts['unavailable']} unavailable · {counts['failed']} need attention · {duration(time.monotonic() - started_all)}")
    for item in results:
        label = {'ok': 'OK', 'unavailable': 'SKIP', 'failed': 'FAILED'}[item['status']]
        print(f"  {label:6} {item['app']}")
        if item['status'] != 'ok' or item['note'] != 'Installed or already present.':
            print('         ' + item['note'])
    print('\nLog out and back in for Snap launchers and NordVPN permissions. Sign into your apps afterward.')
    print('For Codex run codex; for Claude Code run claude. Open the desktop apps from the application menu.')
    print('Report: ' + str(state / 'apps.json'))
    return int(any(item['status'] == 'failed' for item in results))


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('Setup stopped: ' + str(error))
        raise SystemExit(1)
    except KeyboardInterrupt:
        print('\nSetup interrupted. Rerun to continue with installed apps preserved.')
        raise SystemExit(1)
