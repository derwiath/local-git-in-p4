#!/usr/bin/env python3
"""Pre-sync hook that aborts the sync while a named process is running.

Syncing while the Unreal editor is open lets p4 replace assets the editor
still has loaded, so the editor keeps working against files that no longer
match what is on disk. This hook blocks the sync until it is closed.

Install by symlinking (or copying) this file into the workspace as
    .git-p4son/hooks/pre-sync/block-while-running.py
On macOS and Linux it also needs the executable bit, which a symlink takes
from this file in the clone; on Windows git-p4son runs .py hooks through
python.exe, so no bit is needed there.

Which processes block the sync is read from the workspace's own
.git-p4son/config.toml, so a symlinked hook stays per-project:

    [hooks.block-while-running]
    processes = ["UnrealEditor", "UnrealLightmass"]

Names are matched with any .exe suffix stripped and case ignored, so one
entry covers "UnrealEditor.exe" on Windows and "UnrealEditor" on macOS.
Without that table nothing is checked and the sync proceeds. Set
GIT_P4SON_SKIP_PROCESS_CHECK=1 to sync anyway for one run.
"""

import csv
import os
import subprocess
import sys
import tomllib

CONFIG_RELPATH = ('.git-p4son', 'config.toml')
CONFIG_TABLE = ('hooks', 'block-while-running')
CONFIG_KEY = 'processes'

BYPASS_ENV_VAR = 'GIT_P4SON_SKIP_PROCESS_CHECK'
REPO_ROOT_ENV_VAR = 'GIT_P4SON_REPO_ROOT_DIR'


def config_path() -> str:
    """Return the path to the workspace config file.

    git-p4son sets GIT_P4SON_REPO_ROOT_DIR for every hook; the CWD fallback
    only matters when running this script by hand from the workspace root.
    """
    root = os.environ.get(REPO_ROOT_ENV_VAR) or os.getcwd()
    return os.path.join(root, *CONFIG_RELPATH)


def blocking_processes() -> tuple[str, ...]:
    """Return the process names that should block a sync.

    An absent config file, table or key means nothing is configured, so
    nothing is checked; only a table that is present but malformed is an
    error.
    """
    path = config_path()
    if not os.path.exists(path):
        return ()

    with open(path, 'rb') as config_file:
        table = tomllib.load(config_file)
    for key in CONFIG_TABLE:
        table = table.get(key, {})
        if not isinstance(table, dict):
            raise ValueError(
                f'{".".join(CONFIG_TABLE)} in {path} is not a table')

    names = table.get(CONFIG_KEY)
    if names is None:
        return ()
    if (not isinstance(names, list)
            or not all(isinstance(name, str) for name in names)):
        raise ValueError(
            f'{".".join(CONFIG_TABLE)}.{CONFIG_KEY} in {path} must be a '
            'list of strings')
    return tuple(names)


def normalize(name: str) -> str:
    """Reduce a process name to a form comparable across platforms."""
    name = os.path.basename(name.strip())
    if name.lower().endswith('.exe'):
        name = name[:-len('.exe')]
    return name.lower()


def running_processes() -> set[str]:
    """Return the normalized names of all currently running processes."""
    if os.name == 'nt':
        # /NH drops the header row. CSV output keeps an image name that
        # contains spaces or commas inside one quoted field.
        command = ['tasklist', '/NH', '/FO', 'CSV']
    else:
        # -ww stops ps truncating output to the terminal width, which would
        # otherwise cut long process names short.
        command = ['ps', '-A', '-ww', '-o', 'comm=']

    result = subprocess.run(command, capture_output=True, text=True,
                            errors='replace')
    if result.returncode != 0:
        raise RuntimeError(
            f'{command[0]} exited with {result.returncode}: '
            f'{result.stderr.strip()}')

    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if os.name == 'nt':
        return {normalize(row[0]) for row in csv.reader(lines) if row}
    return {normalize(line) for line in lines}


def main() -> int:
    if os.environ.get(BYPASS_ENV_VAR):
        print(f'{BYPASS_ENV_VAR} is set, skipping the running-process check')
        return 0

    # Malformed config, or a process list that cannot be read, aborts the
    # sync: failing open there would silently drop the protection this hook
    # exists to provide. Config that is simply absent asks for nothing, so
    # it is not an error and the sync proceeds.
    try:
        watched = blocking_processes()
    except (OSError, ValueError, tomllib.TOMLDecodeError) as error:
        print(f'Could not read the hook configuration: {error}',
              file=sys.stderr)
        return 1

    if not watched:
        return 0

    try:
        running = running_processes()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'Could not list running processes: {error}', file=sys.stderr)
        return 1

    blocking = sorted(name for name in watched if normalize(name) in running)
    if not blocking:
        return 0

    print('Refusing to sync, these processes are running:', file=sys.stderr)
    for name in blocking:
        print(f'  {name}', file=sys.stderr)
    print(f'Close them and sync again, or set {BYPASS_ENV_VAR}=1 to sync '
          'anyway.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
