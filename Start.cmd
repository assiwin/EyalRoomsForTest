@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title Exam Room App

echo ================================================
echo   Exam Room App - automatic setup and startup
echo ================================================
echo.

if /i "%PROCESSOR_ARCHITECTURE%"=="x86" if "%PROCESSOR_ARCHITEW6432%"=="" goto unsupported_32bit

if exist ".venv\Scripts\python.exe" if exist ".venv\.ready" goto run

echo [1/4] Checking Python 3.12...
call :find_python
if defined APP_PYTHON goto create_venv

echo [2/4] Python is missing. Installing it automatically...
where winget >nul 2>&1
if errorlevel 1 goto official_installer

winget install --exact --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
call :find_python
if defined APP_PYTHON goto create_venv

:official_installer
echo Downloading the official Python installer...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $url='https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe'; $file=Join-Path $env:TEMP 'python-3.12.10-amd64.exe'; Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $file; $signature=Get-AuthenticodeSignature $file; if($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notlike '*Python Software Foundation*'){ throw 'The Python installer digital signature is not valid.' }; $process=Start-Process -FilePath $file -ArgumentList '/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1 Include_test=0' -Wait -PassThru; if($process.ExitCode -ne 0){ throw ('Python installer exit code: ' + $process.ExitCode) }; Remove-Item $file -Force"
if errorlevel 1 goto install_failed

call :find_python
if not defined APP_PYTHON goto install_failed

:create_venv
if exist ".venv\Scripts\python.exe" goto install_libraries
echo [3/4] Creating the application environment...
"%APP_PYTHON%" -m venv .venv
if errorlevel 1 goto fail
if not exist ".venv\Scripts\python.exe" goto fail

:install_libraries
echo [4/4] Installing calculation libraries...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --only-binary=:all: -r requirements.txt
if errorlevel 1 goto fail
type nul > ".venv\.ready"

:run
echo.
echo Opening the application. Keep this window open while working.
echo You can close this window when you finish.
".venv\Scripts\python.exe" app.py
if errorlevel 1 goto fail
exit /b 0

:find_python
set "APP_PYTHON="
for /f "usebackq delims=" %%P in (`py -3.12 -c "import sys; print(sys.executable)" 2^>nul`) do set "APP_PYTHON=%%P"
if defined APP_PYTHON goto :eof
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "APP_PYTHON=%LocalAppData%\Programs\Python\Python312\python.exe"
if defined APP_PYTHON goto :eof
for /d %%D in ("%LocalAppData%\Programs\Python\Python312*") do if exist "%%~fD\python.exe" set "APP_PYTHON=%%~fD\python.exe"
if defined APP_PYTHON goto :eof
if exist "%ProgramFiles%\Python312\python.exe" set "APP_PYTHON=%ProgramFiles%\Python312\python.exe"
goto :eof

:unsupported_32bit
echo [ERROR] This computer uses 32-bit Windows.
echo The calculation engine requires 64-bit Windows.
echo Use the web version, or install 64-bit Windows on compatible hardware.
pause
exit /b 1

:install_failed
echo.
echo [ERROR] Automatic Python installation did not complete.
echo Ask the computer administrator to allow Python installation,
echo and then run Start.cmd again.
pause
exit /b 1

:fail
echo.
echo [ERROR] Setup or startup did not complete.
echo Check the message above or send a photo of this window for support.
pause
exit /b 1
