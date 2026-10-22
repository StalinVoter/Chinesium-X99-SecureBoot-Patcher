# Chinesium X99 SecureBoot Patcher v0.965

Private, version-locked Qt and Visual C++ runtime deployment replaces reliance
on arbitrary DLL copies found on the target machine. Startup verifies native
hashes, preloads the private dependency chain and checks loaded module paths
before the GUI starts. Logs begin before Qt imports.

The Windows build verifies the DLL bytes inside the actual finished EXEs and
requires real GUI, CLI and conflicting-DLL launch tests before creating the
tool-free Windows ZIP. External firmware tools remain user-supplied.

Build and clean-machine test evidence must accompany the compiled release.
The source-authoring checks are listed separately in VALIDATION-v0.965.txt;
they do not claim a Windows EXE or Windows Sandbox test was performed here.
