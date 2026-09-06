@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHON_CALL="
where py >nul 2>&1
if not errorlevel 1 (py -3 -c "import sys" >nul 2>&1 && set "PYTHON_CALL=py -3")
if not defined PYTHON_CALL (
  where python >nul 2>&1
  if not errorlevel 1 (python -c "import sys" >nul 2>&1 && set "PYTHON_CALL=python")
)
if not defined PYTHON_CALL (
  for %%P in (
    "%LocalAppData%\Programs\Python\Python313\python.exe"
    "%LocalAppData%\Programs\Python\Python312\python.exe"
    "%ProgramFiles%\Python313\python.exe"
    "%ProgramFiles%\Python312\python.exe"
  ) do if exist "%%~P" if not defined PYTHON_CALL set PYTHON_CALL="%%~P"
)
if not defined PYTHON_CALL (
  echo Python was not found. Run RUN-SETUP-AND-BUILD.cmd.
  pause
  exit /b 1
)

echo Using Python: %PYTHON_CALL%
%PYTHON_CALL% -m pip install --disable-pip-version-check -r requirements.txt pyinstaller
if errorlevel 1 exit /b 1

%PYTHON_CALL% -m PyInstaller --noconfirm --clean --onefile --windowed --name X99-Secureboot-patcher X99SecurebootPatcher-GUI.py
if errorlevel 1 exit /b 1
%PYTHON_CALL% -m PyInstaller --noconfirm --clean --onefile --name X99-Secureboot-patcher-CLI X99SecurebootPatcher-CLI.py
if errorlevel 1 exit /b 1

if not exist "dist\tools" mkdir "dist\tools"
if not exist "dist\secureboot_donors" mkdir "dist\secureboot_donors"
copy /y "tools\UEFIReplace.exe" "dist\tools\UEFIReplace.exe" >nul
copy /y "secureboot_donors\PkVar.ffs" "dist\secureboot_donors\PkVar.ffs" >nul
copy /y "secureboot_donors\KekVar.ffs" "dist\secureboot_donors\KekVar.ffs" >nul
copy /y "secureboot_donors\dbVar.ffs" "dist\secureboot_donors\dbVar.ffs" >nul

echo.
echo Built: dist\X99-Secureboot-patcher.exe
echo Built: dist\X99-Secureboot-patcher-CLI.exe
echo Verified external UEFIReplace 0.28.0 and validated Secure Boot update payloads copied beside the executables.
