# Chinesium X99 SecureBoot Patcher v0.964

A Windows utility for updating the **factory-default Secure Boot PK, KEK and db certificates** stored in AMI Aptio-style X99 firmware images, with integrated Intel FPT BIOS dump and flash support.

The Secure Boot patcher is driven by firmware structure rather than a hard-coded motherboard list. Unknown or malformed Secure Boot layouts fail closed instead of being guessed.

## Secure Boot update

The automatic plan can update:

- **PK** when the firmware contains `DO NOT TRUST - AMI Test PK`;
- **KEK** when Microsoft Corporation KEK 2K CA 2023 is missing;
- **db** when the expected Microsoft 2023 UEFI certificates are missing.

A different production/OEM PK is preserved rather than overwritten merely because it is not the validated update PK.

ROM patching always creates a **new output file**. The selected input ROM is never overwritten.

### Secure Boot build progress

Clicking **Create Secure Boot-patched ROM** shows a live 0–100% progress bar in the build card. Unlike FPT, UEFIReplace does not report a byte-level percentage, so this bar advances only at real pipeline milestones: input validation, patch-plan creation, completion of each PK/KEK/db replacement, final Secure Boot validation, and final size validation. It is monotonic, reaches 100% only after the output ROM has passed the complete build pipeline, and does not invent or duplicate tool-output percentage records in the session log.

### Contained UEFIReplace rebuilds

UEFIReplace 0.28.0 is used as a firmware-volume rebuild helper, but its complete output image is **not trusted wholesale**. Some AMI X99 images contain non-empty pad-file data in other firmware volumes that UEFIReplace may clear while rebuilding an unrelated target.

v0.964 therefore verifies the requested replacement and the target's outermost firmware-volume boundary, starts the accepted image from the exact original input bytes, and copies only that validated target firmware-volume range from the helper-tool output. It then re-parses the accepted image, requires the donor FFS to be byte-identical, requires the target firmware-volume boundary to remain unchanged, and requires every byte outside that firmware volume to remain byte-identical to the input ROM.

This keeps the fail-closed mutation safeguard while preventing unrelated pad, board-specific or other firmware-volume data from being altered as a side effect of a Secure Boot update.

## BIOS dump and flash

The integrated BIOS-access layer uses **Intel Flash Programming Tool (FPT) 9.1.10.1000**.

The GUI provides:

- **Dump BIOS…** — dump the currently installed SPI firmware to a ROM file;
- **Flash BIOS…** — flash a selected ROM with mandatory verified pre-flash backup;
- live, complete FPT console output in the operation log;
- one stable progress bar for each continuous read, erase, program and verify pass; a new same-type bar is created only when FPT genuinely starts another pass and its percentage resets;
- exact dump-size validation against the SPI capacity FPT reports;
- automatic rollback when a flash fails after erase/programming has begun.

### Pre-flash backup and recovery

Before **any flash erase/programming begins**, the app:

1. dumps the currently installed BIOS once;
2. dumps it a second time independently;
3. requires the two dumps to have the same size and be byte-for-byte identical (same SHA-256);
4. saves the verified backup permanently under the user's Documents folder;
5. only then starts the requested flash.

If the requested flash fails **before** erase/programming begins, the app aborts without an unnecessary recovery write.

If it fails **after** erase/programming begins, the app automatically attempts to flash the verified backup. If recovery itself fails, the app stops further write attempts and displays a prominent **do not reboot or power off** warning together with the saved backup path.

A successful flash is accepted only after FPT exits successfully, reports `FPT Operation Passed`, and reports `RESULT: The data is identical.`

## Required external tool: UEFIReplace 0.28.0

This project deliberately does **not** redistribute `UEFIReplace.exe`.

Download the exact Windows build from the official LongSoft/UEFITool project:

- Repository: https://github.com/LongSoft/UEFITool
- Release: https://github.com/LongSoft/UEFITool/releases/tag/0.28.0
- Exact Windows archive: https://github.com/LongSoft/UEFITool/releases/download/0.28.0/UEFIReplace_0.28.0_win32.zip

Extract `UEFIReplace.exe` to:

```text
tools\UEFIReplace.exe
```

Required SHA-256:

```text
ab05d53fcac19651818f4ee4505813b10badec7a10d141836fff3bba8964ed8b
```

## Required external tool: Intel FPT 9.1.10.1000

Intel FPT is also deliberately **not redistributed** by this project.

The exact verified `WIN64` directory is available here:

https://github.com/CE1CECL/IntelCSTools/tree/ce1cecl/ME%20System%20Tools%20v9.1%20r7/Flash%20Programming%20Tool/WIN64

