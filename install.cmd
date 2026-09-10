@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "INSTALLER=%~dp0installer\install.py"

where uv >nul 2>&1
if not errorlevel 1 goto run_uv

where py >nul 2>&1
if not errorlevel 1 goto run_py

where python >nul 2>&1
if not errorlevel 1 goto run_python

echo MATS_INSTALL_ERROR: Python 3.10+ or uv is required. 1>&2
exit /b 2

:run_py
py -3 "%INSTALLER%" %*
exit /b %ERRORLEVEL%

:run_python
python "%INSTALLER%" %*
exit /b %ERRORLEVEL%

:run_uv
uv run --no-project python "%INSTALLER%" %*
exit /b %ERRORLEVEL%
