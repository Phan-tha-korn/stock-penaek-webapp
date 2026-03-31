@echo off
setlocal
set SCRIPT_DIR=%~dp0
echo Running installer...
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\backend_autostart_install.ps1" %*
echo.
echo Done. Press any key to close.
pause >nul
exit /b %ERRORLEVEL%
