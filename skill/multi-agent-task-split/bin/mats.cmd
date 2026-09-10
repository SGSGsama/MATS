@echo off
setlocal
set "SKILL=%~dp0.."
set "PY=%SKILL%\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo MATS_NOT_INSTALLED: ask the user to run the package installer 1>&2
  exit /b 127
)
"%PY%" -I -B -X utf8 "%SKILL%\scripts\mats.py" %*
exit /b %ERRORLEVEL%
