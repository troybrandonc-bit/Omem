# omem-git.ps1 — safe push of the OMEM infrastructure to a new GitHub repo.
# Run from inside the omem-infrastructure folder (or pass -Path).
# It refuses to commit secrets or databases, so you can't accidentally publish them.

param(
  [string]$Path = ".",
  [string]$RepoUrl = "",
  [string]$CommitMessage = "Initial commit: OMEM agent memory infrastructure"
)

$ErrorActionPreference = "Stop"
Set-Location $Path

# 0. git installed?
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  Write-Host "ERROR: git is not installed. Install from https://git-scm.com/ (or use GitHub Desktop)." -ForegroundColor Red
  exit 1
}

# 1. init (safe to re-run)
if (-not (Test-Path ".git")) {
  git init | Out-Null
  git branch -M main
  Write-Host "Initialized empty git repo." -ForegroundColor Green
} else {
  Write-Host "Existing git repo detected; continuing." -ForegroundColor Yellow
}

# 2. stage everything (respects .gitignore)
git add .

# 3. SAFETY GATE: refuse to commit secrets / databases / build junk.
$staged = git diff --cached --name-only
$danger = $staged | Where-Object {
  $_ -match '(^|/)\.env$' -or
  $_ -match '\.env\.' -and $_ -notmatch '\.env\.example$' -or
  $_ -match '\.db$' -or $_ -match '\.db-' -or
  $_ -match '\.key$' -or $_ -match '\.pem$'
}
if ($danger) {
  Write-Host ""
  Write-Host "STOP: these staged files look like secrets or data and must NOT be pushed:" -ForegroundColor Red
  $danger | ForEach-Object { Write-Host "   $_" -ForegroundColor Red }
  Write-Host "Aborting. Remove them (or fix .gitignore) and re-run." -ForegroundColor Red
  exit 1
}
Write-Host "Safety check passed: no secrets or databases staged." -ForegroundColor Green

# 4. show what WILL be committed and pause for a human look
Write-Host ""
Write-Host "About to commit these files:" -ForegroundColor Cyan
git diff --cached --name-only
Write-Host ""
$ok = Read-Host "Look right? Type 'yes' to commit and push"
if ($ok -ne "yes") { Write-Host "Cancelled. Nothing pushed." -ForegroundColor Yellow; exit 0 }

# 5. commit
git commit -m "$CommitMessage" | Out-Null
Write-Host "Committed." -ForegroundColor Green

# 6. remote + push
if (-not $RepoUrl) {
  Write-Host ""
  Write-Host "Create an EMPTY repo on github.com first (no README/license/gitignore)," -ForegroundColor Cyan
  Write-Host "then paste its URL below (e.g. https://github.com/you/omem.git)." -ForegroundColor Cyan
  $RepoUrl = Read-Host "Repo URL"
}
if (-not $RepoUrl) { Write-Host "No URL given; committed locally but not pushed." -ForegroundColor Yellow; exit 0 }

if (git remote | Select-String -Quiet "^origin$") {
  git remote set-url origin $RepoUrl
} else {
  git remote add origin $RepoUrl
}

Write-Host ""
Write-Host "Pushing... (GitHub will ask for auth: use a Personal Access Token as the password —" -ForegroundColor Cyan
Write-Host "github.com -> Settings -> Developer settings -> Personal access tokens, 'repo' scope.)" -ForegroundColor Cyan
git push -u origin main

Write-Host ""
Write-Host "Done. Your repo is live at: $RepoUrl" -ForegroundColor Green
