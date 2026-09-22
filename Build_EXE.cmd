@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Run Start.cmd once to install the application first.
 pause
 exit /b 1
)
.venv\Scripts\python.exe -m pip install pyinstaller==6.16.0
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onedir --windowed --name ExamRoomApp --icon "assets\app_icon.ico" --collect-all scipy --collect-all numpy --collect-all reportlab --add-data "web;web" --add-data "assets;assets" app.py
if errorlevel 1 goto fail
echo Ready: dist\ExamRoomApp\ExamRoomApp.exe
echo Keep the whole dist\ExamRoomApp folder together.
pause
exit /b 0
:fail
echo Build failed. See the message above.
pause
