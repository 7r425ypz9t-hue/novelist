@echo off
rem Puts the Kateb icon on the Desktop and in the Start menu, then shows the result.
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" -CreateShortcut
pause
