@echo off
REM GridWise Live Demo Launcher - BUP CSE Fest 2026
echo ===================================================
echo   Starting GridWise Smart Campus Energy Optimizer
echo ===================================================

REM Check Python
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not on PATH.
    pause
    exit /b 1
)

echo [1/2] Launching FastAPI server on http://0.0.0.0:8000...
start "GridWise Server" cmd /k "python -m uvicorn main:app --host 0.0.0.0 --port 8000"

timeout /t 3 >nul

echo [2/2] Launching Cloudflare Quick Tunnel...
cloudflared --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    start "Cloudflare Tunnel" cmd /k "cloudflared tunnel --url http://localhost:8000"
    echo Cloudflare Quick Tunnel launched. Check tunnel window for public URL.
) else (
    echo [WARNING] cloudflared is not installed or not on PATH.
    echo Local API is running at http://localhost:8000
)

echo.
echo ===================================================
echo   GridWise service is starting up!
echo   Health Check: http://localhost:8000/health
echo   Run Tests:    python test_runner.py
echo ===================================================
