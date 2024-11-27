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
    parser = argparse.ArgumentParser(
        description='Sync local git repo with a perforce workspace')
    parser.add_argument('changelist', help='Changelist to sync')
    parser.add_argument(
        '-f', '--force', default=False, action='store_true',
        help='Force sync encountered writable files.'
        ' When clobber is not enabled on your workspace, p4 will fail to sync'
        ' files that are read-only. git removes the readonly' +
        ' flag on touched files.'
    )
    return parser


def enqueue_lines(stream, output_queue):
    for line in iter(stream.readline, ''):
        output_queue.put(line.rstrip())


def echo_output_to_stream(line, stream):
    print(line, file=stream)


def run(command, cwd='.', on_output=None):
    command_line = ''
    for c in command:
        if c.find(' ') != -1:
            command_line += ' "%s"' % c
        else:
            command_line += ' %s' % c
    print('>', command_line)

    start_timestamp = timer()

    stdout_lines = []
    stderr_lines = []
    returncode = None

    with subprocess.Popen(command,
                          cwd=cwd,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,
                          stdin=None,
                          text=True) as process:

        output_queue = queue.Queue()
        out_thread = threading.Thread(
            target=enqueue_lines, args=(process.stdout, output_queue))
        out_thread.daemon = True

        error_queue = queue.Queue()
        err_thread = threading.Thread(
            target=enqueue_lines, args=(process.stderr, error_queue))
        err_thread.daemon = True

        out_thread.start()
        err_thread.start()

        def poll_queue_until_empty(q, lines, cb):
            try:
                while not q.empty():
                    line = q.get_nowait()
                    lines.append(line)
                    if cb:
                        cb(line)
            except queue.Empty:
                pass
        try:
            def on_stdout(l): return on_output(
                line=l, stream=sys.stdout) if on_output else None
            def on_stderr(l): return on_output(
                line=l, stream=sys.stderr) if on_output else None
            while True:
                poll_queue_until_empty(output_queue,
                                       stdout_lines,
                                       on_stdout)
                poll_queue_until_empty(error_queue,
                                       stderr_lines,
                                       on_stderr)
                if process.poll() is not None:
                    if output_queue.empty() and error_queue.empty():
                        break

            # Wait for threads to finish
            out_thread.join()
            err_thread.join()

            (final_stdout, final_stderr) = process.communicate()
            returncode = process.returncode

            if final_stdout:
                final_stdout_lines = final_stdout.splitlines()
                stdout_lines = stdout_lines + final_stdout_lines
                for l in final_stdout_lines:
                    on_stdout(l)

            if final_stderr:
                stderr_lines = stderr_lines + final_stderr.splitlines()
                stderr_lines = stderr_lines + final_stderr_lines
                for l in final_stderr_lines:
                    on_stderr(l)

        except KeyboardInterrupt:
            print("CTRL-C pressed, terminate subprocess")
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("Subprocess did not terminate in time. Forcing kill...")
                process.kill()
            sys.exit(1)

    end_timestamp = timer()

    print('Elapsed time is', timedelta(seconds=end_timestamp - start_timestamp))

    class RunResult:
        def __init__(self, returncode, stdout, stderr):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    return RunResult(returncode, stdout_lines, stderr_lines)


def get_writable_files(stderr_lines):
    cant_clobber_prefix = "Can't clobber writable file "
    writable_files = []
    for line in stderr_lines:
        if not line.startswith(cant_clobber_prefix):
            continue
        writable_file = line[len(cant_clobber_prefix):]
        writable_files.append(writable_file.rstrip())
    return writable_files


def parse_p4_sync_line(line):
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
    if not os.path.isfile(filename):
        return 0
    file_stats = os.stat(filename)
    return file_stats.st_size if file_stats else 0


def green_text(s):
    return f'\033[92m{s}\033[0m'


class SyncStats:
    def __init__(self):
        self.count = 0
        self.total_size = 0


