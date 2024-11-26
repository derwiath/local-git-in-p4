# local-git-in-p4
Utility scripts for managing a local git repository within a perforce workspace.

The idea is to have a `main` branch is keept in sync with the perforce depot.
From the `main` you branch out feature branches, where you do your local
changes, rebase on `main` whenever it is updated.
This is a bit cumbersome to do manually, but this repo contains scripts
that help out with the repetitive and error prone stuff.

## Setup

### Perforce workspace
* Set clobber flag on your perforce workspace.
* Sync workspace to a specified changelist
```
p4 sync //...@123
```
  Take note of the changelist number.

### Local git repo
* Initialize a repo somewhere `git init`
  It does not have to be in the root of your perforce workspace.
* Add a `.gitignore` file and commit
  Ideally your ignore file should ignore the same files that is ignored
  by perforce.
* Add all files and commit
```sh
git add .
git commit -m "Initial commit for CL 123"
```

### Shell integration

The scripts are implemented in python that can be used as is by passing them
to the python executable.

For convenience there is also wrappers for Powershell and unix shells that figures
out where the scripts are stored, and start them with python for you.

#### Sh/Bash/Zsh
Source convenience wrapper functions in your profile.
```sh
source . $(PathToThisRepoRoot)/sh/local_git_in_p4.sh
```
This creates two functions: `sync_local_git_with_p4` and `edit_local_git_changes_in_p4`

#### Powershell
Import convenience wrapper commands in your Powershell user profile, find out where with `echo $PROFILE`.
```ps
. $(PathToThisRepoRoot)/ps1/LocalGitInP4.ps1
```
Creates two commands: `Sync-LocalGitWithP4` and `Edit-LocalGitChangesInP4`

## Usage example

### Zsh/Bash/Sh
```sh
# Sync main with new changes from perforce, CL 124
git checkout main
sync_local_git_with_p4 124

# Start work on a new feature
git checkout -b my-fancy-feature

# Change some code
git add .
git commit -m "Feature part1"

# Sync latest from perforce
git checkout main
sync_local_git_with_p4 125

# Rebase your changes on main
git checkout my-fancy-feature
git rebase main

# Change even more code
git add .
git commit -m "Feature part2"

# Open all edited files on your feature branch for edit in perforce
edit_local_git_changes_in_p4

# Swap over to p4v and submit as CL 126

# Sync latest from perforce
git checkout main
sync_local_git_with_p4 126

# Start working on the next feature
git checkout -b my-next-fancy-feature

```


