@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Missing .venv. Create it first:
  echo   python -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)

REM The free model is usually rate-limited. Use the active OpenCode Go model unless
REM the caller explicitly chose another model.
if not defined FILE_ORGANIZER_MODEL set FILE_ORGANIZER_MODEL=opencode-go/deepseek-v4.1-flash
REM Local-folder import is limited to this root. Edit or add roots separated by semicolons.
if not defined FILE_ORGANIZER_SCAN_ROOTS set FILE_ORGANIZER_SCAN_ROOTS=%USERPROFILE%\Pictures
echo Classifier model: %FILE_ORGANIZER_MODEL%
echo Local scan roots: %FILE_ORGANIZER_SCAN_ROOTS%
echo Backend: http://127.0.0.1:8000
echo.

netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul
if not errorlevel 1 (
  echo Port 8000 is already in use. Close the other backend window first.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir backend --reload --port 8000