def readable_file_size(num, suffix="B"):
    for unit in ('', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi'):
        if abs(num) < 1024.0:
            return f'{num:3.1f}{unit}{suffix}'
        num /= 1024.0
    return f'{num:.1f}Yi{suffix}'


class P4SyncOutputProcessor:
    def __init__(self, file_count_to_sync):
        self.start_timestamp = timer()
        self.synced_file_count = 0
        self.file_count_to_sync = file_count_to_sync
        self.stats = {}
        for mode in ['add', 'del', 'upd', 'clb']:
            self.stats[mode] = SyncStats()

    def __call__(self, line, stream):
        # print('line: ', line)
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
        sync_stats = self.get_sync_stats()
        print(f'Sync stats: {sync_stats}')

        for mode, stat in self.stats.items():
            print(f'{mode}')
            print(f'  count: {stat.count}')
            print('  size : {}'.format(readable_file_size(stat.total_size)))


def p4_force_sync_file(changelist, filename):
    output_processor = P4SyncOutputProcessor(-1)
    res = run(['p4', 'sync', '-f', '%s@%s' %
              (filename, changelist)], on_output=output_processor)
    output_processor.print_stats()
    return res.returncode


def get_file_count_to_sync(changelist):
    res = run(['p4', 'sync', '-n', '//...@%s' % (changelist)])

    if res.returncode != 0:
        return -1

    return len(res.stdout)


def p4_sync(changelist, force):
    file_count_to_sync = get_file_count_to_sync(changelist)
    if file_count_to_sync < 0:
        return False
    if file_count_to_sync == 0:
        print('All files are up to date')
        return True
    print(f'Syncing {file_count_to_sync} files')

    output_processor = P4SyncOutputProcessor(file_count_to_sync)
    res = run(['p4', 'sync', '//...@%s' %
              (changelist)], on_output=output_processor)
    output_processor.print_stats()
    if res.returncode == 0:
        return True

    writable_files = get_writable_files(res.stderr)
    print('Found %d writable files' % len(writable_files))
    if force:
        for filename in writable_files:
            if p4_force_sync_file(changelist, filename) != 0:
                return False
    else:
        print('Leaving files as is, use --force to force sync')
        for filename in writable_files:
            print(filename)
        return False

    return True


def p4_is_workspace_clean():
    res = run(['p4', 'opened'], on_output=echo_output_to_stream)
    if res.returncode != 0:
        print('Failed to run p4 opened')
        return False

    local_changes = res.stdout
    return len(local_changes) == 0


def git_is_workspace_clean():
    res = run(['git', 'status', '--porcelain'],
              on_output=echo_output_to_stream)
    if res.returncode != 0:
        print('Failed to run git status')
        return False

    local_changes = res.stdout
    return len(local_changes) == 0


def git_add_all_files():
    res = run(['git', 'add', '.'], cwd=workspace_dir,
              on_output=echo_output_to_stream)
    return res.returncode == 0


def git_commit(message, allow_empty=False):
    args = ['commit', '-m', message]
    if allow_empty:
        args.append('--allow-empty')
    res = run(['git'] + args,
              cwd=workspace_dir, on_output=echo_output_to_stream)
    return res.returncode == 0


def git_changelist_of_last_commit():
    res = run(['git', 'log', '--oneline', '-1', '--pretty="%s"'],
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


def main():
    parser = create_parser()
    args = parser.parse_args()

    if not git_is_workspace_clean():
        print('git status shows that workspace is not clean, aborting')
        return 1
    print('')

    if not p4_is_workspace_clean():
        print('p4 opened shows that workspace is not clean, aborting')
        return 1
    print('')

    last_changelist = git_changelist_of_last_commit()
    if args.changelist.lower() == 'head':
        if not p4_sync(last_changelist, args.force):
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
        if not p4_sync(last_changelist, args.force):
            print('Failed to sync files from perforce')
            return 1
        print('')

    if not p4_sync(args.changelist, args.force):
        print('Failed to sync files from perforce')
        return 1
    print('')

    if not git_is_workspace_clean():
        if not git_add_all_files():
            print('Failed to add all files to git')
            return 1
        print('')

    commit_msg = '%s: p4 sync //...@%s' % (args.changelist, args.changelist)
    if not git_commit(commit_msg, allow_empty=True):
        print('Failed to commit files to git')
        return 1
    print('')

    print('Finished with success')
    return 0


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
