@echo off
setlocal
cd /d "%~dp0"
set PYTHONDONTWRITEBYTECODE=1
if not defined PAPERRULE_MEMORY set "PAPERRULE_MEMORY=%~dp0../paperrule-private-memory"
where git.exe >nul 2>&1
if errorlevel 1 (
  echo Git for Windows is required. Install it and then reopen PaperRule.
  goto failed
)
if exist ".venv/Scripts/paperrule.exe" goto launch
if not exist "wheels/paperrule-0.1.0-py3-none-any.whl" (
  echo Installation files were not found. Extract the entire Windows ZIP, or follow docs/installation.md for a source install.
  goto failed
)
echo Setting up PaperRule. This may take a minute.
if not exist .setup-tmp mkdir .setup-tmp
if errorlevel 1 goto failed
set "TEMP=%CD%/.setup-tmp"
set "TMP=%TEMP%"
call :createVenv
if errorlevel 1 (
  echo Python 3.12 x64 is required. Install it or set PAPERRULE_PYTHON to its python.exe.
  goto failed
)
".venv/Scripts/python.exe" -B -m pip --disable-pip-version-check --no-cache-dir install --no-index --find-links wheels "paperrule==0.1.0"
if errorlevel 1 goto failed
:launch
if /I "%~1"=="--install-only" exit /b 0
".venv/Scripts/paperrule.exe" app --open
if errorlevel 1 goto failed
exit /b 0
:failed
echo PaperRule could not start. See the message above before trying again.
pause
exit /b 1

:createVenv
if defined PAPERRULE_PYTHON goto customPython
py -3.12-64 -B -m venv .venv
if not errorlevel 1 exit /b 0
set PAPERRULE_PYTHON=python
:customPython
"%PAPERRULE_PYTHON%" -B -c "import struct,sys; sys.exit(sys.version_info[:2] != (3,12) or struct.calcsize('P') != 8)"
if errorlevel 1 exit /b 1
"%PAPERRULE_PYTHON%" -B -m venv .venv
exit /b %ERRORLEVEL%
