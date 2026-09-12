[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogPath = Join-Path $Root 'setup-build-X99-Secureboot-patcher.log'
$BuildScript = Join-Path $Root 'build_exe.bat'
$Requirements = Join-Path $Root 'requirements.txt'
$DistExe = Join-Path $Root 'dist\X99-Secureboot-patcher.exe'
$UefiReplace = Join-Path $Root 'tools\UEFIReplace.exe'
$ExpectedUefiReplace = 'ab05d53fcac19651818f4ee4505813b10badec7a10d141836fff3bba8964ed8b'
$UefiReplaceUrl = 'https://github.com/LongSoft/UEFITool/releases/download/0.28.0/UEFIReplace_0.28.0_win32.zip'
$Fpt = Join-Path $Root 'tools\fptw64.exe'
$ExpectedFpt = 'b7e942e903f5f6bba84c3e9294edc8cc097c1173ca249a41a4cca1ab9e15a697'
$FptFolderUrl = 'https://github.com/CE1CECL/IntelCSTools/tree/ce1cecl/ME%20System%20Tools%20v9.1%20r7/Flash%20Programming%20Tool/WIN64'
$Fparts = Join-Path $Root 'fpt_support\fparts.txt'
$ExpectedFparts = '9f815e22fdc5562f0af6ac552c27e0adccf9f3654c3d76dbc4f9cc9278bc2313'

function Write-Log([string]$Message) {
    $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Write-Host $line
    Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8
}
function Fail([string]$Message) { Write-Log "ERROR: $Message"; throw $Message }
function Download-VerifiedFile([string]$Uri,[string]$Destination,[string]$ExpectedSha256) {
    Write-Log "Downloading $Uri"
    Invoke-WebRequest -UseBasicParsing -Uri $Uri -OutFile $Destination
    $actual=(Get-FileHash -Algorithm SHA256 -LiteralPath $Destination).Hash.ToLowerInvariant()
    if ($actual -ne $ExpectedSha256.ToLowerInvariant()) { Remove-Item $Destination -Force -ErrorAction SilentlyContinue; Fail "SHA-256 mismatch for $Uri" }
    Write-Log "SHA-256 verified: $actual"
}

'' | Set-Content -LiteralPath $LogPath -Encoding UTF8
Write-Log 'Starting X99 Secureboot patcher v0.964 build-environment setup.'
Write-Log "Source folder: $Root"
if (-not (Test-Path $BuildScript -PathType Leaf)) { Fail 'build_exe.bat is missing.' }
if (-not (Test-Path $Requirements -PathType Leaf)) { Fail 'requirements.txt is missing.' }

if (-not (Test-Path $UefiReplace -PathType Leaf)) {
    Write-Host ''
    Write-Host 'UEFIReplace 0.28.0 is required and is not redistributed with this project.' -ForegroundColor Yellow
    Write-Host "Exact Windows archive: $UefiReplaceUrl"
    Write-Host 'Extract UEFIReplace.exe into tools\UEFIReplace.exe and run this script again.'
    Write-Host "Required SHA-256: $ExpectedUefiReplace"
    Fail 'Required external UEFIReplace.exe is not present.'
}
$toolHash=(Get-FileHash -Algorithm SHA256 -LiteralPath $UefiReplace).Hash.ToLowerInvariant()
if ($toolHash -ne $ExpectedUefiReplace) { Fail "UEFIReplace.exe hash mismatch: $toolHash. Expected $ExpectedUefiReplace" }
Write-Log "Official UEFIReplace 0.28.0 verified: $toolHash"

$requiredFptFiles = @('fptw64.exe','pmxdll32e.DLL','idrvdll32e.DLL')
foreach ($name in $requiredFptFiles) {
    $p = Join-Path $Root ("tools\" + $name)
    if (-not (Test-Path $p -PathType Leaf)) {
        Write-Host ''
        Write-Host 'Intel Flash Programming Tool 9.1.10.1000 files are required for BIOS dump/flash.' -ForegroundColor Yellow
        Write-Host "Verified source folder: $FptFolderUrl"
        Write-Host 'Copy fptw64.exe, pmxdll32e.DLL and idrvdll32e.DLL into tools\ and run this script again.'
        Fail "Required external FPT file is missing: $name"
    }
}
$fptHash=(Get-FileHash -Algorithm SHA256 -LiteralPath $Fpt).Hash.ToLowerInvariant()
if ($fptHash -ne $ExpectedFpt) { Fail "fptw64.exe hash mismatch: $fptHash. Expected $ExpectedFpt (FPT 9.1.10.1000)" }
Write-Log "Intel FPT 9.1.10.1000 verified: $fptHash"

if (-not (Test-Path $Fparts -PathType Leaf)) { Fail 'fpt_support\fparts.txt is missing.' }
$fpartsHash=(Get-FileHash -Algorithm SHA256 -LiteralPath $Fparts).Hash.ToLowerInvariant()
if ($fpartsHash -ne $ExpectedFparts) { Fail "Bundled authoritative fparts.txt hash mismatch: $fpartsHash" }
Write-Log "Authoritative fparts.txt verified: $fpartsHash"

$PythonVersion='3.13.14'
$PythonUrl="https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe"
$PythonInstallerSha256='c54d9b9bbb8a36e6489363ddd01139707fd781d72f1f9e90c7ec65d0061368e0'
$PythonInstallDir=Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313'
$PythonExe=Join-Path $PythonInstallDir 'python.exe'
if (-not (Test-Path $PythonExe -PathType Leaf)) {
    $TempDir=Join-Path $env:TEMP ('X99-Secureboot-Build-'+[Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
    try {
        $Installer=Join-Path $TempDir "python-$PythonVersion-amd64.exe"
        Download-VerifiedFile $PythonUrl $Installer $PythonInstallerSha256
        $sig=Get-AuthenticodeSignature -LiteralPath $Installer
        if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'Python Software Foundation') { Fail 'Python installer signature verification failed.' }
        Write-Log "Installing Python $PythonVersion per-user."
        $args=@('/quiet','InstallAllUsers=0',"TargetDir=$PythonInstallDir",'PrependPath=1','Include_pip=1','Include_launcher=1','InstallLauncherAllUsers=0','Include_test=0','AssociateFiles=0','Shortcuts=0','CompileAll=0')
        $proc=Start-Process -FilePath $Installer -ArgumentList $args -Wait -PassThru
        if ($proc.ExitCode -ne 0) { Fail "Python installer exited $($proc.ExitCode)." }
    } finally { Remove-Item $TempDir -Recurse -Force -ErrorAction SilentlyContinue }
}
$ver=(& $PythonExe --version 2>&1 | Out-String).Trim(); Write-Log "Using $ver at $PythonExe"
& $PythonExe -m ensurepip --upgrade; if ($LASTEXITCODE -ne 0) { Fail 'ensurepip failed.' }
& $PythonExe -m pip install --disable-pip-version-check --upgrade pip setuptools wheel; if ($LASTEXITCODE -ne 0) { Fail 'pip bootstrap failed.' }
& $PythonExe -m pip install --disable-pip-version-check --prefer-binary -r $Requirements pyinstaller; if ($LASTEXITCODE -ne 0) { Fail 'Installing PySide6/PyInstaller failed.' }
$env:PATH="$PythonInstallDir;$(Join-Path $PythonInstallDir 'Scripts');$env:PATH"
Push-Location $Root
try { & cmd.exe /d /c "call `"$BuildScript`""; $rc=$LASTEXITCODE } finally { Pop-Location }
if ($rc -ne 0) { Fail "build_exe.bat failed with exit code $rc." }
if (-not (Test-Path $DistExe -PathType Leaf)) { Fail "$DistExe was not created." }
$hash=(Get-FileHash -Algorithm SHA256 -LiteralPath $DistExe).Hash.ToLowerInvariant()
Write-Log "Build completed successfully: $DistExe"
Write-Log "Standalone EXE SHA-256: $hash"
Write-Host ''; Write-Host 'DONE.' -ForegroundColor Green; Write-Host "Standalone GUI: $DistExe"; Write-Host "Log: $LogPath"
exit 0
