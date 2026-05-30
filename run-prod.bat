@echo off
cd /d "%~dp0"
call ensure-venv.bat
if errorlevel 1 pause & exit /b 1

set APP_ENV=production

echo.
echo [pas-foto] PRODUCTION - http://0.0.0.0:8000
echo Tanpa auto-reload. Tutup jendela ini untuk stop.
echo.
.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000
pause
