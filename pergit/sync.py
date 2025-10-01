"""
Sync command implementation for pergit.
"""

import os
import re
import subprocess
import sys
import time
from timeit import default_timer as timer
from datetime import timedelta

from .common import ensure_workspace, run, run_with_output


def echo_output_to_stream(line, stream):
    """Echo a line to a stream."""
    print(line, file=stream)


def get_writable_files(stderr_lines):
    """Extract writable files from p4 sync stderr output."""
    cant_clobber_prefix = "Can't clobber writable file "
    writable_files = []
    for line in stderr_lines:
        if not line.startswith(cant_clobber_prefix):
            continue
        writable_file = line[len(cant_clobber_prefix):]
        writable_files.append(writable_file.rstrip())
    return writable_files


def parse_p4_sync_line(line):
    """Parse a line from p4 sync output."""
    patterns = [
        ('add', ' - added as '),
        ('del', ' - deleted as '),
        ('upd', ' - updating '),
        ('clb', "Can't clobber writable file ")
    ]
    for mode, pattern in patterns:
        tokens = line.split(pattern)
        if len(tokens) == 2:
            return (mode, tokens[1])

    return (None, None)


def get_file_size(filename):
    """Get the size of a file in bytes."""
    if not os.path.isfile(filename):
        return 0
    file_stats = os.stat(filename)
    return file_stats.st_size if file_stats else 0


def green_text(s):
    """Format text in green color."""
    return f'\033[92m{s}\033[0m'


class SyncStats:
    """Statistics for sync operations."""

    def __init__(self):
        self.count = 0
        self.total_size = 0


