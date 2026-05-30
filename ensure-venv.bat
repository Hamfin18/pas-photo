@echo off
if exist ".venv\Scripts\uvicorn.exe" exit /b 0

echo [pas-foto] Setup pertama kali, install dependency...
python -m venv .venv
if errorlevel 1 (
    echo Gagal: Python tidak ketemu. Install Python dulu dari python.org
    exit /b 1
)
.venv\Scripts\pip install -r requirements.txt
if errorlevel 1 (
    echo Gagal install dependency.
    exit /b 1
)
exit /b 0
