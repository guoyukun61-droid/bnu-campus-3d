@echo off
chcp 65001 >nul
powershell.exe -NoProfile -File "%~dp0start_viewer.ps1" -Edition white
