@echo off
setlocal
cd /d "%~dp0"

set "PORT=9095"
set "FOUND=0"

for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
    taskkill /PID %%P /T /F >nul 2>&1
    if not errorlevel 1 (
        echo Stopped PID %%P listening on port %PORT%.
        set "FOUND=1"
    )
)

if "%FOUND%"=="0" (
    echo No running server found on port %PORT%.
) else (
    echo Server stopped.
)

exit /b 0
