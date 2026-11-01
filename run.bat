@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creating a local Python environment...
  python -m venv .venv
  if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
echo.
echo Open http://127.0.0.1:8000 in your browser.
echo Press Ctrl+C to stop NetCoop.
".venv\Scripts\python.exe" -m uvicorn server:app --host 127.0.0.1 --port 8000
goto end
:fail
echo Setup failed. Install Python 3.11 or newer and check your internet connection.
pause
:end
