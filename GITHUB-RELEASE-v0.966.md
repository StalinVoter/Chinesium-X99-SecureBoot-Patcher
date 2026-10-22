# Chinesium X99 SecureBoot Patcher v0.966

## Changes since v0.964

- **Private Qt and Visual C++ runtime:** the Windows build pins Python,
  PySide/Qt/Shiboken, PyInstaller and their build dependencies. Each EXE carries
  its verified runtime DLLs, restricts DLL lookup and preloads private copies.
  Every normal packaged launch checks native-file hashes and loaded paths;
  GUI startup also checks Qt binding/runtime versions and plugin locations.
  This addresses the reported QtCore DLL startup failure without relying on
  whichever Qt or Visual C++ DLLs happen to be installed elsewhere.
- **Earlier diagnostics:** session logging begins before Qt imports. Native
  startup errors identify the failed dependency and diagnostic log, including
  when the GUI cannot initialize. Logs also have a writable-folder fallback.
- **Required-tools panel:** every GUI launch checks UEFIReplace.exe 0.28.0 and
  Intel FPT 9.1.10.1000's fptw64.exe, pmxdll32e.DLL and idrvdll32e.DLL in the
  application's tools folder. Missing or incorrect files each get a
  **Download this file** repair button. Downloads run in the background, use
  pinned HTTPS sources, verify exact sizes and SHA-256 hashes, and install
  only after verification. Existing files survive failed downloads. Both FPT
  companion DLL hashes now gate BIOS access as well as the executable hash.
- **Drag-and-drop and BIOS privileges:** the GUI runs normally with an
  asInvoker manifest so ordinary Explorer file drops can reach it. Both the
  opening panel and main window accept one local file. BIOS compatibility
  checks, dumps and complete flash/backup/recovery workflows request elevation
  through the companion CLI, keeping the GUI at normal privileges. Keep both
  EXEs together and start the GUI normally, without Run as administrator.
- **Explicit flash acknowledgement:** the original ROM-created question is
  preserved. Selecting Yes opens the additional warning text requested by
  the maintainer. Both dialogs default to No, and flashing requires Yes in
  both plus a successful FPT readiness check.
- **Reproducible build and release validation:** setup uses isolated Windows
  Python 3.13.14 and hash-locked wheels. Source tests permit user-supplied tools
  in the build folder. PowerShell paths are resolved after parameter binding
  and passed explicitly by the builder. The actual finished EXEs are inspected
  for native-file hashes, runtime-hook order and asInvoker manifests. GUI,
  CLI and conflicting-DLL launches, including packaged GUI drop routing, must
  pass for the exact executable hashes before the release ZIP is created.
  The repository now automates this build and publication on Windows.

The firmware parsing, Secure Boot replacement containment, PK/KEK/db payloads,
protected-variable handling and selective rebuild safeguard are unchanged
from v0.964. The dual verified backups and automatic recovery workflow are
retained inside the BIOS access helper.

## Download and use

The Windows asset retains the previous release's naming structure:
`Chinesium-X99-SecureBoot-Patcher-v0.966-Windows-x64.zip`.

Extract the complete archive and keep its two EXEs and supporting folders
together. Open `X99-Secureboot-patcher.exe` normally. The Required tools panel
can install the exact external files on demand; FPT and UEFIReplace binaries
are not redistributed in the ZIP. Validated donor files and authoritative
`fpt_support/fparts.txt` are included. Source is available from this release's
Git tag and GitHub's source archives.

After flashing, restore/re-enroll the firmware's factory-default Secure Boot
keys and verify the live Secure Boot state as described in the README.
