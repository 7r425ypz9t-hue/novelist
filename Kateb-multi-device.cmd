@echo off
rem Kateb for several computers: reachable from your other machines on the network.
rem Create your account first with Kateb.cmd, then use this one.
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" -Lan %*
if errorlevel 1 pause
