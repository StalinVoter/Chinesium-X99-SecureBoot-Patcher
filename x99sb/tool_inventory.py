"""Exact-file inventory and verified, atomic downloads of external tools."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import io
import os
from pathlib import Path
import tempfile
import time
from typing import Callable
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import zipfile

from .constants import (
    FPT_VERSION, FPT_FILE_SHA256, FPT_SOURCE_COMMIT,
    UEFIREPLACE_VERSION, UEFIREPLACE_SHA256, UEFIREPLACE_DOWNLOAD_URL,
    UEFIREPLACE_ARCHIVE_SHA256,
)
from .sessionlog import log
from .tools import app_directory, sha256_file


@dataclass(frozen=True)
class ToolSpec:
    name: str
    version: str
    sha256: str
    size: int
    url: str
    download_sha256: str
    download_size: int
    archive_member: str | None = None


_FPT_BASE = (
    f'https://raw.githubusercontent.com/CE1CECL/IntelCSTools/{FPT_SOURCE_COMMIT}/'
    'ME%20System%20Tools%20v9.1%20r7/Flash%20Programming%20Tool/WIN64/'
)
TOOL_SPECS = (
    ToolSpec('UEFIReplace.exe', UEFIREPLACE_VERSION, UEFIREPLACE_SHA256, 4898304,
             UEFIREPLACE_DOWNLOAD_URL, UEFIREPLACE_ARCHIVE_SHA256, 2059168, 'UEFIReplace.exe'),
    *(ToolSpec(name, FPT_VERSION, FPT_FILE_SHA256[name], size, _FPT_BASE + name,
               FPT_FILE_SHA256[name], size)
      for name, size in (('fptw64.exe', 1325016), ('pmxdll32e.DLL', 114176), ('idrvdll32e.DLL', 61952))),
)
TOOLS_BY_NAME = {spec.name: spec for spec in TOOL_SPECS}


def tool_status(spec: ToolSpec, folder: Path) -> dict:
    path = folder / spec.name
    try:
        if not path.exists():
            state, detail = 'missing', 'Missing'
        elif not path.is_file():
            state, detail = 'unreadable', 'Path is not a file'
        elif path.stat().st_size == spec.size and sha256_file(path) == spec.sha256:
            state, detail = 'ready', 'Exact required file verified'
        else:
            state, detail = 'wrong', 'Incorrect version or modified file'
    except OSError as exc:
        state, detail = 'unreadable', f'Cannot read file: {exc}'
    return {'name': spec.name, 'version': spec.version, 'state': state,
            'detail': detail, 'path': str(path)}


def scan_tools(folder: Path | None = None) -> list[dict]:
    folder = folder if folder is not None else app_directory() / 'tools'
    statuses = [tool_status(spec, folder) for spec in TOOL_SPECS]
    for status in statuses:
        log('TOOL INVENTORY', f"{status['path']}: {status['state']}; {status['detail']}")
    return statuses


def _download(spec: ToolSpec, progress: Callable[[str], None]) -> bytes:
    progress('Downloading…')
    log('TOOL DOWNLOAD', f'{spec.name}: {spec.url}')
    request = Request(spec.url, headers={'User-Agent': 'X99-SecureBoot-Patcher', 'Accept-Encoding': 'identity'})
    deadline = time.monotonic() + 120
    with urlopen(request, timeout=20) as response:
        if urlsplit(response.geturl()).scheme.lower() != 'https':
            raise RuntimeError('The download redirected to a non-HTTPS URL.')
        chunks = []
        size = 0
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError('The download exceeded two minutes. Please try again.')
            block = response.read(65536)
            if not block:
                break
            size += len(block)
            if size > spec.download_size:
                raise RuntimeError('The download is larger than the required file.')
            chunks.append(block)
    data = b''.join(chunks)
    if len(data) != spec.download_size or sha256(data).hexdigest() != spec.download_sha256:
        raise RuntimeError('The download failed its exact size/SHA-256 check. No file was installed.')
    return data


def install_tool(name: str, folder: Path | None = None,
                 progress: Callable[[str], None] | None = None) -> Path:
    spec = TOOLS_BY_NAME[name]  # The GUI can select only these fixed downloads.
    folder = folder if folder is not None else app_directory() / 'tools'
    notify = progress if progress is not None else lambda message: None
    destination = folder / spec.name
    if tool_status(spec, folder)['state'] == 'ready':
        notify('Already installed and verified')
        return destination
    temporary = None
    try:
        data = _download(spec, notify)
        notify('Verifying…')
        if spec.archive_member is not None:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = [entry for entry in archive.infolist() if entry.filename == spec.archive_member]
                if len(entries) != 1 or entries[0].file_size != spec.size:
                    raise RuntimeError('The archive does not contain the exact required executable.')
                data = archive.read(entries[0])  # Never extract paths from an archive.
        if len(data) != spec.size or sha256(data).hexdigest() != spec.sha256:
            raise RuntimeError('The tool failed its exact size/SHA-256 check. No file was installed.')
        folder.mkdir(parents=True, exist_ok=True)
        notify('Installing…')
        with tempfile.NamedTemporaryFile(dir=folder, prefix='.x99-download-', delete=False) as output:
            temporary = Path(output.name)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        if sha256_file(temporary) != spec.sha256:
            raise RuntimeError('The downloaded file could not be written correctly.')
        os.replace(temporary, destination)
        log('TOOL DOWNLOAD', f'Installed {destination}; SHA-256={spec.sha256}')
        notify('Installed and verified')
        return destination
    except Exception as exc:
        log('TOOL DOWNLOAD FAILED', f'{name}: {type(exc).__name__}: {exc}')
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
