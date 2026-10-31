@echo off
cd /d "%~dp0"
python palette_lab_gui.py %*
if errorlevel 1 pause
