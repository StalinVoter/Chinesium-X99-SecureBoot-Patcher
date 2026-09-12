from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Callable, Any
import json
import shutil
import tempfile

from .constants import SECURE_BOOT_GUIDS
from .firmware import sha256_file
from .fit import inspect_fit, capture_fit_rebuild_reference, repair_fit_rebuild_damage
from .replacer import replace_ffs
from .secureboot import (
    inspect_secure_boot,
    load_bundled_donors,
    plan_secure_boot,
    secureboot_ffs_hashes,
)
from .tools import app_directory, discover_uefireplace, validate_uefireplace
from .sessionlog import logs_directory, log, log_json

Progress = Callable[[str, str], None]

@dataclass
class BuildResult:
    success: bool
    input_path: str
    output_path: str
    input_sha256: str
    output_sha256: str | None
    input_size: int
    output_size: int | None
    initial_secure_boot: dict[str, Any]
    plan: list[dict[str, Any]]
    steps: list[dict[str, Any]]
    final_secure_boot: dict[str, Any] | None
    fit_before: dict[str, Any]
    fit_after: dict[str, Any] | None
    fit_guard: dict[str, Any] | None
    error: str | None


def default_output(source: Path) -> Path:
    suffix = source.suffix or '.ROM'
    return source.with_name(source.stem + '_SB2023' + suffix)


def inspect_rom(path: Path) -> dict[str, Any]:
    path = path.resolve()
    log('ROM', f'Inspecting ROM: {path}')
    sb = inspect_secure_boot(path)
    fit = inspect_fit(path)
    report = {
        'path': str(path),
        'size': path.stat().st_size,
        'sha256': sha256_file(path),
        'secure_boot': sb,
        'fit': fit,
    }
    log_json('ROM', 'ROM inspection result', report)
    return report


def _log_step(steps: list[dict[str, Any]], progress: Progress | None, state: str, text: str) -> None:
    item = {'time': datetime.now().isoformat(timespec='seconds'), 'state': state, 'text': text}
    steps.append(item)
    log('BUILD', f'[{state}] {text}')
    if progress:
        progress(state, text)


