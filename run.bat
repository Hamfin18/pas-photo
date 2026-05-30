@echo off
cd /d "%~dp0"
call ensure-venv.bat
if errorlevel 1 pause & exit /b 1

set APP_ENV=development

echo.
echo [pas-foto] DEV - http://localhost:8000
echo Auto-reload aktif. Tutup jendela ini untuk stop.
echo.
start "" "http://localhost:8000"
.venv\Scripts\uvicorn.exe app.main:app --reload --host 127.0.0.1 --port 8000
pause
