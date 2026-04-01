@echo off
setlocal
set SCRIPT_DIR=%~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\cloudflared_startup_install.ps1" %*
exit /b %ERRORLEVEL%
