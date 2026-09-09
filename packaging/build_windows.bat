@echo off
setlocal

set SCRIPT_DIR=%~dp0
set ROOT_DIR=%SCRIPT_DIR%..

echo === ComicDesk — Windows Build ===

REM Ensure PyInstaller is installed
python -m pip install --quiet pyinstaller

REM Clean previous build
if exist "%ROOT_DIR%\build\comicdesk" rmdir /s /q "%ROOT_DIR%\build\comicdesk"
if exist "%ROOT_DIR%\dist\comicdesk.exe" del /q "%ROOT_DIR%\dist\comicdesk.exe"

REM Build
pyinstaller "%SCRIPT_DIR%comicdesk.spec" --clean --noconfirm

REM Verify
if not exist "%ROOT_DIR%\dist\comicdesk.exe" (
    echo ERROR: dist\comicdesk.exe not found >&2
    exit /b 1
)

echo OK: dist\comicdesk.exe
