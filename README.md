# pergit

A tool for managing a local git repository within a Perforce workspace.

The idea is to have a `main` branch that is kept in sync with the Perforce depot.
From `main` you branch out into feature branches, where you do local
changes and rebase on `main` whenever it is updated.

This is a bit cumbersome to do manually, but this package provides commands
that help out with the repetitive and error prone stuff.

## Installation

Currently, pergit must be installed from source. Clone the repository and install:

```sh
git clone https://github.com/derwiath/pergit.git
cd pergit
pip install .
```

Or install in development mode:

```sh
git clone https://github.com/derwiath/pergit.git
cd pergit
pip install -e .
```

## Development

To contribute to pergit or modify it for your needs, you can install it in development mode:

```sh
git clone https://github.com/derwiath/pergit.git
cd pergit
pip install -e .
```

The `-e` flag installs the package in "editable" mode. Which means that changes
to the code are immediately available and `pergit` can be tested right
away without reinstalling.

### Development Requirements

pergit only uses Python standard library modules, no additional packages are required.

## Setup

### Perforce workspace
* Set clobber flag on your perforce workspace.
* Sync workspace to a specified changelist
```sh
p4 sync //...@123
```
  Take note of the changelist number.

### Local git repo
* Initialize a local git repo:
```sh
git init
```
  It does not have to be in the root of your perforce workspace, you may choose to only
  keep a part of it in your local git repo.
* Add a `.gitignore` file and commit.
  Ideally your ignore file should ignore the same files that is ignored
  by perforce.
* Add all files and commit
```sh
git add .
git commit -m "Initial commit for CL 123"
```

## Usage

pergit provides three main commands: `sync`, `edit`, and `list-changes`.

### Sync Command

Sync local git repository with a Perforce workspace:

```sh
pergit sync <changelist> [--force]
```

**Arguments:**
- `changelist`: Changelist to sync

**Options:**
- `-f, --force`: Force sync encountered writable files. When clobber is not enabled on your workspace, p4 will fail to sync files that are read-only. git removes the readonly flag on touched files.

**Examples:**
```sh
pergit sync 12345
pergit sync 12345 --force
```

### Edit Command

Find files that have changed between your current git `HEAD` and the base branch, and open them for edit in Perforce:

```sh
pergit edit <changelist> [--base-branch BASE_BRANCH] [--dry-run]
```

**Arguments:**
- `changelist`: Changelist to update

**Options:**
- `-b, --base-branch BASE_BRANCH`: Base branch where p4 and git are in sync. Default is `HEAD~1`.
- `-n, --dry-run`: Pretend and print all commands, but do not execute

**Examples:**
```sh
pergit edit 12345
pergit edit 12345 --base-branch main
pergit edit 12345 --dry-run
```

### List-Changes Command

List commit subjects since a base branch in chronological order (oldest first):

```sh
pergit list-changes [--base-branch BASE_BRANCH]
```

**Options:**
- `-b, --base-branch BASE_BRANCH`: Base branch to compare against. Default is `HEAD~1`.

**Examples:**
```sh
pergit list-changes
pergit list-changes --base-branch main
```

This command is useful for generating changelist descriptions by listing all commit messages since the base branch, numbered sequentially.

## Usage Example

Here's a typical workflow using pergit:

```sh
# Sync main with new changes from perforce, CL 124
git checkout main
pergit sync 124

# Start work on a new feature
git checkout -b my-fancy-feature

# Change some code
git add .
git commit -m "Feature part1"

# Sync latest from perforce
git checkout main
pergit sync 125

# Rebase your changes on main
git checkout my-fancy-feature
git rebase main

# Change even more code
git add .
git commit -m "Feature part2"

# List all commit messages since main branch (useful for changelist description)
pergit list-changes --base-branch main

# Open all edited files on your feature branch (compared to main) for edit in perforce
# Store all files in changelist 126
pergit edit 126 --base-branch main

# Swap over to p4v and submit as CL 126

# Sync latest from perforce
git checkout main
pergit sync 126

# Remove old branch as you don't need it anymore
git branch -D my-fancy-feature

# Start working on the next feature
git checkout -b my-next-fancy-feature
```
