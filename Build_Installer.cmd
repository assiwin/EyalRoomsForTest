@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title בניית מתקין - אפליקציה לשיבוץ חדרים

echo [1/5] Checking Windows 64-bit...
if /i "%PROCESSOR_ARCHITECTURE%"=="x86" if "%PROCESSOR_ARCHITEW6432%"=="" goto unsupported

echo [2/5] Preparing Python build environment...
set "BUILD_PYTHON="
for /f "usebackq delims=" %%P in (`py -3.12 -c "import sys; print(sys.executable)" 2^>nul`) do set "BUILD_PYTHON=%%P"
if not defined BUILD_PYTHON if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "BUILD_PYTHON=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined BUILD_PYTHON goto no_python
if not exist ".venv\Scripts\python.exe" "%BUILD_PYTHON%" -m venv .venv
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --only-binary=:all: -r requirements.txt pyinstaller==6.16.0
if errorlevel 1 goto fail

echo [3/5] Building the application...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --windowed --name ExamRoomApp --icon "assets\app_icon.ico" --collect-all scipy --collect-all numpy --collect-all reportlab --add-data "web;web" --add-data "assets;assets" app.py
if errorlevel 1 goto fail

echo [4/5] Locating Inno Setup...
set "ISCC_PATH="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC_PATH goto no_inno

echo [5/5] Creating one installer EXE...
"%ISCC_PATH%" installer.iss
if errorlevel 1 goto fail
echo.
echo Ready: installer_output\ExamRoomApp_Setup_v7.exe
echo Test the installer on a clean Windows 10 or 11 64-bit computer before distribution.
pause
exit /b 0

:no_python
echo [ERROR] Python 3.12 64-bit is required only on the build computer.
echo Install it from python.org and run this file again.
pause
exit /b 1

:no_inno
echo [ERROR] Inno Setup 6 is required only on the build computer.
echo Install it from https://jrsoftware.org/isinfo.php and run this file again.
pause
exit /b 1

:unsupported
echo [ERROR] The installer must be built on 64-bit Windows.
pause
exit /b 1

:fail
echo [ERROR] Build failed. Check the message above.
pause
exit /b 1
