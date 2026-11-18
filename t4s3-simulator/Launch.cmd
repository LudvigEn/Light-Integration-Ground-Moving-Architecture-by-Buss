@echo off
setlocal
set "SIM_PYTHON_ARGS="
if defined SIM_PYTHON goto run
if exist "%~dp0.venv\Scripts\python.exe" (
    set "SIM_PYTHON=%~dp0.venv\Scripts\python.exe"
    goto run
)
if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
    set "SIM_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    goto run
)
where py >nul 2>&1
if not errorlevel 1 (
    set "SIM_PYTHON=py"
    set "SIM_PYTHON_ARGS=-3"
    goto run
)
set "SIM_PYTHON=python"
:run
"%SIM_PYTHON%" %SIM_PYTHON_ARGS% -c "import sys; assert sys.version_info >= (3, 10), 'Python 3.10 or newer is required'; import tkinter; import PIL"
if errorlevel 1 (
    echo Python 3.10+, Tkinter and Pillow are required. See "%~dp0README.md" for setup.
    pause
    exit /b 1
)
rem Keep the caller's directory so relative image arguments resolve correctly.
"%SIM_PYTHON%" %SIM_PYTHON_ARGS% "%~dp0simulator.py" %*
set "SIM_EXIT=%errorlevel%"
if not "%SIM_EXIT%"=="0" pause
exit /b %SIM_EXIT%
