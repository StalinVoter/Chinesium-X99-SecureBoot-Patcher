@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "BUILD_PY=%~dp0.build-venv\Scripts\python.exe"
if not exist "%BUILD_PY%" (
  echo Run RUN-SETUP-AND-BUILD.cmd to create the pinned build environment.
  exit /b 1
)
for %%F in (Chinesium-X99-SecureBoot-Patcher-v0.966-Windows-x64.zip Chinesium-X99-SecureBoot-Patcher-v0.966-Windows-x64.zip.sha256) do if exist "%%F" del /q "%%F"
for %%F in (X99-Secureboot-patcher.exe X99-Secureboot-patcher-CLI.exe) do if exist "dist\%%F" del /q "dist\%%F"
if exist "build" rmdir /s /q "build"
mkdir "build"
if errorlevel 1 exit /b 1
"%BUILD_PY%" -m pytest -q --junitxml "build\source-tests.xml"
if errorlevel 1 exit /b 1
"%BUILD_PY%" -m PyInstaller --noconfirm --clean --workpath "build\pyinstaller" patcher.spec
if errorlevel 1 exit /b 1
"%BUILD_PY%" scripts\verify_exe.py "dist\X99-Secureboot-patcher.exe" "build\verified-gui.json"
if errorlevel 1 exit /b 1
"%BUILD_PY%" scripts\verify_exe.py "dist\X99-Secureboot-patcher-CLI.exe" "build\verified-cli.json"
if errorlevel 1 exit /b 1
if not exist "dist\tools" mkdir "dist\tools"
if not exist "dist\secureboot_donors" mkdir "dist\secureboot_donors"
if not exist "dist\fpt_support" mkdir "dist\fpt_support"
for %%F in (UEFIReplace.exe fptw64.exe pmxdll32e.DLL idrvdll32e.DLL) do if exist "tools\%%F" copy /y "tools\%%F" "dist\tools\%%F" >nul
copy /y "fpt_support\fparts.txt" "dist\fpt_support\fparts.txt" >nul
if errorlevel 1 exit /b 1
copy /y "fpt_support\fparts.txt" "dist\tools\fparts.txt" >nul
if errorlevel 1 exit /b 1
for %%F in (PkVar.ffs KekVar.ffs dbVar.ffs) do (
  copy /y "secureboot_donors\%%F" "dist\secureboot_donors\%%F" >nul
  if errorlevel 1 exit /b 1
)
copy /y "README.txt" "dist\README.txt" >nul
if errorlevel 1 exit /b 1
copy /y "tools\README.txt" "dist\tools\README.txt" >nul
if errorlevel 1 exit /b 1
"%BUILD_PY%" scripts\copy_licenses.py
if errorlevel 1 exit /b 1
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0TEST-PACKAGED-RUNTIME.ps1" -Distribution "%~dp0dist" -Reports "%~dp0build"
if errorlevel 1 exit /b 1
"%BUILD_PY%" scripts\package_release.py
if errorlevel 1 exit /b 1
echo Ready: Chinesium-X99-SecureBoot-Patcher-v0.966-Windows-x64.zip
exit /b 0
