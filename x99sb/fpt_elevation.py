"""Keep the GUI at Explorer's integrity level; elevate only BIOS access."""
from __future__ import annotations
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from .sessionlog import log
from .tools import app_directory


def needs_elevation() -> bool:
    if os.name != 'nt':
        return False
    import ctypes
    return not bool(ctypes.windll.shell32.IsUserAnAdmin())


def helper_command(request: Path) -> tuple[Path, list[str]]:
    if getattr(sys, 'frozen', False):
        executable = app_directory() / 'X99-Secureboot-patcher-CLI.exe'
        if not executable.is_file():
            raise FileNotFoundError('BIOS access needs X99-Secureboot-patcher-CLI.exe beside the GUI executable.')
        return executable, ['--fpt-helper', str(request)]
    entrypoint = Path(__file__).resolve().parents[1] / 'X99SecurebootPatcher-CLI.py'
    return Path(sys.executable), [str(entrypoint), '--fpt-helper', str(request)]


def _wait_elevated(executable: Path, arguments: list[str], poll) -> int:
    import ctypes
    from ctypes import wintypes
    from .nativeprocess import external_dll_search

    class ExecuteInfo(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.DWORD), ('fMask', wintypes.ULONG),
                    ('hwnd', wintypes.HWND), ('lpVerb', wintypes.LPCWSTR),
                    ('lpFile', wintypes.LPCWSTR), ('lpParameters', wintypes.LPCWSTR),
                    ('lpDirectory', wintypes.LPCWSTR), ('nShow', ctypes.c_int),
                    ('hInstApp', wintypes.HINSTANCE), ('lpIDList', ctypes.c_void_p),
                    ('lpClass', wintypes.LPCWSTR), ('hkeyClass', wintypes.HKEY),
                    ('dwHotKey', wintypes.DWORD), ('hIcon', wintypes.HANDLE),
                    ('hProcess', wintypes.HANDLE)]

    shell = ctypes.WinDLL('shell32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    ole = ctypes.WinDLL('ole32')
    shell.ShellExecuteExW.argtypes = [ctypes.POINTER(ExecuteInfo)]
    shell.ShellExecuteExW.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole.CoInitializeEx.restype = ctypes.c_long
    initialized = ole.CoInitializeEx(None, 2) in (0, 1)
    info = ExecuteInfo()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x40 | 0x100 | 0x400  # Process handle, synchronous activation, no shell error UI.
    info.lpVerb = 'runas'
    info.lpFile = str(executable)
    info.lpParameters = subprocess.list2cmdline(arguments)
    info.lpDirectory = str(app_directory())
    info.nShow = 0
    try:
        with external_dll_search():
            if not shell.ShellExecuteExW(ctypes.byref(info)):
                error = ctypes.get_last_error()
                if error == 1223:
                    raise RuntimeError('Administrator permission was cancelled. BIOS access was not started.')
                raise ctypes.WinError(error)
        if not info.hProcess:
            raise RuntimeError('Windows did not return a BIOS helper process handle.')
        try:
            while True:
                state = kernel.WaitForSingleObject(info.hProcess, 100)
                poll()
                if state == 0:
                    break
                if state != 258:
                    raise ctypes.WinError(ctypes.get_last_error())
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(info.hProcess, ctypes.byref(code)):
                raise ctypes.WinError(ctypes.get_last_error())
            return code.value
        finally:
            kernel.CloseHandle(info.hProcess)
    finally:
        if initialized:
            ole.CoUninitialize()


def run_elevated(action: str, path: Path | None = None, callback=None) -> dict:
    if action not in ('probe', 'dump', 'flash'):
        raise ValueError('Unsupported BIOS helper action.')
    log('BIOS HELPER', f'Requesting administrator permission for {action}')
    # The helper is never killed on a timeout: a flash/recovery must finish.
    with tempfile.TemporaryDirectory(prefix='X99-BIOS-access-') as temporary:
        from .fpt import backup_directory
        root = Path(temporary)
        request = root / 'request.json'
        events = root / 'events.jsonl'
        result = root / 'result.json'
        events.touch()
        request.write_text(json.dumps({'action': action, 'path': str(path.resolve()) if path else None,
                                       'backup_directory': str(backup_directory())}), encoding='utf-8')
        executable, arguments = helper_command(request)
        with events.open(encoding='utf-8') as reader:
            pending = ''
            def poll():
                nonlocal pending
                pending += reader.read()
                while '\n' in pending:
                    line, pending = pending.split('\n', 1)
                    if line:
                        event = json.loads(line)
                        if callback:
                            callback(event)
                        if event.get('type') == 'transcript':
                            log('FPT HELPER', event.get('text', ''))
            code = _wait_elevated(executable, arguments, poll)
            poll()
        if not result.is_file():
            raise RuntimeError(f'The BIOS access helper returned no result (exit code {code}).')
        envelope = json.loads(result.read_text(encoding='utf-8'))
        if not envelope.get('completed') or code != 0:
            raise RuntimeError(envelope.get('error', f'BIOS access helper failed (exit code {code}).'))
        log('BIOS HELPER', f'{action} helper completed')
        if envelope.get('session_log'):
            log('BIOS HELPER', f"Detailed helper session log: {envelope['session_log']}")
        return envelope['result']


def helper_main(request_path: Path) -> int:
    root = request_path.resolve().parent
    result_path = root / 'result.json'
    envelope = {'completed': False}
    try:
        if os.name != 'nt' or needs_elevation():
            raise RuntimeError('The BIOS helper requires administrator permission on Windows.')
        request = json.loads(request_path.read_text(encoding='utf-8'))
        os.environ['X99_SECUREBOOT_BACKUP_DIR'] = request['backup_directory']
        from . import fpt
        with (root / 'events.jsonl').open('a', encoding='utf-8') as stream:
            def emit(event):
                stream.write(json.dumps(event) + '\n')
                stream.flush()
            action = request['action']
            if action == 'probe':
                result = fpt.probe_fpt(emit)
            elif action == 'dump':
                result = asdict(fpt.dump_bios(Path(request['path']), emit))
            elif action == 'flash':
                result = asdict(fpt.flash_bios_with_recovery(Path(request['path']), emit))
            else:
                raise ValueError('Unsupported BIOS helper action.')
        from .sessionlog import session_log_path
        envelope = {'completed': True, 'result': result, 'session_log': str(session_log_path())}
    except Exception as exc:
        envelope['error'] = f'{type(exc).__name__}: {exc}'
        log('BIOS HELPER FAILED', envelope['error'])
    temporary = result_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(envelope), encoding='utf-8')
    temporary.replace(result_path)
    return 0 if envelope['completed'] else 2
