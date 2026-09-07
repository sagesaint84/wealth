@echo off
setlocal
chcp 65001 >nul
pushd "%~dp0"
if exist "%~dp0.venv\Scripts\python.exe" goto start_dashboard
echo Setup is required before starting the dashboard.
echo Please follow the installation steps in README.md.
pause
popd
exit /b 1

:start_dashboard
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:4829/dashboard?rev=8'"
"%~dp0.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 4829 --reload
popd
