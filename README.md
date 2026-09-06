# Chinesium X99 SecureBoot Patcher v0.9

A Windows utility for inspecting and updating the **factory-default Secure Boot PK, KEK and db certificates** stored in AMI Aptio-style X99 firmware images.

The patcher is designed around the firmware structures themselves rather than a hard-coded motherboard list. If a ROM exposes the validated AMI Secure Boot variable layout, the app can inspect it and determine which of PK, KEK and db need updating. Unknown or malformed layouts fail closed instead of being guessed.

## What v0.9 updates

The automatic plan can update:

- **PK** when the firmware contains `DO NOT TRUST - AMI Test PK`;
- **KEK** when Microsoft Corporation KEK 2K CA 2023 is missing;
- **db** when the expected Microsoft 2023 UEFI certificates are missing.

A different production/OEM PK is preserved rather than overwritten merely because it is not the validated update PK.

The ROM is written to a **new output file**. The input image is never overwritten.

## Required external tool: UEFIReplace 0.28.0

This project deliberately does **not** redistribute `UEFIReplace.exe`.

Download the exact Windows build from the official LongSoft/UEFITool project:

- Official repository: https://github.com/LongSoft/UEFITool
- Official 0.28.0 release: https://github.com/LongSoft/UEFITool/releases/tag/0.28.0
- Exact Windows archive: https://github.com/LongSoft/UEFITool/releases/download/0.28.0/UEFIReplace_0.28.0_win32.zip

Extract `UEFIReplace.exe` and place it at:

```text
tools\UEFIReplace.exe
```

The required executable has SHA-256:

```text
ab05d53fcac19651818f4ee4505813b10badec7a10d141836fff3bba8964ed8b
```

The build/setup scripts and the application verify this exact hash and refuse another binary.

## Validated Secure Boot update payloads

The source repository includes the exact PK/KEK/db update payloads used by the application:

| File | SHA-256 |
|---|---|
| `secureboot_donors/PkVar.ffs` | `6ad2c119c70b4325ad29138c65d0ddafd09cdba299d34fdcb4e3f2aa01b1e7dd` |
| `secureboot_donors/KekVar.ffs` | `6b8bcfd771d6efcba8459d62d2a8687a252671d66ea0f22ee6aa2140ac8e802a` |
| `secureboot_donors/dbVar.ffs` | `744662e5b2c92171cf777d36a6b4e3c59d2a6d99ffe4914a41f6a7a2a24f779a` |

## Compatibility approach

The patcher looks for the standard AMI factory-default Secure Boot FFS files by GUID and validates their internal structure before permitting a modification:

- `PkVar` — `CC0F8A3F-3DEA-4376-9679-5426BA0A907E`
- `KekVar` — `9FE7DE69-0AEA-470A-B50A-139813649189`
- `dbVar` — `FBF95065-427F-47B3-8077-D13C60710998`

The parser validates the Freeform FFS wrapper, GUID-defined LZMA section, raw authenticated-variable payload, and EFI signature-list framing. It refuses ambiguous or structurally unfamiliar targets.

The generic implementation has been regression-tested against supplied firmware from multiple Chinese X99 families, including PANDL X99-XD3, MACHINIST X99-V9S, Qiyida X99-K9S and Jginue X99 firmware.

## Safety checks

Before accepting an output ROM, v0.9 verifies that:

- the input ROM remains untouched;
- output size matches input size;
- update-payload GUIDs, structures, certificate content and exact hashes are correct;
- each required Secure Boot target is unambiguous;
- each replacement re-extracts byte-for-byte identical to the expected update payload;
- firmware-volume rebuilding does not introduce unrelated changes outside the allowed mutation boundary;
- non-target Secure Boot data is preserved;
- rebuild-induced microcode/FIT pointer displacement is silently corrected only when it can be mapped unambiguously to the same microcode identities.

Pre-existing FIT state is not a user-facing requirement and is not shown in the GUI.

## Building on Windows

1. Download the official `UEFIReplace_0.28.0_win32.zip` linked above.
2. Extract its `UEFIReplace.exe` to `tools\UEFIReplace.exe`.
3. Run:

```bat
RUN-SETUP-AND-BUILD.cmd
```

The setup script verifies the UEFIReplace SHA-256 before continuing. It then installs/checks the Python build prerequisites and builds:

```text
dist\X99-Secureboot-patcher.exe
dist\X99-Secureboot-patcher-CLI.exe
```

The verified external `UEFIReplace.exe` and the validated Secure Boot update payloads are copied beside the executables in `dist\`.

If Python and the dependencies are already installed, you can use `build_exe.bat` after placing the required UEFIReplace binary in `tools\`.

## CLI

```text
X99-Secureboot-patcher-CLI.exe inspect mybios.ROM
X99-Secureboot-patcher-CLI.exe patch mybios.ROM
X99-Secureboot-patcher-CLI.exe patch mybios.ROM -o patched.ROM
```

## After flashing

Patching a ROM changes the firmware's **factory-default** Secure Boot key payloads. It does not itself replace keys already enrolled in live UEFI NVRAM.

After flashing, use the motherboard's Secure Boot / Key Management menu to clear and re-enroll or restore the factory-default keys, then verify the live Secure Boot state.

## Validation

See [`VALIDATION-v0.9.txt`](VALIDATION-v0.9.txt) for the regression details and [`RELEASE-NOTES-v0.9.txt`](RELEASE-NOTES-v0.9.txt) for the release summary.

## Firmware flashing warning

This application creates patched ROM files; it does not flash the motherboard. Firmware flashing always carries recovery risk. Keep a known-good backup and an appropriate recovery method for the board you are working on.
