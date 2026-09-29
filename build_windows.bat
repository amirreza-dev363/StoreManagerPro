@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo   Store Manager Pro - Windows Build
echo ========================================
echo.

where py >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python 3 was not found.
  echo Install Python 3 from python.org and enable "Add Python to PATH".
  pause
  exit /b 1
)

echo [1/3] Installing build tools...
py -m pip install --upgrade pyinstaller
if errorlevel 1 goto :error

echo.
echo [2/3] Building StoreManagerPro.exe...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
py -m PyInstaller --noconfirm --clean --onefile --windowed --name StoreManagerPro app.py
if errorlevel 1 goto :error

if not exist "dist\StoreManagerPro.exe" (
  echo ERROR: EXE was not created.
  goto :error
)

echo.
echo [3/3] Building Windows installer...

set "ISCC="
where ISCC.exe >nul 2>nul
if not errorlevel 1 set "ISCC=ISCC.exe"

if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 7\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not defined ISCC (
  echo.
  echo EXE created successfully:
  echo   %CD%\dist\StoreManagerPro.exe
  echo.
  echo Inno Setup was not found in the standard locations.
  echo Open Inno Setup and compile installer\StoreManagerPro_Setup.iss with F9.
  goto :done
)

if not exist "dist-installer" mkdir "dist-installer"
"%ISCC%" "installer\StoreManagerPro_Setup.iss"
if errorlevel 1 goto :error

if exist "dist-installer\StoreManagerPro_Setup.exe" (
  echo.
  echo ========================================
  echo BUILD SUCCESSFUL!
  echo ========================================
  echo Installer:
  echo   %CD%\dist-installer\StoreManagerPro_Setup.exe
  echo.
  echo EXE:
  echo   %CD%\dist\StoreManagerPro.exe
  goto :done
)

echo ERROR: Inno Setup finished but installer was not found.
goto :error

:error
echo.
echo ========================================
echo BUILD FAILED
echo ========================================
pause
exit /b 1

:done
pause
exit /b 0
