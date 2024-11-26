#!/bin/bash

if [[ -n "$ZSH_VERSION" ]]; then
    script_dir=$(dirname "$(realpath "$0")")
elif [[ -n "${BASH_SOURCE[0]}" ]]; then
    script_dir=$(dirname "$(realpath "${BASH_SOURCE[0]}")")
else
    echo "Unsupported shell. Please use Bash or Zsh." >&2
    exit 1
fi

root_dir=$(dirname "$script_dir")

sync_local_git_with_p4() {
  local python_script="$root_dir/src/sync_local_git_with_p4.py"
  python3 "$python_script" "$@"
}

edit_local_git_changes_in_p4() {
  local python_script="$root_dir/src/edit_local_git_changes_in_p4.py"
  python3 "$python_script" "$@"
}
