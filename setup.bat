@echo off
cd /d "%~dp0"
echo === Domain Expansion setup ===
where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Install Python 3.10 or newer from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" during installation, then run this again.
    pause
    exit /b 1
)
if not exist .venv\Scripts\python.exe (
    echo Creating virtual environment...
    python -m venv .venv || goto :fail
)
echo Installing packages, this can take a few minutes...
.venv\Scripts\python.exe -m pip install --upgrade pip || goto :fail
.venv\Scripts\python.exe -m pip install -r requirements.txt || goto :fail
echo Downloading hand tracking models...
.venv\Scripts\python.exe setup_models.py || goto :fail
echo.
echo Setup complete. Put your video in the "videos" folder, then double-click run.bat.
pause
exit /b 0

:fail
echo.
echo Setup failed. Read the error above, or see Troubleshooting in README.md.
pause
exit /b 1
