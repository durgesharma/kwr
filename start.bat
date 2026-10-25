@echo off
cd /d "%~dp0"
echo ========================================================
echo   KWR - Keyword Research Intelligence Suite
echo ========================================================
echo.
echo [*] Checking and installing dependencies...
python -m pip install -r requirements.txt 2>nul || python -m pip install flask requests
echo.
echo [*] Starting Web Command Center...
python kwr.py start
pause
