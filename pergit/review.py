"""
Review command implementation for pergit.
"""

import re
import sys
from .common import ensure_workspace, run
from .edit import get_local_git_changes, create_new_changelist, include_changes_in_changelist


def p4_shelve_changelist(changelist, workspace_dir, dry_run=False):
    """
    Shelve a changelist to make it available for review.

    Args:
        changelist: The changelist number to shelve
        workspace_dir: The workspace directory
        dry_run: If True, don't actually shelve

    Returns:
        Tuple of (returncode, success)
    """
    res = run(['p4', 'shelve', '-f', '-Af', '-c', changelist],
              cwd=workspace_dir, dry_run=dry_run)

    if res.returncode != 0:
        print('Failed to shelve changelist', file=sys.stderr)
        return (res.returncode, False)

    return (0, True)


def p4_add_review_keyword_to_changelist(changelist, workspace_dir, dry_run=False):
    """
    Add the #review keyword to a changelist description.

    Args:
        changelist: The changelist number to update
        workspace_dir: The workspace directory
        dry_run: If True, don't actually update

    Returns:
        Tuple of (returncode, success)
    """
    # Get current changelist description
    res = run(['p4', 'change', '-o', changelist], cwd=workspace_dir)
    if res.returncode != 0:
        print('Failed to get changelist description', file=sys.stderr)
        return (res.returncode, False)

    # Parse the changelist spec to find description and track its end
    lines = res.stdout
    description_start_idx = None
    description_end_idx = None

    for i, line in enumerate(lines):
        if line.strip() == 'Description:':
            description_start_idx = i
        elif description_start_idx is not None and line.strip() == '' and i > description_start_idx + 1:
            # Empty line after description content, end of description
            description_end_idx = i
            break

    # If we didn't find an empty line, description goes to end of file
    if description_start_idx is not None and description_end_idx is None:
        description_end_idx = len(lines)

    # Check if #review is already in the description
    if description_start_idx is not None:
        description_text = '\n'.join(
            lines[description_start_idx:description_end_idx])
        if '#review' in description_text:
            print(f'Changelist {changelist} already has #review keyword')
            return (0, True)

    # Add #review as the last line of description
    updated_lines = lines.copy()
    if description_start_idx is not None:
        # Insert #review before the empty line that ends the description
        updated_lines.insert(description_end_idx, '\t')
        updated_lines.insert(description_end_idx, '\t#review')

    # Update the changelist
    if dry_run:
        print(f"Would add #review keyword to changelist {changelist}")
        return (0, True)

    import subprocess
    try:
        result = subprocess.run(
            ['p4', 'change', '-i'],
            cwd=workspace_dir,
            input='\n'.join(updated_lines),
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print('Failed to update changelist description', file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            return (result.returncode, False)

        return (0, True)

    except Exception as e:
        print(f'Failed to update changelist description: {e}', file=sys.stderr)
        return (1, False)


def review_new_command(args):
    """
    Execute the review new command.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    workspace_dir = ensure_workspace()

    # Create new changelist (reuse logic from edit.py)
    returncode, changelist = create_new_changelist(
        args.base_branch, workspace_dir, dry_run=args.dry_run)
    if returncode != 0:
        print('Failed to create new changelist', file=sys.stderr)
        return returncode

    if args.dry_run:
        print(f"Would create review for changelist: {changelist}")
        return 0

    print(f"Created new changelist: {changelist}")

    # Add #review keyword to changelist description
    returncode, success = p4_add_review_keyword_to_changelist(
        changelist, workspace_dir, dry_run=args.dry_run)
    if not success:
        return returncode

    # Get local git changes and add them to the changelist
    returncode, changes = get_local_git_changes(
        args.base_branch, workspace_dir)
    if returncode != 0:
        print('Failed to get a list of changed files', file=sys.stderr)
        return returncode

    # Process all changes in the changelist
    returncode = include_changes_in_changelist(
        changes, changelist, workspace_dir, args.dry_run)
    if returncode != 0:
        return returncode

    # Shelve the changelist to create the review
    returncode, success = p4_shelve_changelist(
        changelist, workspace_dir, dry_run=args.dry_run)
    if not success:
        return returncode

    print(f"Created Swarm review for changelist {changelist}")
    return 0


def review_update_command(args):
    """
    Execute the review update command.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    workspace_dir = ensure_workspace()

    # Convert changelist string to integer for validation
    try:
        changelist = int(args.changelist)
    except ValueError:
        print('Invalid changelist number: %s' %
              args.changelist, file=sys.stderr)
        return 1

    # Get local git changes (reuse logic from edit.py)
    returncode, changes = get_local_git_changes(
        args.base_branch, workspace_dir)
    if returncode != 0:
        print('Failed to get a list of changed files', file=sys.stderr)
        return returncode

    # Process all changes in the changelist
    returncode = include_changes_in_changelist(
        changes, str(changelist), workspace_dir, args.dry_run)
    if returncode != 0:
        return returncode

    # Re-shelve the changelist to update the review
    returncode, success = p4_shelve_changelist(
        str(changelist), workspace_dir, dry_run=args.dry_run)
    if not success:
        return returncode

    print(f"Updated Swarm review for changelist {changelist}")

    return 0
