from __future__ import annotations
from pathlib import Path
import shutil
import subprocess
import time

from .firmware import find_ffs_by_guid, find_enclosing_fv, parse_ffs_at, sha256_file
from .tools import run_tool


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
    if result.returncode != 0:
        raise RuntimeError(f'UEFIReplace failed with exit code {result.returncode}\n{diagnostic}')
    if not output_path.is_file():
        raise RuntimeError('UEFIReplace returned success without output file')
    output_data = output_path.read_bytes()
    if len(output_data) != len(input_data):
        raise RuntimeError(f'UEFIReplace changed image size {len(input_data)} -> {len(output_data)}')
    output_hits = find_ffs_by_guid(output_data, guid)
    if len(output_hits) != 1:
        raise RuntimeError(f'expected one target after replacement, found {len(output_hits)}')
    if output_hits[0].data != replacement_data:
        raise RuntimeError('post-write target FFS is not byte-identical to the validated donor')

    # Strong generic mutation boundary: a firmware-volume rebuild may alter pad
    # files/free space inside the containing FV, but must not alter the image
    # outside the outermost valid FV that contained the target.
    boundary = None
    if fv is not None:
        unexpected = [
            i for i, (a, b) in enumerate(zip(input_data, output_data))
            if a != b and not (fv.offset <= i < fv.end)
        ]
        if unexpected:
            raise RuntimeError(
                'UEFIReplace changed bytes outside the target firmware volume; '
                f'first unexpected offsets: {[hex(x) for x in unexpected[:16]]}'
            )
        boundary = {'offset': fv.offset, 'size': fv.size, 'end': fv.end}

    return {
        'skipped': False,
        'diagnostic': diagnostic,
        'old_offset': existing.offset,
        'new_offset': output_hits[0].offset,
        'old_size': existing.size,
        'new_size': output_hits[0].size,
        'fv_boundary': boundary,
    }
