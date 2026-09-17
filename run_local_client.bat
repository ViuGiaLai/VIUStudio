@echo off
setlocal
cd /d "%~dp0"

echo [VIUStudio] Starting local client...
if exist "%~dp0venv\Scripts\pythonw.exe" (
    start "" "%~dp0venv\Scripts\pythonw.exe" ui\gui.py
    exit /b 0
) else if exist "%~dp0venv\Scripts\python.exe" (
    "%~dp0venv\Scripts\python.exe" ui\gui.py
) else (
    pythonw ui\gui.py 2>nul || python ui\gui.py
)

if errorlevel 1 (
    echo.
    echo [VIUStudio] Local client exited with an error.
    pause
)
