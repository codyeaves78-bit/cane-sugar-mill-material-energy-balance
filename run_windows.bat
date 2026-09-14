@echo off
setlocal enabledelayedexpansion

rem Double-click launcher for the Streamlit app on Windows.
rem First run: creates a virtual environment and installs dependencies.
rem Every run after that: just activates the venv and launches the app.

rem Re-launch under "cmd /k" so the window can never just flash and vanish.
rem Double-clicking a .bat normally runs it under "cmd /c", which closes the
rem window the instant the script stops running - including if something
rem (antivirus, a permissions issue, an unexpected crash) kills it before a
rem PAUSE below ever gets a chance to run. /k instead drops to a prompt in
rem the same window when the script ends, so any error stays on screen.
if /I not "%~1"=="RELAUNCHED" (
    cmd /k ""%~f0" RELAUNCHED"
    exit /b
)

rem pushd (not "cd /d") so this still works when the repo lives on a UNC path
rem (a redirected Desktop/Documents folder, e.g. \\server\share\...) - cmd.exe
rem can't cd into a UNC path directly, but pushd maps it to a temp drive letter.
pushd "%~dp0"
if errorlevel 1 (
    echo Could not open the folder this .bat file is in: %~dp0
    echo.
    pause
    exit /b 1
)

if not exist "streamlit_app.py" (
    echo Could not find streamlit_app.py next to this .bat file.
    echo Make sure run_windows.bat stays in the same folder as the rest of the repo.
    echo.
    popd
    pause
    exit /b 1
)

echo Looking for Python...
set "PYCMD="
where py >nul 2>nul
if %errorlevel%==0 (
    set "PYCMD=py -3"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PYCMD=python"
    )
)

if not defined PYCMD (
    echo.
    echo Python was not found on this computer.
    echo Install it from https://www.python.org/downloads/ ^(check "Add python.exe to PATH"
    echo during install^), then double-click this file again.
    echo.
    popd
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating a virtual environment in .venv ^(first run only^)...
    %PYCMD% -m venv .venv
    if not exist ".venv\Scripts\python.exe" (
        echo.
        echo Failed to create the virtual environment. See the error above.
        echo.
        popd
        pause
        exit /b 1
    )
)

echo Installing/updating dependencies ^(this can take a minute on first run^)...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo Failed to install dependencies. Check your internet connection and the error above.
    echo.
    popd
    pause
    exit /b 1
)

echo.
echo Starting the app - a browser tab should open automatically.
echo Close this window (or press Ctrl+C) to stop the app.
echo.
".venv\Scripts\python.exe" -m streamlit run streamlit_app.py

echo.
echo App stopped.
popd
pause
