@echo off
REM ============================================
REM Aion - Local Deployment Script for Windows
REM Uses relative paths from the script's own location
REM ============================================
setlocal

REM Resolve the project root from this script's directory
set "PROJECT_ROOT=%~dp0"
REM Remove trailing backslash
if "%PROJECT_ROOT:~-1%"=="\" set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"

echo.
echo ========================================
echo    AION - Personal AI System Launcher
echo ========================================
echo.

REM Check if Ollama is running
echo [1/4] Checking Ollama AI Engine...
curl -s http://localhost:11434/api/tags >nul 2>&1
if %ERRORLEVEL% neq 0 (
    where ollama >nul 2>&1
    if %ERRORLEVEL% neq 0 (
        echo WARNING: Ollama not found in PATH. Please install Ollama first.
        echo Download from: https://ollama.com/download
    ) else (
        echo Starting Ollama...
        start /B ollama serve
        timeout /t 3 /nobreak >nul
    )
) else (
    echo Ollama is already running.
)

REM Start Qdrant (via Docker)
echo [2/4] Checking Qdrant Vector Database...
curl -s http://localhost:6333/collections >nul 2>&1
if %ERRORLEVEL% neq 0 (
    where docker >nul 2>&1
    if %ERRORLEVEL% neq 0 (
        echo WARNING: Docker not found in PATH. Please install Docker Desktop first.
        echo Download from: https://www.docker.com/products/docker-desktop/
    ) else (
        echo Starting Qdrant via Docker...
        docker start qdrant 2>nul || docker run -d --name qdrant -p 6333:6333 -p 6334:6334 -v "%USERPROFILE%\.qdrant\storage:/qdrant/storage" qdrant/qdrant
        timeout /t 5 /nobreak >nul
    )
) else (
    echo Qdrant is already running.
)

REM Start Backend
echo [3/4] Starting Aion Backend API...
if not exist "%PROJECT_ROOT%\backend" (
    echo ERROR: Backend directory not found at %PROJECT_ROOT%\backend
    goto :error
)
cd /d "%PROJECT_ROOT%\backend"
if exist ".venv\Scripts\activate.bat" (
    start "Aion Backend" cmd /k ".venv\Scripts\activate.bat && py -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
) else (
    start "Aion Backend" cmd /k "py -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
)
timeout /t 3 /nobreak >nul

REM Start Frontend
echo [4/4] Starting Aion Desktop UI...
if not exist "%PROJECT_ROOT%\desktop" (
    echo ERROR: Desktop directory not found at %PROJECT_ROOT%\desktop
    goto :error
)
cd /d "%PROJECT_ROOT%\desktop"
start "Aion Desktop" cmd /k "npm run tauri:dev"
timeout /t 3 /nobreak >nul

echo.
echo ========================================
echo    AION IS NOW ONLINE!
echo ========================================
echo.
echo Access Points:
echo   Desktop app:  running as an overlay window
echo   Backend API:  http://localhost:8000
echo   API Docs:     http://localhost:8000/docs
echo.
echo Network Access:
echo   Other devices on your network can connect to:
echo   http://YOUR_IP_ADDRESS:8000
echo.
goto :eof

:error
echo.
echo ========================================
echo    STARTUP FAILED - See errors above
echo ========================================
echo.
pause
endlocal
