# Chinesium X99 SecureBoot Patcher v0.967

## Changes since v0.966

- Fixed the elevated BIOS helper result exchange. The normal GUI now creates
  both reply and event files before elevation. The helper updates those same
  files in place, preserving their identity and caller-created permissions,
  instead of creating and renaming an elevated replacement `result.json`.
  Results are consumed only after the helper process has exited.
- Temporary-file cleanup failures are logged separately and cannot override
  an operation result or hide the original operation error.
- Cancelled administrator approval, helper launch failures, inaccessible or
  missing result files, malformed results and helper operation failures now
  have separate diagnostic reasons. Logs include exception tracebacks and
  helper exit codes. Event-delivery errors do not abandon an active helper.
- FPT's driver error `-2146762484` / `0x800B010C` is identified as a revoked
  certificate/driver trust failure, rather than relying on FPT's misleading
  generic administrator-account instruction. No Windows security setting is
  changed automatically.
- Added a hardware-free packaged helper exchange test using the production
  GUI/CLI entry points and ShellExecute `runas` launch. This test is required
  before packaging. A Windows integration regression also uses a real medium
  integrity caller token and an elevated helper process to verify reply-file
  identity, readability and deletion across that permission boundary.
- Included `TEST-ELEVATED-HELPER.cmd` for testing the same packaged exchange
  on a user's PC. Run it normally and approve the helper's UAC request; it
  records whether the caller was elevated and exchanges a diagnostic message
  only. It does not probe, dump or flash the BIOS. The JSON report is saved
  in `LOGS/elevated-helper-test.json`.

The normal GUI retains Explorer drag-and-drop, exact-tool verification and
downloads, private Qt/Visual C++ runtime checks and both flash confirmations.
Keep the two EXEs together. Open the GUI normally.

The uploaded user logs established successful FPT information probes followed
by GUI helper-exchange failures. They did not contain a traceback or file ACL
dump establishing the exact Windows permission rule responsible. This update
removes elevated reply-file replacement and tests the exchange explicitly;
interactive Windows 11 UAC prompts still require testing on a user's PC.

No physical BIOS write is performed by any release-validation test.
