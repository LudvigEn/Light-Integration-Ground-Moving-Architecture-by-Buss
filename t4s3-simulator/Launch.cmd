@echo off
setlocal
cd /d "%~dp0"
set "SIM_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%SIM_PYTHON%" (
    "%SIM_PYTHON%" simulator.py %*
) else (
    py -3 simulator.py %*
)
if errorlevel 1 pause
