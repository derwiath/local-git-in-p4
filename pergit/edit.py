"""
Edit command implementation for pergit.
"""

import re
import sys
from .common import ensure_workspace, run


class LocalChanges:
    """Container for local git changes."""

    def __init__(self):
        self.adds = []
        self.mods = []
        self.dels = []
        self.moves = []


def check_file_status(filename, workspace_dir):
    """
    Check if a file is already checked out in Perforce and return its changelist.

    Args:
        filename: The file to check
        workspace_dir: The workspace directory

    Returns:
        changelist_number or None
        changelist_number is None if file is not checked out
    """
    res = run(['p4', 'opened', filename], cwd=workspace_dir)

    # Check if file is not opened (p4 opened always returns 0, so check output)
    if not res.stdout or any('file(s) not opened on this client' in line for line in res.stdout):
        return None

    # Parse the output to extract changelist number
    # Format: "//depot/path/file#1 - edit change 12345 (text) by user@workspace"
    for line in res.stdout:
        if '- edit default change ' in line:
            return 'default'
        if '- edit change ' in line:
            # Extract changelist number using regex
            match = re.search(r'change (\d+)', line)
            if match:
                return match.group(1)

    # If we get here, file is checked out but we couldn't parse the changelist
    return None


def get_local_git_changes(base_branch, workspace_dir):
    """
    Get local git changes between base_branch and HEAD.

    Args:
        base_branch: The base branch to compare against
        workspace_dir: The git workspace directory

    Returns:
        Tuple of (returncode, LocalChanges object or None)
    """
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


def edit_command(args):
    """
    Execute the edit command.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    workspace_dir = ensure_workspace()

    returncode, changes = get_local_git_changes(
        args.base_branch, workspace_dir)
    if returncode != 0:
        print('Failed to get a list of changed files', file=sys.stderr)
        return returncode

    # Process added files
    for filename in changes.adds:
        res = run(['p4', 'add', '-c', args.changelist, filename],
                  cwd=workspace_dir, dry_run=args.dry_run)
        if res.returncode != 0:
            print('Failed to add file to perforce', file=sys.stderr)
            return False

    # Process modified files
    for filename in changes.mods:
        # Check if file is already checked out
        current_changelist = check_file_status(filename, workspace_dir)

        if current_changelist is None:
            # File is not checked out, use p4 edit
            res = run(['p4', 'edit', '-c', args.changelist, filename],
                      cwd=workspace_dir, dry_run=args.dry_run)
            if res.returncode != 0:
                print('Failed to open file for edit in perforce', file=sys.stderr)
                return False
        elif current_changelist != args.changelist:
            # File is checked out in different changelist, use p4 reopen
            res = run(['p4', 'reopen', '-c', args.changelist, filename],
                      cwd=workspace_dir, dry_run=args.dry_run)
            if res.returncode != 0:
                print('Failed to reopen file in perforce', file=sys.stderr)
                return False
        # If current_changelist == args.changelist, file is already in correct changelist, do nothing

    # Process deleted files
    for filename in changes.dels:
        res = run(['p4', 'delete', '-c', args.changelist, filename],
                  cwd=workspace_dir, dry_run=args.dry_run)
        if res.returncode != 0:
            print('Failed to delete file from perforce', file=sys.stderr)
            return False

    # Process moved/renamed files
    for from_filename, to_filename in changes.moves:
        res = run(['p4', 'delete', '-c', args.changelist, from_filename],
                  cwd=workspace_dir, dry_run=args.dry_run)
        if res.returncode != 0:
            print('Failed to delete from-file in perforce', file=sys.stderr)
            return False
        res = run(['p4', 'add', '-c', args.changelist, to_filename],
                  cwd=workspace_dir, dry_run=args.dry_run)
        if res.returncode != 0:
            print('Failed to add file to-file to perforce', file=sys.stderr)
            return False

    return 0
