@echo off
cd /d "%~dp0"
if not exist venv\Scripts\python.exe call setup.bat
if not exist customer\.env python setup_config.py
cd /d "%~dp0customer"
..\venv\Scripts\python.exe app.py
pause
