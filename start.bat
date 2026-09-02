@echo off
cd /d "%~dp0"
if "%~1"=="" (python -m yesir --web) else (python -m yesir %*)
