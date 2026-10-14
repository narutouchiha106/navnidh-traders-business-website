@echo off
cd /d "%~dp0"
if not exist venv\Scripts\python.exe call setup.bat
if not exist admin\.env python setup_config.py
cd /d "%~dp0admin"
..\venv\Scripts\python.exe app.py
pause
