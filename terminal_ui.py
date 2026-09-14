"""Small, dependency-free terminal display; readable without ANSI support."""
import os
import sys
import time

STARTED = time.monotonic()

def paint(text, code):
    if sys.stdout.isatty() and not os.environ.get('NO_COLOR') and os.environ.get('TERM') != 'dumb':
        return f'\033[{code}m{text}\033[0m'
    return text

def duration(seconds):
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f'{hours}h {minutes:02d}m' if hours else f'{minutes}m {seconds:02d}s'

def size(value):
    value = float(value or 0)
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if value < 1024 or unit == 'TiB':
            return f'{value:.1f} {unit}'
        value /= 1024

def banner(title):
    print('\n' + paint('━' * 56, '36'), flush=True)
    print(paint('  ' + title, '1;36'), flush=True)
    print(paint('━' * 56, '36'), flush=True)

def stage(number, total, title):
    print('\n' + paint(f'[{number}/{total}] {title}', '1;36'), flush=True)

def done(title, started=None):
    elapsed = '' if started is None else ' · ' + duration(time.monotonic() - started)
    print(paint('  OK  ' + title + elapsed, '32'), flush=True)

def progress(event):
    fraction = min(1, max(0, float(event.get('percent_done', 0))))
    filled = int(fraction * 24)
    bar = '#' * filled + '-' * (24 - filled)
    processed = size(event.get('bytes_done', 0))
    total = event.get('total_bytes', 0)
    amount = processed + (' / ' + size(total) if total else ' · discovering total…')
    remaining = event.get('seconds_remaining')
    eta = ' · ~' + duration(remaining) + ' left' if remaining and fraction > 0 else ''
    print(f'  [{bar}] {fraction:5.1%}  {amount}  · {event.get("files_done", 0):,} files' + eta, flush=True)
