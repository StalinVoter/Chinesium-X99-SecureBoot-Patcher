from __future__ import annotations
from pathlib import Path
import shutil
import subprocess
import time

from .firmware import find_ffs_by_guid, find_enclosing_fv, parse_ffs_at, sha256_file
from .tools import run_tool
from .sessionlog import log


def _command_text(command: list[str]) -> str:
    return subprocess.list2cmdline(command)


def replace_ffs(
    input_path: Path,
    replacement_path: Path,
    output_path: Path,
    guid: str,
    uefireplace: Path,
) -> dict:
    input_data = input_path.read_bytes()
    hits = find_ffs_by_guid(input_data, guid)
    if len(hits) != 1:
        raise RuntimeError(f'expected exactly one target {guid}, found {len(hits)}')
    existing = hits[0]
    replacement_data = replacement_path.read_bytes()
    replacement = parse_ffs_at(replacement_data, 0, guid)
    if replacement.size != len(replacement_data):
        raise RuntimeError('replacement is not a standalone complete FFS')
    if existing.ffs_type != replacement.ffs_type:
        raise RuntimeError(f'FFS type mismatch {existing.ffs_type:02X}!={replacement.ffs_type:02X}')
    if existing.data == replacement.data:
        log('UEFIREPLACE', f'{guid}: target already byte-identical; UEFIReplace invocation skipped')
        shutil.copy2(input_path, output_path)
        return {
            'skipped': True,
            'reason': 'target FFS already byte-identical to replacement',
            'diagnostic': 'UEFIReplace was not invoked because the target is already current.',
            'old_offset': existing.offset,
            'new_offset': existing.offset,
            'old_size': existing.size,
            'new_size': existing.size,
            'fv_boundary': None,
        }

    fv = find_enclosing_fv(input_data, existing.offset)
    subtype = f'{existing.ffs_type:02X}'
    command = [str(uefireplace), str(input_path), guid, subtype, str(replacement_path), '-o', str(output_path), '-asis']
    started = time.monotonic()
    result = run_tool(command, cwd=input_path.parent)
    elapsed = time.monotonic() - started
    diagnostic = (
        f'Command: {_command_text(command)}\n'
        f'Working directory: {input_path.parent}\n'
        f'Elapsed: {elapsed:.3f}s\n'
        f'Exit code: {result.returncode}\n'
        f'GUID: {guid}\nSubtype: 0x{subtype}\n'
        f'Old offset/size: 0x{existing.offset:X}/0x{existing.size:X}\n'
        f'Replacement size: 0x{replacement.size:X}\n'
        f'Input SHA-256: {sha256_file(input_path)}\nReplacement SHA-256: {sha256_file(replacement_path)}\n\n'
        f'Output:\n{result.stdout}'
    )
    log('UEFIREPLACE', f'{guid}: elapsed={elapsed:.3f}s; target=0x{existing.offset:X}/0x{existing.size:X}; replacement_size=0x{replacement.size:X}; input_sha256={sha256_file(input_path)}; replacement_sha256={sha256_file(replacement_path)}')
    if result.returncode != 0:
        raise RuntimeError(f'UEFIReplace failed with exit code {result.returncode}; see the session log for the complete tool output')
    if not output_path.is_file():
        raise RuntimeError('UEFIReplace returned success without output file')
    raw_output_data = output_path.read_bytes()
    if len(raw_output_data) != len(input_data):
        raise RuntimeError(f'UEFIReplace changed image size {len(input_data)} -> {len(raw_output_data)}')
    raw_output_hits = find_ffs_by_guid(raw_output_data, guid)
    if len(raw_output_hits) != 1:
        raise RuntimeError(f'expected one target after replacement, found {len(raw_output_hits)}')
    if raw_output_hits[0].data != replacement_data:
        raise RuntimeError('post-write target FFS is not byte-identical to the validated donor')

    # UEFIReplace 0.28.0 rebuilds the requested firmware volume, but on some
    # real X99 images it also clears non-empty pad-file bytes in *other* firmware
    # volumes.  Those unrelated mutations are never part of a Secure Boot update.
    #
    # Fail closed unless we can identify the target's outermost containing FV.
    # Then use UEFIReplace only as the producer of that rebuilt FV: start from
    # the exact original image and transplant only the target FV byte range.
    # This preserves board/NVRAM/reset-vector/pad contents everywhere else.
    if fv is None:
        raise RuntimeError('could not establish a firmware-volume boundary for the Secure Boot target')

    raw_fv = find_enclosing_fv(raw_output_data, raw_output_hits[0].offset)
    if raw_fv is None:
        raise RuntimeError('UEFIReplace output no longer contains a structurally valid target firmware volume')
    if (raw_fv.offset, raw_fv.size, raw_fv.end) != (fv.offset, fv.size, fv.end):
        raise RuntimeError(
            'UEFIReplace changed the target firmware-volume boundary; '
            f'input=0x{fv.offset:X}-0x{fv.end:X}, output=0x{raw_fv.offset:X}-0x{raw_fv.end:X}'
        )

    outside_changes = [
        i for i, (a, b) in enumerate(zip(input_data, raw_output_data))
        if a != b and not (fv.offset <= i < fv.end)
    ]
    if outside_changes:
        sanitized = bytearray(input_data)
        sanitized[fv.offset:fv.end] = raw_output_data[fv.offset:fv.end]
        output_data = bytes(sanitized)
        output_path.write_bytes(output_data)
        log(
            'UEFIREPLACE',
            f'{guid}: contained rebuild to target FV 0x{fv.offset:X}-0x{fv.end:X}; '
            f'preserved {len(outside_changes)} unrelated byte change(s) outside it; '
            f'first raw offsets={[hex(x) for x in outside_changes[:16]]}',
        )
    else:
        output_data = raw_output_data
        log('UEFIREPLACE', f'{guid}: raw rebuild already stayed inside target FV 0x{fv.offset:X}-0x{fv.end:X}')

    # Re-validate the *accepted* image after containment, never the unsanitized
    # helper-tool output.  The donor must still be exact and the FV boundary must
    # be unchanged; every byte outside that FV must be original input data.
    output_hits = find_ffs_by_guid(output_data, guid)
    if len(output_hits) != 1:
        raise RuntimeError(f'expected one target after contained rebuild, found {len(output_hits)}')
    if output_hits[0].data != replacement_data:
        raise RuntimeError('contained rebuild target FFS is not byte-identical to the validated donor')
    accepted_fv = find_enclosing_fv(output_data, output_hits[0].offset)
    if accepted_fv is None or (accepted_fv.offset, accepted_fv.size, accepted_fv.end) != (fv.offset, fv.size, fv.end):
        raise RuntimeError('contained rebuild did not preserve the validated target firmware-volume boundary')
    unexpected = [
        i for i, (a, b) in enumerate(zip(input_data, output_data))
        if a != b and not (fv.offset <= i < fv.end)
    ]
    if unexpected:
        raise RuntimeError(
            'contained rebuild still changed bytes outside the target firmware volume; '
            f'first unexpected offsets: {[hex(x) for x in unexpected[:16]]}'
        )

    boundary = {
        'offset': fv.offset,
        'size': fv.size,
        'end': fv.end,
        'external_changes_restored': len(outside_changes),
    }
    log('UEFIREPLACE', f'{guid}: mutation boundary verified: FV 0x{fv.offset:X}-0x{fv.end:X} (0x{fv.size:X} bytes)')
    log('UEFIREPLACE', f'{guid}: replacement verified successfully at 0x{output_hits[0].offset:X}')
    return {
        'skipped': False,
        'diagnostic': diagnostic,
        'old_offset': existing.offset,
        'new_offset': output_hits[0].offset,
        'old_size': existing.size,
        'new_size': output_hits[0].size,
        'fv_boundary': boundary,
    }
