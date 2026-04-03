@echo off
echo ============================================
echo  ProcessAuth - Starting up...
echo ============================================
cd /d "%~dp0"
python main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Application exited with code %ERRORLEVEL%
    pause
)
