@echo off
setlocal
set "SCRIPT_DIR=%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%launcher.ps1"

if errorlevel 1 (
    echo.
    echo Something went wrong above - scroll up to read the error message.
    echo.
)

pause
