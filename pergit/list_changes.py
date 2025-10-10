"""
List-changes command implementation for pergit.
"""

import sys
from .common import ensure_workspace, run


def list_changes_command(args):
    """
    Execute the list-changes command.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    workspace_dir = ensure_workspace()

    # Run git log to get commit subjects since base branch
    # Using --reverse to get oldest commits first
    res = run(['git', 'log', '--oneline', '--reverse', '{}..HEAD'.format(args.base_branch)],
              cwd=workspace_dir)

    if res.returncode != 0:
        print('Failed to get commit list', file=sys.stderr)
        return res.returncode

    # Print numbered list of commit subjects
    for i, line in enumerate(res.stdout, 1):
        # Extract just the subject (everything after the hash and space)
        if ' ' in line:
            subject = line.split(' ', 1)[1]
            print(f"{i}. {subject}")
        else:
            # Fallback if format is unexpected
            print(f"{i}. {line}")

    return 0
