@echo off
setlocal

set SCRIPT_DIR=%~dp0
set ROOT_DIR=%SCRIPT_DIR%..

echo === CBL Maker — Windows Build ===

REM Ensure PyInstaller is installed
python -m pip install --quiet pyinstaller

REM Clean previous build
if exist "%ROOT_DIR%\build\cbl-maker" rmdir /s /q "%ROOT_DIR%\build\cbl-maker"
if exist "%ROOT_DIR%\dist\cbl-maker.exe" del /q "%ROOT_DIR%\dist\cbl-maker.exe"

REM Build
pyinstaller "%SCRIPT_DIR%cbl-maker.spec" --clean --noconfirm

REM Verify
if not exist "%ROOT_DIR%\dist\cbl-maker.exe" (
    echo ERROR: dist\cbl-maker.exe not found >&2
    exit /b 1
)

echo OK: dist\cbl-maker.exe
