@echo off
echo ========================================================
echo   KWR - Keyword Research Intelligence Suite
echo ========================================================
echo.
echo [*] Checking and installing dependencies...
pip install -r requirements.txt
echo.
echo [*] Starting Web Command Center...
python kwr.py start
pause
