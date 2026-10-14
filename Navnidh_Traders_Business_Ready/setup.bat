@echo off
cd /d "%~dp0"
if not exist venv\Scripts\python.exe (
  echo Creating virtual environment...
  python -m venv venv
  if errorlevel 1 goto fail
)
call venv\Scripts\activate
python setup_config.py
if errorlevel 1 goto fail
python -m pip install --upgrade pip
if errorlevel 1 goto fail
python -m pip install -r requirements.txt
if errorlevel 1 goto fail
echo.
echo Setup complete. Run run_both.bat to start both services.
pause
exit /b 0
:fail
echo Setup failed. Read the error above and try again.
pause
exit /b 1
