from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import locale
import os
import subprocess
import sys

from .constants import UEFIREPLACE_SHA256, UEFIREPLACE_DOWNLOAD_URL

@dataclass(frozen=True)
class ToolPaths:
    uefireplace: Path | None


def app_directory() -> Path:
    override = os.environ.get('X99_SECUREBOOT_PATCHER_HOME')
    if override:
        return Path(override).resolve()
    return Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent


def sha256_file(path: Path) -> str:
    h = sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def discover_uefireplace() -> Path | None:
    base = app_directory()
    source = Path(__file__).resolve().parent.parent
    for folder in (base / 'tools', base, source / 'tools', source):
        p = folder / 'UEFIReplace.exe'
        if p.is_file():
            return p.resolve()
    return None


def validate_uefireplace(path: Path) -> None:
    digest = sha256_file(path)
    if digest != UEFIREPLACE_SHA256:
        raise ValueError(
            'UEFIReplace.exe is not the required official 0.28.0 Windows binary: '
            f'{digest} != {UEFIREPLACE_SHA256}. Download the exact required build from {UEFIREPLACE_DOWNLOAD_URL}'
        )


def _decode(data: bytes) -> str:
    enc = locale.getpreferredencoding(False) or 'utf-8'
    try:
        return data.decode(enc, errors='replace')
    except LookupError:
        return data.decode('utf-8', errors='replace')


def run_tool(args: list[str], cwd: Path | None = None, timeout: int = 300) -> subprocess.CompletedProcess:
    creationflags = 0
    startupinfo = None
    if os.name == 'nt':
        creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
    proc = subprocess.Popen(
        args,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
        startupinfo=startupinfo,
    )
    try:
        output, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        output, _ = proc.communicate()
        raise subprocess.TimeoutExpired(args, timeout, output=_decode(output or b'')) from exc
    return subprocess.CompletedProcess(args, proc.returncode, _decode(output or b''), None)
