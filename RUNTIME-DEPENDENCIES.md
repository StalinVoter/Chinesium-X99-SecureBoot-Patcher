# Native runtime deployment in v0.967

The release targets Windows 11 x64. Its Qt and Microsoft C/C++ runtime files
are carried inside the GUI EXE. The CLI has its own smaller native manifest.
End users do not install Python, Qt or a separate VC++ redistributable for
these private application dependencies. The four firmware-tool files remain
external and are described in tools/README.txt.

## Build

Run `RUN-SETUP-AND-BUILD.cmd`. The setup reuses an exact Python 3.13.14 x64
interpreter in the documented locations or downloads the official installer,
verifying its SHA-256 and signature. It creates a clean `.build-venv` without
system site packages. Every direct and transitive wheel has an exact version
and SHA-256 in `requirements-build.lock`. No globally installed PyInstaller
or Qt package is used.

The selected Qt binding, Essentials, Addons and Shiboken version is 6.10.3.
PyInstaller is 6.22.3; its hook package is 2026.9. The official Windows
Shiboken wheel carries the Microsoft runtime family. The spec replaces all
MSVC runtime candidates found by Analysis with this one coherent set at the
private bundle root. It never copies an arbitrary System32 or PATH runtime.
It validates ordinary and delay-load imports against every private provider's
export table and rejects unbundled Qt/Python/MSVC dependencies, wrong
architectures and conflicting private DLL basenames. OS-provided DLLs remain
the responsibility of Windows and the packaged launch tests.

`scripts/verify_exe.py` then opens each completed PyInstaller CArchive. It
requires the actual native file inventory and every DLL/PYD hash to match the
embedded manifest. It also verifies that the custom runtime hook precedes
the installed PyInstaller runtime hooks.

## Startup

The first custom runtime hook starts the session log, verifies the private
files, restricts the default DLL search directories to approved private
directories and System32, and loads the private dependency chain by absolute
path. It excludes the launch directory and PATH from these explicit loads.
It checks every loaded module sharing a protected basename against its
expected private path, including the Python/MSVC libraries already loaded by
the bootloader. It does not unload and replace an already-loaded foreign
runtime: it aborts with its exact path if this unexpected state is detected.

Qt plugin paths are set to the private plugin directory. The loaded Qt,
PySide and Shiboken versions are compared to the build manifest. The GUI
audits loaded paths after QApplication creates the Windows platform plugin.
Source execution is logged as source execution and does not claim the frozen
EXE's runtime guarantees.

Logging normally uses `LOGS` beside the executable. If that directory cannot
be written, logs use `%LOCALAPPDATA%\X99-SecureBoot-Patcher\LOGS`.
Startup error reporting uses the native Windows message box and does not
require a working Qt import. Automated self-tests suppress modal errors.

## External tools

DLL-directory changes needed by the frozen application must not make its
external programs accidentally use Qt's runtime directory. All FPT,
UEFIReplace and Memory Integrity PowerShell process creation goes through a
wrapper which clears the inherited DLL directory during process creation,
passes an environment with the original PATH and without private Qt plugin
paths, then restores the parent's private directory even on a spawn error.
This does not change the tools' firmware-validation or flashing algorithms.

## Actual packaged tests

Every Windows build runs `TEST-PACKAGED-RUNTIME.ps1` before packaging:

1. GUI EXE: import Core/Gui/Widgets, check exact versions, create and show a
   QWidget through the actual Windows Qt platform, process events, audit
   loaded DLL paths, close and return a machine-readable report.
2. CLI EXE: initialize and audit its own private runtime without Qt.
3. GUI EXE: repeat with deliberately invalid Qt and VC++ DLLs beside the
   EXE, in the current directory and in PATH; foreign Qt environment settings
   are also supplied. This case must still use the private runtime and the
   Windows platform plugin.
4. GUI entry point: launch the actual companion CLI with ShellExecuteExW/runas,
   stream a diagnostic event and read its result after exit. This check uses
   check-transport only and never accesses BIOS hardware. Both EXE hashes are
   recorded and checked before packaging.

The GUI self-tests construct the production window in runtime-check mode,
with tool/payload preflight and the BIOS probe suppressed. File-drop events
are routed through the real panel and main-window handlers into a recording
ROM loader. No network download, BIOS probe, dump, patch or flash occurs. Each success report
identifies the exact EXE SHA-256. ZIP packaging rejects missing results,
failed cases, results for different executables and altered CArchive files.
Both EXEs use asInvoker manifests, verified from the actual finished PE
resources. The fourth test requests helper elevation; on an already elevated
CI runner this does not exercise an interactive UAC prompt. The BIOS access
helper also requests administrator permission for a compatibility probe, dump
or complete flash/backup/recovery operation. GUI file-drop routing must pass
inside both packaged GUI launch cases before ZIP packaging can proceed.

Run `TEST-WINDOWS-SANDBOX.ps1` after building for the same tests in a fresh,
offline Windows Sandbox. The runner does not enable Windows features. It
maps source and binaries read-only and writes results under
`build/sandbox-results`. Sandbox testing is separate from the mandatory
current-machine build tests and is not falsely recorded as having run when
it has not.

The normal GUI creates result.json and events.jsonl before helper elevation.
The helper opens these existing files in place and never renames an elevated
replacement reply over the caller's file. The GUI waits for helper exit before
reading the reply. Cleanup exceptions are logged separately and never replace
an operation result. TEST-ELEVATED-HELPER.cmd exercises this exchange with a
diagnostic message on a user's PC; start it normally to test interactive UAC.

## Output

The local `dist` may contain the user's firmware tools if they were supplied
in `tools` before building. The public ZIP is created from a separate staging
directory and excludes those four binaries automatically. Their originals
remain untouched. Runtime DLLs remain inside the application EXEs.

The generated public file is
`Chinesium-X99-SecureBoot-Patcher-v0.967-Windows-x64.zip`, with a companion
SHA-256 file. The ZIP includes both EXEs, root and tools READMEs, donor files,
the authoritative fparts.txt, runtime manifests, helper-test script and
third-party notices.

On supported Windows 10+ systems, ucrtbase.dll, msvcp_win.dll and Windows
API-set contracts are supplied by Windows and excluded from the private DLL
inventory. The pinned MSVC v14 runtime DLLs remain bundled and checked.
