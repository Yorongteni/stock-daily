@echo off
cd /d "%~dp0"
set PY=python
python --version >nul 2>&1
if errorlevel 1 set PY=py
echo Python:
%PY% --version
echo.
echo Running main.py ...
%PY% main.py --open
echo.
echo ==== Finished. Copy the messages above if something went wrong. ====
pause
