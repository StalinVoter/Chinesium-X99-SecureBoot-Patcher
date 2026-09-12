External tools required by Chinesium X99 SecureBoot Patcher v0.964
================================================================

1) UEFIReplace 0.28.0
---------------------
UEFIReplace is required for Secure Boot ROM patching and is NOT redistributed by this project.

Official project:
https://github.com/LongSoft/UEFITool

Exact Windows archive:
https://github.com/LongSoft/UEFITool/releases/download/0.28.0/UEFIReplace_0.28.0_win32.zip

Place:
  tools\UEFIReplace.exe

Required SHA-256:
ab05d53fcac19651818f4ee4505813b10badec7a10d141836fff3bba8964ed8b

2) Intel Flash Programming Tool 9.1.10.1000
-------------------------------------------
Intel FPT is required for the Dump BIOS and Flash BIOS functions and is NOT redistributed by this project.

Verified public source containing the exact files:
https://github.com/CE1CECL/IntelCSTools/tree/ce1cecl/ME%20System%20Tools%20v9.1%20r7/Flash%20Programming%20Tool/WIN64

Copy these files from that WIN64 folder into tools\:
  fptw64.exe
  pmxdll32e.DLL
  idrvdll32e.DLL

Required SHA-256 of fptw64.exe:
b7e942e903f5f6bba84c3e9294edc8cc097c1173ca249a41a4cca1ab9e15a697

You do NOT need to preserve the fparts.txt supplied with Intel FPT. The application ships its own validated/extended fparts.txt and unconditionally overwrites tools\fparts.txt with that exact file before every FPT compatibility probe, BIOS dump and BIOS flash operation.
