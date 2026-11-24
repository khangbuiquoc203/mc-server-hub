@echo off
setlocal
cd /d "%~dp0"

python -m pip install -r requirements-dev.txt
if errorlevel 1 exit /b 1

python -m PyInstaller --noconfirm --clean --onedir --windowed --name MCServerHub --paths . --collect-submodules mc_server_hub --collect-all winpty --hidden-import psutil mc_server_hub\main.py
if errorlevel 1 exit /b 1

if not exist "dist\MCServerHub\config" mkdir "dist\MCServerHub\config"
if not exist "dist\MCServerHub\config\servers.json" copy /Y "config\servers.json" "dist\MCServerHub\config\servers.json"
if not exist "dist\MCServerHub\config\settings.json" copy /Y "config\settings.json" "dist\MCServerHub\config\settings.json"
if not exist "dist\MCServerHub\logs" mkdir "dist\MCServerHub\logs"

echo.
echo Built dist\MCServerHub\MCServerHub.exe
exit /b 0
