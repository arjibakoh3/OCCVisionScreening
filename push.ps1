param(
  [string]$Message = "auto update"
)

$ErrorActionPreference = "Stop"

# Ensure git is available
$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) { throw "git not found in PATH" }

# Show status
$status = git status --porcelain
if (-not $status) {
  Write-Host "No changes to commit."
  exit 0
}

# Stage all changes
& git add -A

# Commit
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm"
$commitMsg = if ($Message -and $Message.Trim().Length -gt 0) { $Message } else { "update $timestamp" }
& git commit -m $commitMsg

# Push
& git push
Write-Host "Pushed successfully."
