function Edit-LocalGitChangesInP4 {
	param (
		[Parameter(ValueFromRemainingArguments=$true)]
		$Args
	)
	$bin_dir = $PSScriptRoot
	$root_dir = (Split-Path -Path $bin_dir -Parent)
	$python_script = (Join-Path -Path "$root_dir" -ChildPath "src/edit_local_git_changes_in_p4.py")

	& python.exe $python_script $Args
}

function Sync-LocalGitWithP4 {
	param (
		[Parameter(ValueFromRemainingArguments=$true)]
		$Args
	)
	$bin_dir = $PSScriptRoot
	$root_dir = (Split-Path -Path $bin_dir -Parent)
	$python_script = (Join-Path -Path "$root_dir" -ChildPath "src/sync_local_git_with_p4.py")

	& python.exe $python_script $Args
}
