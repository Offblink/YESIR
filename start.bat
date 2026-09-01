@echo off
cd /d "%~dp0"
if "%~1"=="" (python -m oksir --web) else (python -m oksir %*)