def readable_file_size(num, suffix="B"):
    """Convert bytes to human readable format."""
    for unit in ('', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi'):
        if abs(num) < 1024.0:
            return f'{num:3.1f}{unit}{suffix}'
        num /= 1024.0
    return f'{num:.1f}Yi{suffix}'


class P4SyncOutputProcessor:
    """Process p4 sync output in real-time."""

    def __init__(self, file_count_to_sync):
        self.start_timestamp = timer()
        self.synced_file_count = 0
        self.file_count_to_sync = file_count_to_sync
        self.stats = {}
        for mode in ['add', 'del', 'upd', 'clb']:
            self.stats[mode] = SyncStats()

    def __call__(self, line, stream):
        if re.search(r"//...@\d+ - file\(s\) up-to-date\.", line):
            print('All files are up to date')
            return

        mode, filename = parse_p4_sync_line(line)
        if not mode or not filename:
            print(f'Unparsable line: {line}')
            return

        if mode in self.stats:
            self.stats[mode].count += 1
        self.synced_file_count += 1

        print('{}: {}'.format(green_text(mode), filename))

        indentation = '     '
        if self.file_count_to_sync >= 0:
            print('{}progress: {} / {}'.format(indentation,
                                               self.synced_file_count,
                                               self.file_count_to_sync))

        if mode in ['add', 'upd', 'clb']:
            size = get_file_size(filename)
            self.stats[mode].total_size += size
            print('{}size: {}'.format(indentation, readable_file_size(size)))

        print('{}sync stats {}'.format(indentation, self.get_sync_stats()))

    def get_sync_stats(self):
        """Get current sync statistics."""
        duration_sec = timer() - self.start_timestamp
        duration = timedelta(seconds=duration_sec)

        synced_count = self.stats['add'].count + \
            self.stats['upd'].count - self.stats['clb'].count
        synced_size = self.stats['add'].total_size + \
            self.stats['upd'].total_size - self.stats['clb'].total_size

        return 'file count {}, size {}, time {}, average speed {} / sec'.format(
            synced_count,
            readable_file_size(synced_size),
            duration,
            readable_file_size(synced_size/duration_sec))

    def print_stats(self):
        """Print final sync statistics."""
        sync_stats = self.get_sync_stats()
        print(f'Sync stats: {sync_stats}')

        for mode, stat in self.stats.items():
            print(f'{mode}')
            print(f'  count: {stat.count}')
            print('  size : {}'.format(readable_file_size(stat.total_size)))


def p4_force_sync_file(changelist, filename, workspace_dir):
    """Force sync a single file."""
    output_processor = P4SyncOutputProcessor(-1)
    res = run_with_output(['p4', 'sync', '-f', '%s@%s' %
                          (filename, changelist)], cwd=workspace_dir, on_output=output_processor)
    output_processor.print_stats()
    return res.returncode


def get_file_count_to_sync(changelist, workspace_dir):
    """Get the number of files that need to be synced."""
    res = run(['p4', 'sync', '-n', '//...@%s' %
              (changelist)], cwd=workspace_dir)

    if res.returncode != 0:
        return -1

    return len(res.stdout)


def p4_sync(changelist, force, workspace_dir):
    """Sync files from Perforce."""
    file_count_to_sync = get_file_count_to_sync(changelist, workspace_dir)
    if file_count_to_sync < 0:
        return False
    if file_count_to_sync == 0:
        print('All files are up to date')
        return True
    print(f'Syncing {file_count_to_sync} files')

    output_processor = P4SyncOutputProcessor(file_count_to_sync)
    res = run_with_output(['p4', 'sync', '//...@%s' %
                          (changelist)], cwd=workspace_dir, on_output=output_processor)
    output_processor.print_stats()
    if res.returncode == 0:
        return True

    writable_files = get_writable_files(res.stderr)
    print('Found %d writable files' % len(writable_files))
    if force:
        for filename in writable_files:
            if p4_force_sync_file(changelist, filename, workspace_dir) != 0:
                return False
    else:
        print('Leaving files as is, use --force to force sync')
        for filename in writable_files:
            print(filename)
        return False

    return True


def p4_is_workspace_clean(workspace_dir):
    """Check if Perforce workspace is clean."""
    res = run_with_output(['p4', 'opened'], cwd=workspace_dir,
                          on_output=echo_output_to_stream)
    if res.returncode != 0:
        print('Failed to run p4 opened')
        return False

    local_changes = res.stdout
    return len(local_changes) == 0


def git_is_workspace_clean(workspace_dir):
    """Check if git workspace is clean."""
    res = run_with_output(['git', 'status', '--porcelain'], cwd=workspace_dir,
                          on_output=echo_output_to_stream)
    if res.returncode != 0:
        print('Failed to run git status')
        return False

    local_changes = res.stdout
    return len(local_changes) == 0


def git_add_all_files(workspace_dir):
    """Add all files to git."""
    res = run_with_output(['git', 'add', '.'], cwd=workspace_dir,
                          on_output=echo_output_to_stream)
    return res.returncode == 0


def git_commit(message, workspace_dir, allow_empty=False):
    """Commit changes to git."""
    args = ['commit', '-m', message]
    if allow_empty:
        args.append('--allow-empty')
    res = run_with_output(['git'] + args,
                          cwd=workspace_dir, on_output=echo_output_to_stream)
    return res.returncode == 0


def git_changelist_of_last_commit(workspace_dir):
    """Get the changelist number from the last commit message."""
    res = run_with_output(['git', 'log', '--oneline', '-1', '--pretty="%s"'],
                          cwd=workspace_dir, on_output=echo_output_to_stream)
    if res.returncode != 0 or len(res.stdout) == 0:
        return None

    msg = res.stdout[0]
    pattern = r"(\d+): p4 sync //\.\.\.@\1"
    match = re.search(pattern, msg)
    if match:
        return int(match.group(1))
    else:
        return None


def sync_command(args):
    """
    Execute the sync command.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    workspace_dir = ensure_workspace()

    if not git_is_workspace_clean(workspace_dir):
        print('git status shows that workspace is not clean, aborting')
        return 1
    print('')

    if not p4_is_workspace_clean(workspace_dir):
        print('p4 opened shows that workspace is not clean, aborting')
        return 1
    print('')

    last_changelist = git_changelist_of_last_commit(workspace_dir)
    if args.changelist.lower() == 'head':
        if not p4_sync(last_changelist, args.force, workspace_dir):
            print('Failed to sync files from perforce')
            return 1
        return 0

    args.changelist = int(args.changelist)
    if last_changelist == args.changelist:
        print('Changelist of last commit is %d, nothing to do, aborting '
              % last_changelist)
        return 0
    print('')

    if last_changelist != None:
        if not p4_sync(last_changelist, args.force, workspace_dir):
            print('Failed to sync files from perforce')
            return 1
        print('')

    if not p4_sync(args.changelist, args.force, workspace_dir):
        print('Failed to sync files from perforce')
        return 1
    print('')

    if not git_is_workspace_clean(workspace_dir):
        if not git_add_all_files(workspace_dir):
            print('Failed to add all files to git')
            return 1
        print('')

    commit_msg = '%s: p4 sync //...@%s' % (args.changelist, args.changelist)
    if not git_commit(commit_msg, workspace_dir, allow_empty=True):
        print('Failed to commit files to git')
        return 1
    print('')

    print('Finished with success')
    return 0
