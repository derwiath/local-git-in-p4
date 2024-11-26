import argparse
import itertools
import os
import os.path
import queue
import subprocess
import threading
from timeit import default_timer as timer
from datetime import timedelta
import sys
import time
import re


def is_workspace_dir(directory):
    return os.path.isdir(os.path.join(directory, '.git'))


def get_workspace_dir():
    candidate_dir = os.getcwd()
    while True:
        if is_workspace_dir(candidate_dir):
            return candidate_dir

        parent_dir = os.path.dirname(candidate_dir)
        if parent_dir == candidate_dir:
            return None
        candidate_dir = parent_dir


workspace_dir = get_workspace_dir()
if not workspace_dir:
    print('Failed to find workspace root directory')
    sys.exit(1)


def create_parser():
    parser = argparse.ArgumentParser(description='Build utilities')
    parser.add_argument('--base-branch', default='main',
                        help='Base branch where p4 and git are in sync')
    parser.add_argument('-n', '--dry-run', default=False, action='store_true')
    return parser


def enqueue_output(stream, output_queue):
    try:
        for line in iter(stream.readline, ''):
            output_queue.put(line)
            time.sleep(0.2)
    except ValueError:
        pass
    finally:
        stream.close()


def enqueue_error(stream, error_queue):
    try:
        for line in iter(stream.readline, ''):
            error_queue.put(line)
            time.sleep(0.2)
    except ValueError:
        pass
    finally:
        stream.close()


class RunResult:
    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def run(command, cwd='.', dry_run=False):
    command_line = ''
    for c in command:
        if c.find(' ') != -1:
            command_line += ' "%s"' % c
        else:
            command_line += ' %s' % c
    print('>', command_line)

    if dry_run:
        return RunResult(0, [], [])

    start_timestamp = timer()

    result = subprocess.run(command,
                            cwd=cwd,
                            capture_output=True,
                            text=True)

    end_timestamp = timer()

    print('Elapsed time is', timedelta(seconds=end_timestamp - start_timestamp))

    return RunResult(result.returncode, result.stdout.splitlines(), result.stderr.splitlines())


class LocalChanges:
    def __init__(self):
        self.adds = []
        self.mods = []
        self.dels = []
        self.moves = []


def get_local_git_changes(base_branch):
    res = run(['git', 'diff', '--name-status', '{}..HEAD'.format(base_branch)],
              cwd=workspace_dir)
    if res.returncode != 0:
        return (res.returncode, None)

    changes = LocalChanges()
    renamepattern = r"^r(\d+)$"
    for line in res.stdout:
        tokens = line.split('\t')
        status = tokens[0].lower()
        filename = tokens[1]
        if status == 'm':
            changes.mods.append(filename)
        elif status == 'd':
            changes.dels.append(filename)
        elif status == 'a':
            changes.adds.append(filename)
        elif re.search(renamepattern, status):
            from_filename = filename
            to_filename = tokens[2]
            changes.moves.append((from_filename, to_filename))
        else:
            print('Unknown git status in "{}"'.format(line), file=sys.stderr)
            return (1, None)

    return (0, changes)


def main():
    parser = create_parser()
    args = parser.parse_args()

    returncode, changes = get_local_git_changes(args.base_branch)
    if returncode != 0:
        print('Failed to get a list of changed files', file=sys.stderr)

    for filename in changes.adds:
        res = run(['p4', 'add', filename],
                  cwd=workspace_dir, dry_run=args.dry_run)
        if res.returncode != 0:
            print('Failed to add file to perforce', file=sys.stderr)
            return False

    for filename in changes.mods:
        res = run(['p4', 'edit', filename],
                  cwd=workspace_dir, dry_run=args.dry_run)
        if res.returncode != 0:
            print('Failed to open file for edit in perforce', file=sys.stderr)
            return False

    for filename in changes.dels:
        res = run(['p4', 'delete', filename],
                  cwd=workspace_dir, dry_run=args.dry_run)
        if res.returncode != 0:
            print('Failed to delete file from perforce', file=sys.stderr)
            return False

    for from_filename, to_filename in changes.moves:
        res = run(['p4', 'delete', from_filename],
                  cwd=workspace_dir, dry_run=args.dry_run)
        if res.returncode != 0:
            print('Failed to delete from-file in perforce', file=sys.stderr)
            return False
        res = run(['p4', 'add', to_filename],
                  cwd=workspace_dir, dry_run=args.dry_run)
        if res.returncode != 0:
            print('Failed to add file to-file to perforce', file=sys.stderr)
            return False

    return 0


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