def build_secureboot_rom(source: Path, output: Path, progress: Progress | None = None) -> BuildResult:
    source = source.resolve()
    output = output.resolve()
    steps: list[dict[str, Any]] = []
    initial_sb: dict[str, Any] = {}
    plan: list[dict[str, Any]] = []
    fit_before: dict[str, Any] = {}
    final_sb = None
    fit_after = None
    fit_guard = None
    input_hash = sha256_file(source)
    input_size = source.stat().st_size
    result: BuildResult | None = None
    log('BUILD', f'Secure Boot build requested: input={source} output={output}')
    log('BUILD', f'Input size={input_size} SHA-256={input_hash}')

    try:
        if source == output:
            raise ValueError('output path must be different from the input ROM')
        if input_size < 64 * 1024:
            raise ValueError('input is too small to be a firmware image')
        initial_sb = inspect_secure_boot(source)
        if not initial_sb.get('patchable'):
            raise ValueError('Secure Boot layout cannot be patched safely: ' + '; '.join(initial_sb.get('errors', [])))
        fit_before = inspect_fit(source)
        fit_rebuild_reference = capture_fit_rebuild_reference(source)
        _log_step(steps, progress, 'PASS', f'Input inspected: {input_size} bytes; Secure Boot structures are compatible')

        home = app_directory()
        donors = load_bundled_donors(home)
        tool = discover_uefireplace()
        if tool is None:
            raise FileNotFoundError('UEFIReplace.exe 0.28.0 is required. Download the official Windows archive from https://github.com/LongSoft/UEFITool/releases/download/0.28.0/UEFIReplace_0.28.0_win32.zip, then place UEFIReplace.exe in the tools folder.')
        validate_uefireplace(tool)
        plan = plan_secure_boot(initial_sb, donors)
        log_json('BUILD', 'Secure Boot patch plan', plan)
        patches = [x for x in plan if x['action'] == 'PATCH']
        if not patches:
            raise ValueError('This ROM already has the desired Secure Boot 2023 defaults; no output ROM is needed.')
        _log_step(steps, progress, 'PASS', 'Auto plan: ' + ', '.join(x['name'] for x in patches))

        initial_hashes = secureboot_ffs_hashes(source)

        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='X99-Secureboot-patcher-') as td:
            td = Path(td)
            work = td / 'work.rom'
            shutil.copy2(source, work)

            for index, item in enumerate(patches, 1):
                name = item['name']
                next_path = td / f'sb-{index}-{name}.rom'
                _log_step(steps, progress, 'RUNNING', f'Update {name}')
                rep = replace_ffs(work, donors[name], next_path, SECURE_BOOT_GUIDS[name], tool)
                shutil.copy2(next_path, work)
                current = inspect_secure_boot(work)
                if not current.get('patchable'):
                    raise RuntimeError(f'Secure Boot structures became invalid after {name}')
                donor_hash = item['donor_ffs_sha256']
                if current['variables'][name].get('ffs_sha256') != donor_hash:
                    raise RuntimeError(f'{name} does not match the validated donor after replacement')
                _log_step(
                    steps,
                    progress,
                    'PASS',
                    f'{name}: 0x{rep["old_size"]:X} -> 0x{rep["new_size"]:X}; donor verified',
                )

            shutil.copy2(work, output)

        if output.stat().st_size != input_size:
            raise RuntimeError('output image size does not match input image size')

        # Protect every Secure Boot variable that was not meant to change.
        final_hashes_pre_guard = secureboot_ffs_hashes(output)
        patched_names = {x['name'] for x in patches}
        for name in SECURE_BOOT_GUIDS:
            if name not in patched_names and final_hashes_pre_guard[name] != initial_hashes[name]:
                raise RuntimeError(f'{name} changed even though it was not a patch target')

        # Silent backend safeguard: if UEFIReplace moved microcode blobs, repair
        # only the resulting FIT pointer movement. A pre-existing stale
        # relationship is preserved at the same displacement; it is not turned
        # into a general-purpose FIT cleanup.
        try:
            fit_guard = repair_fit_rebuild_damage(output, fit_rebuild_reference)
        except Exception as exc:
            fit_guard = {
                'checked': True,
                'passed': False,
                'changed': False,
                'reason': 'selective rebuild repair failed',
                'technical_error': f'{type(exc).__name__}: {exc}',
            }
            # This message can surface in the GUI, so deliberately keep the
            # implementation detail invisible there.
            raise RuntimeError(
                'The Secure Boot rebuild altered firmware metadata in a way that could not be safely corrected.'
            ) from None
        fit_after = inspect_fit(output)

        final_sb = inspect_secure_boot(output)
        if not final_sb.get('patchable'):
            raise RuntimeError('final Secure Boot structures do not parse safely')
        if final_sb.get('has_ami_test_pk'):
            raise RuntimeError('final ROM still contains the AMI test PK')
        if not final_sb.get('has_complete_2023_set'):
            raise RuntimeError('final ROM does not contain the complete required 2023 KEK/db certificate set')

        # Re-check the patched FFS set after the silent rebuild safeguard so
        # the Secure Boot contents are exactly the same bytes that passed donor
        # verification above.
        final_hashes = secureboot_ffs_hashes(output)
        if final_hashes != final_hashes_pre_guard:
            raise RuntimeError('Secure Boot FFS contents changed after replacement validation')

        _log_step(steps, progress, 'PASS', 'Final Secure Boot 2023 validation passed; dbx preserved')
        _log_step(steps, progress, 'PASS', f'Output size preserved: {input_size} bytes')
        result = BuildResult(
            True, str(source), str(output), input_hash, sha256_file(output), input_size,
            output.stat().st_size, initial_sb, plan, steps, final_sb, fit_before, fit_after, fit_guard, None,
        )
    except Exception as exc:
        result = BuildResult(
            False, str(source), str(output), input_hash, sha256_file(output) if output.is_file() else None,
            input_size, output.stat().st_size if output.is_file() else None,
            initial_sb, plan, steps, final_sb, fit_before, fit_after, fit_guard,
            f'{type(exc).__name__}: {exc}',
        )

    log_json('BUILD', 'Secure Boot build summary', {
        'success': result.success,
        'output_sha256': result.output_sha256,
        'error': result.error,
    })
    write_reports(result)
    return result


def _report_paths(output: Path) -> tuple[Path, Path, Path]:
    root = logs_directory()
    base = output.name
    return (
        root / f'{base}.build.log',
        root / f'{base}.report.txt',
        root / f'{base}.report.json',
    )


def write_reports(result: BuildResult) -> None:
    output = Path(result.output_path)
    log_path, txt_path, json_path = _report_paths(output)
    data = asdict(result)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, indent=2), encoding='utf-8')
    lines = [
        'X99 Secureboot patcher build report',
        '===================================',
        '',
        f'Success: {result.success}',
        f'Input: {result.input_path}',
        f'Output: {result.output_path}',
        f'Input SHA-256: {result.input_sha256}',
        f'Output SHA-256: {result.output_sha256}',
        f'Input size: {result.input_size}',
        f'Output size: {result.output_size}',
        '',
        'Secure Boot plan:',
    ]
    for item in result.plan:
        lines.append(f"- [{item['action']}] {item['name']}: {item['reason']}")
    lines += ['', 'Steps:']
    for item in result.steps:
        lines.append(f"- [{item['state']}] {item['text']}")
    if result.error:
        lines += ['', 'ERROR:', result.error]
    txt_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    log_lines = [f"{x['time']} [{x['state']}] {x['text']}" for x in result.steps]
    if result.error:
        log_lines += [f"{datetime.now().isoformat(timespec='seconds')} [ERROR] {result.error}"]
    log_path.write_text('\n'.join(log_lines) + ('\n' if log_lines else ''), encoding='utf-8')
    log('BUILD', f'Wrote build log: {log_path}')
    log('BUILD', f'Wrote text report: {txt_path}')
    log('BUILD', f'Wrote JSON report: {json_path}')