Copy these three files into `tools\`:

```text
tools\fptw64.exe
tools\pmxdll32e.DLL
tools\idrvdll32e.DLL
```

Required SHA-256 of `fptw64.exe`:

```text
b7e942e903f5f6bba84c3e9294edc8cc097c1173ca249a41a4cca1ab9e15a697
```

That executable is Intel Flash Programming Tool **9.1.10.1000**, the version used and validated for the X99/C610 workflow in this project.

## Authoritative `fparts.txt`

The project ships its own `fpt_support\fparts.txt`:

```text
SHA-256: 9f815e22fdc5562f0af6ac552c27e0adccf9f3654c3d76dbc4f9cc9278bc2313
```

Immediately before **every** FPT compatibility probe, BIOS dump and BIOS flash, the app unconditionally copies this file to:

```text
tools\fparts.txt
```

Any existing FPT `fparts.txt` is overwritten. The files are not merged and there is no fallback to the stock FPT table. If the overwrite or hash verification fails, FPT is not started.

## Windows Memory Integrity / Core isolation

At launch, the app checks whether Windows **Memory Integrity (HVCI)** is actually running and performs a non-destructive FPT `-i` compatibility probe when the required FPT files are installed.

- If FPT works, dump/flash remain available even if Memory Integrity is running.
- If Memory Integrity is running **and** this FPT installation cannot access the flash, the GUI explains that BIOS dump/flash are unavailable until **Windows Security → Device security → Core isolation details → Memory integrity** is disabled and Windows is restarted.
- If FPT fails while Memory Integrity is not running, the app reports the actual FPT/platform failure instead of blaming Core isolation.


## FPT progress display

The FPT window shows one live progress bar for each continuous read, erase, program and verify pass. The bracketed hexadecimal address printed by FPT is a moving cursor address and is not treated as a separate phase. If FPT later starts another pass of the same type and its percentage resets, a new pass bar is created.

## Automatic session logging in v0.964

Every GUI or CLI launch automatically creates a chronological session log under:

```text
<application folder>\LOGS\Session-YYYYMMDD-HHMMSS-mmm-PIDxxxx.log
```

For the compiled Windows application, `<application folder>` is the `dist` folder that contains the executable. `LOGS` is created automatically at launch if it does not already exist.

The session log is the master record for the entire run. It includes application/version/environment details, tool and payload validation, hashes and paths, the Memory Integrity/HVCI query including its PowerShell output, the complete launch-time `fptw64.exe -i` transcript, ROM inspection results, Secure Boot planning, every UEFIReplace command and stdout/stderr stream, every FPT command/output record, backup dump sizes/hashes/comparison, flash and recovery decisions, caught/unhandled errors, and final operation results. In v0.964, each underlying diagnostic item is written once: raw FPT percentage lines themselves are the session-log progress record, while parsed progress events are used only to drive the GUI bars; structured result summaries omit raw transcript arrays that were already logged live.

Secure Boot build artifacts are also centralized in `LOGS` instead of being written beside the output ROM:

```text
LOGS\<ROM>.build.log
LOGS\<ROM>.report.txt
LOGS\<ROM>.report.json
```

The operation-specific FPT `.fpt.log`/JSON artifacts and permanent BIOS backups remain available in their existing locations. The master session log records the same operation chronologically without replaying duplicate copies of already logged raw output.

## FPT logging and progress

FPT output is captured directly from the child process. Carriage-return progress updates are treated as records as well as ordinary newline-delimited lines, so the technical log retains every command/output record received from FPT.

The GUI uses one stable bar for each continuous FPT read, erase, program and verify pass. The bracketed hexadecimal address reported by FPT is only the current cursor position and does not create a new bar. If FPT genuinely begins another pass of the same type and its percentage resets, the GUI creates a second pass bar. The same complete transcript is also written to a persistent `.fpt.log` file (beside a manual dump, or in the BIOS Backups folder for a flash/recovery workflow). For a normal single-pass flash, the display is therefore approximately:

```text
Reading flash                         100%
Erasing flash                         100%
Programming flash                     100%
Verifying flash                       100%
```

## Validated Secure Boot update payloads

The repository includes the exact PK/KEK/db update payloads used by the application:

| File | SHA-256 |
|---|---|
| `secureboot_donors/PkVar.ffs` | `6ad2c119c70b4325ad29138c65d0ddafd09cdba299d34fdcb4e3f2aa01b1e7dd` |
| `secureboot_donors/KekVar.ffs` | `6b8bcfd771d6efcba8459d62d2a8687a252671d66ea0f22ee6aa2140ac8e802a` |
| `secureboot_donors/dbVar.ffs` | `744662e5b2c92171cf777d36a6b4e3c59d2a6d99ffe4914a41f6a7a2a24f779a` |

## Secure Boot compatibility and safety

The patcher locates the standard AMI factory-default Secure Boot FFS files by GUID and validates their internal structure before permitting modification. The generic implementation has been regression-tested against supplied firmware from multiple Chinese X99 families, including PANDL X99-XD3, MACHINIST X99-V9S, Qiyida X99-K9S and Jginue X99 firmware.

The existing silent rebuild safeguard remains in place: if UEFIReplace moves microcode blobs, the app corrects only new FIT pointer displacement attributable to its own rebuild while preserving any pre-existing stale relationship. FIT is not displayed in the GUI.

## Building on Windows

1. Put the exact `UEFIReplace.exe` in `tools\`.
2. Put `fptw64.exe`, `pmxdll32e.DLL` and `idrvdll32e.DLL` from the verified FPT WIN64 folder in `tools\`.
3. Run:

```bat
RUN-SETUP-AND-BUILD.cmd
```

The setup validates the pinned UEFIReplace/FPT hashes and the bundled authoritative `fparts.txt`, then builds the executables and copies the runtime documentation/data into `dist\`:

```text
dist\X99-Secureboot-patcher.exe
dist\X99-Secureboot-patcher-CLI.exe
dist\README.txt
dist\tools\README.txt
dist\secureboot_donors\PkVar.ffs
dist\secureboot_donors\KekVar.ffs
dist\secureboot_donors\dbVar.ffs
dist\fpt_support\fparts.txt
```

`dist\README.txt` is the main end-user guide. `dist\tools\README.txt` gives the exact download locations, required hashes, filenames, and placement instructions for the external UEFIReplace and Intel FPT files.

The GUI executable requests Administrator privileges because direct FPT dump/flash operations require elevated hardware access.

## After flashing a Secure Boot-patched ROM

Patching a ROM changes the firmware's **factory-default** Secure Boot key payloads. It does not itself replace keys already enrolled in live UEFI NVRAM.

After flashing, use the motherboard's Secure Boot / Key Management menu to clear and re-enroll or restore the factory-default keys, then verify the live Secure Boot state.

## Version

Public release version: **v0.964**.
