@echo off
setlocal enabledelayedexpansion

REM Safe auto-update: commit -> pull --rebase -> push

cd /d "%~dp0"

echo.
echo [1/6] Checking git availability...
git --version >nul 2>nul
if errorlevel 1 (
  echo Git not found in PATH.
  exit /b 1
)

echo.
echo [2/6] Checking repository status...
for /f %%b in ('git branch --show-current') do set BRANCH=%%b
if "%BRANCH%"=="" (
  echo Could not detect current branch.
  exit /b 1
)
echo Branch: %BRANCH%

git remote get-url origin >nul 2>nul
if errorlevel 1 (
  echo Remote "origin" not configured.
  exit /b 1
)

echo.
echo [3/6] Staging changes...
git add -A

echo.
echo [4/6] Committing (if needed)...
git diff --cached --quiet
if errorlevel 1 (
  set MSG=auto update %date% %time%
  git commit -m "!MSG!"
  if errorlevel 1 (
    echo Commit failed. Resolve issues and try again.
    exit /b 1
  )
) else (
  echo No staged changes to commit.
)

echo.
echo [5/6] Pulling with rebase...
git pull --rebase origin %BRANCH%
if errorlevel 1 (
  echo.
  echo Rebase failed. Fix conflicts, then run:
  echo   git rebase --continue
  echo or:
  echo   git rebase --abort
  exit /b 1
)

echo.
echo [6/6] Pushing to origin/%BRANCH%...
git push origin %BRANCH%
if errorlevel 1 (
  echo Push failed.
  exit /b 1
)

echo.
echo Done. Current HEAD:
git log -n 1 --oneline --decorate

echo.
echo Streamlit Cloud: click Reboot / Redeploy (or Clear cache + Reboot).
exit /b 0
