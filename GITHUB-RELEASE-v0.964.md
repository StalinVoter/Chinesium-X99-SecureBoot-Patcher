# Chinesium X99 SecureBoot Patcher v0.964

v0.964 fixes the live FPT progress display during BIOS flashing.

FPT reports a changing cursor address while a single erase or program operation
moves from 0 to 100%. Earlier builds incorrectly treated those addresses as
separate progress phases, creating a large stack of bars. v0.964 uses one bar
for each continuous read/erase/program/verify pass, while still creating a new
bar if FPT genuinely starts another pass and the percentage resets.

All firmware-patching, backup, verification and recovery behavior is unchanged.
