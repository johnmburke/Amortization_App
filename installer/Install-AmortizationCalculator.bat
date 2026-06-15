@echo off
title Amortization Calculator Installer
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
echo.
echo Installer finished with exit code %ERRORLEVEL%.
echo.
pause
