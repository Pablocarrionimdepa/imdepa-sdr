@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "PORT=9095"

set "ENV_FILE=.env"
if not exist "%ENV_FILE%" (
    if exist ".env.example" (
        set "ENV_FILE=.env.example"
        echo Warning: using .env.example
    ) else (
        echo Missing .env file in project root.
        echo Create it from .env.example and set OPENAI_API_KEY.
        exit /b 1
    )
)

for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
    set "K=%%A"
    set "V=%%B"
    if defined K if not "!K:~0,1!"=="#" (
        if "!V:~0,1!"=="\"" if "!V:~-1!"=="\"" set "V=!V:~1,-1!"
        set "!K!=!V!"
    )
)

set "PYTHONIOENCODING=utf-8"

if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Starting server on http://127.0.0.1:%PORT%/
echo Press Ctrl+C to stop in this terminal, or use stop_server.bat in another terminal.
"%PYTHON_EXE%" -m uvicorn app:app --host 0.0.0.0 --port %PORT%

exit /b %errorlevel%
