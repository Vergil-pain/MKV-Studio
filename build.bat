@echo off
REM Run the app or create a portable build.
setlocal EnableExtensions
cd /d "%~dp0"
title MKV Studio

if /i "%~1"=="run" goto run
if /i "%~1"=="build" goto build

:menu
cls
echo.
echo  MKV Studio
echo.
echo  [1] Run the app
echo  [2] Build the Windows app
echo  [Q] Quit
echo.
choice /c 12Q /n /m "Choose an option: "
if errorlevel 3 exit /b 0
if errorlevel 2 goto menu_build
goto menu_run

:menu_build
set "ACTION=2"
goto build

:menu_run
set "ACTION=1"
goto run

:python_check
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if defined PY goto have_python
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY goto have_python

echo.
echo  Python 3.10 or newer was not found.
echo  Install Python from https://www.python.org/downloads/ and enable PATH.
echo.
pause
exit /b 1

:have_python
if exist ".venv\Scripts\python.exe" goto have_venv
echo Creating the project environment...
%PY% -m venv .venv
if errorlevel 1 goto fail

:have_venv
set "VPY=.venv\Scripts\python.exe"
REM Remove the full PySide6 package if its optional Addons are installed.
"%VPY%" -m pip show PySide6-Addons >nul 2>&1
if errorlevel 1 goto runtime_check
echo Replacing the old full PySide6 environment with the smaller Essentials version...
rmdir /s /q .venv
%PY% -m venv .venv
if errorlevel 1 goto fail
set "VPY=.venv\Scripts\python.exe"

:runtime_check
"%VPY%" -c "from PySide6.QtWidgets import QApplication" >nul 2>&1
if not errorlevel 1 goto runtime_ready

echo Installing the smaller PySide6 Essentials runtime...
"%VPY%" -m pip install -r requirements.txt
if errorlevel 1 goto fail

:runtime_ready
if /i "%~1"=="build" goto do_build
if /i "%~1"=="run" goto do_run
if not "%ACTION%"=="" goto dispatch

goto menu

:dispatch
if /i "%ACTION%"=="1" goto do_run
if /i "%ACTION%"=="2" goto do_build
goto menu

:run
goto python_check

:build
goto python_check

:do_run
echo Starting MKV Studio...
"%VPY%" -c "import ui"
if errorlevel 1 goto fail
start "" ".venv\Scripts\pythonw.exe" main.py
exit /b 0

:do_build
"%VPY%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    "%VPY%" -m pip install pyinstaller
    if errorlevel 1 goto fail
)

echo Building MKV Studio...
"%VPY%" -m PyInstaller --noconfirm --clean --windowed --onedir --optimize 2 --name "MKV Studio" --icon "icon.ico" --version-file "version_info.txt" --exclude-module pytest main.py
if errorlevel 1 goto fail

REM Include only the FFmpeg executables and DLLs.
if exist "ffmpeg\ffmpeg.exe" if exist "ffmpeg\ffprobe.exe" (
    if not exist "dist\MKV Studio\ffmpeg" mkdir "dist\MKV Studio\ffmpeg"
    copy /y "ffmpeg\ffmpeg.exe" "dist\MKV Studio\ffmpeg\" >nul
    copy /y "ffmpeg\ffprobe.exe" "dist\MKV Studio\ffmpeg\" >nul
    for %%F in ("ffmpeg\*.dll") do if exist "%%~fF" copy /y "%%~fF" "dist\MKV Studio\ffmpeg\" >nul
    echo Bundled FFmpeg executables and DLLs.
) else (
    echo FFmpeg was not bundled. The app will look for FFmpeg on PATH or in its FFmpeg settings.
)

echo.
echo  Build complete: dist\MKV Studio\MKV Studio.exe
echo  Zip the contents of "dist\MKV Studio" for a GitHub Release.
echo.
pause
exit /b 0

:fail
echo.
echo  The operation failed. Read the error messages above.
echo.
pause
exit /b 1
