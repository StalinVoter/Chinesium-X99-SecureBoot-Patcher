# Chinesium X99 SecureBoot Patcher v0.9

First public preview of **Chinesium X99 SecureBoot Patcher**, a Windows utility for updating legacy factory-default Secure Boot PK/KEK/db certificates in AMI Aptio-style X99 firmware.

## Highlights

- Structure-driven AMI X99 compatibility rather than a hard-coded motherboard list.
- Automatic detection of AMI test PK and missing Microsoft 2023 KEK/db certificate material.
- Exact validated PK/KEK/db update payloads included.
- Input ROM is never overwritten.
- Replacements are re-extracted and verified after firmware-volume rebuilds.
- Silent backend protection for rebuild-induced microcode/FIT pointer movement, without exposing FIT controls or terminology in the GUI.
- Unknown or ambiguous firmware layouts fail closed.

## UEFIReplace requirement

`UEFIReplace.exe` is **not redistributed** by this project. Download **UEFIReplace 0.28.0 for Windows** from the official LongSoft/UEFITool release:

https://github.com/LongSoft/UEFITool/releases/download/0.28.0/UEFIReplace_0.28.0_win32.zip

Required SHA-256 of the extracted `UEFIReplace.exe`:

`ab05d53fcac19651818f4ee4505813b10badec7a10d141836fff3bba8964ed8b`

## Tested firmware corpus

Regression coverage includes supplied firmware from PANDL X99-XD3 compact/classic, MACHINIST X99-V9S, Qiyida X99-K9S, and Jginue X99 boards.

**42/42 regression tests pass.**

## Build

Place the verified `UEFIReplace.exe` in `tools\`, then run:

```bat
RUN-SETUP-AND-BUILD.cmd
```

Expected outputs:

```text
dist\X99-Secureboot-patcher.exe
dist\X99-Secureboot-patcher-CLI.exe
```

## Important

The tool creates patched ROM files. It does not flash firmware. Keep a known-good firmware backup and an appropriate recovery method before flashing any modified image.
