@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Setup has not been run yet. Double-click setup.bat first.
    pause
    exit /b 1
)
set SIGN=%~1
if "%SIGN%"=="" set /p SIGN=Name of the sign to teach (for example mute or idle_death_gamble): 
.venv\Scripts\python.exe record_samples.py --sign "%SIGN%"
pause