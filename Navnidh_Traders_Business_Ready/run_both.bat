@echo off
cd /d "%~dp0"
if not exist venv\Scripts\python.exe call setup.bat
if not exist customer\.env python setup_config.py
if not exist admin\.env python setup_config.py
if not exist venv\Scripts\python.exe exit /b 1
echo Starting Customer website on http://127.0.0.1:5000 ...
start "Navnidh CUSTOMER (5000)" cmd /k "cd /d %~dp0customer && ..\venv\Scripts\python.exe app.py"
timeout /t 6 /nobreak >nul
echo Starting Admin panel on http://127.0.0.1:5001 ...
start "Navnidh ADMIN (5001)" cmd /k "cd /d %~dp0admin && ..\venv\Scripts\python.exe app.py"
timeout /t 4 /nobreak >nul
start http://127.0.0.1:5000
start http://127.0.0.1:5001/login
