@echo off
setlocal
cd /d "%~dp0frontend"

if not exist "node_modules" (
  echo Installing frontend dependencies...
  call npm install
  if errorlevel 1 (
    echo npm install failed.
    pause
    exit /b 1
  )
)

echo Frontend: http://localhost:5173
echo Keep the backend window running too.
echo.
call npm run dev
