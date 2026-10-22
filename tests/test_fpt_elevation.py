from dataclasses import asdict
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from x99sb import fpt, fpt_elevation as elevation


def test_source_helper_command_uses_cli_entrypoint(tmp_path):
    request = tmp_path / 'request with spaces.json'
    executable, args = elevation.helper_command(request)
    assert executable.is_file()
    assert args[0].endswith('X99SecurebootPatcher-CLI.py')
    assert args[1:] == ['--fpt-helper', str(request)]


def test_frozen_helper_command_requires_companion_cli(monkeypatch, tmp_path):
    monkeypatch.setattr(elevation.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(elevation, 'app_directory', lambda: tmp_path)
    with pytest.raises(FileNotFoundError, match='CLI.exe'):
        elevation.helper_command(tmp_path / 'request.json')
    cli = tmp_path / 'X99-Secureboot-patcher-CLI.exe'; cli.touch()
    executable, args = elevation.helper_command(tmp_path / 'request.json')
    assert executable == cli
    assert args[0] == '--fpt-helper'


def test_helper_transport_reassembles_events_and_preserves_backup_location(monkeypatch, tmp_path):
    backup = tmp_path / 'original user Documents' / 'BIOS Backups'
    monkeypatch.setattr(fpt, 'backup_directory', lambda: backup)
    received = []
    def fake_wait(executable, args, poll):
        request = Path(args[-1]); body = json.loads(request.read_text())
        assert body['backup_directory'] == str(backup)
        events = request.parent / 'events.jsonl'
        events.write_text('{"type":"transcript","text":"first')
        poll()
        assert not received
        with events.open('a') as stream:
            stream.write(' line"}\n{"type":"status","text":"done"}\n')
        poll()
        (request.parent / 'result.json').write_text(json.dumps({'completed': True, 'result': {'ready': True}}))
        return 0
    monkeypatch.setattr(elevation, '_wait_elevated', fake_wait)
    assert elevation.run_elevated('probe', callback=received.append) == {'ready': True}
    assert [event['text'] for event in received] == ['first line', 'done']


def test_cancelled_elevation_is_reported_without_local_probe(monkeypatch, tmp_path):
    monkeypatch.setattr(fpt, 'validate_fpt_installation', lambda: {'ready': True})
    monkeypatch.setattr(fpt, 'needs_elevation', lambda: True)
    def cancel(*a, **k):
        raise RuntimeError('Administrator permission was cancelled')
    monkeypatch.setattr(fpt, 'run_elevated', cancel)
    monkeypatch.setattr(fpt, '_run_fpt', lambda *a, **k: pytest.fail('local hardware access'))
    assert fpt.probe_fpt()['reason'] == 'administrator-permission'
    assert not fpt.dump_bios(tmp_path / 'dump.ROM').success
    monkeypatch.setattr(fpt, '_write_flash_report', lambda result: None)
    result = fpt.flash_bios_with_recovery(tmp_path / 'target.ROM')
    assert not result.success and not result.recovery_attempted


def test_helper_dispatches_complete_flash_workflow_and_streams_events(monkeypatch, tmp_path):
    monkeypatch.setattr(elevation, 'os', SimpleNamespace(name='nt', environ={}))
    monkeypatch.setattr(elevation, 'needs_elevation', lambda: False)
    target = tmp_path / 'target.ROM'
    backup = tmp_path / 'user backups'
    request = tmp_path / 'request.json'
    request.write_text(json.dumps({'action': 'flash', 'path': str(target), 'backup_directory': str(backup)}))
    expected = fpt.FlashResult(True, str(target), str(backup / 'original.ROM'), 'hash', {}, False, None, None, {}, None)
    def flash(path, callback):
        assert path == target
        assert elevation.os.environ['X99_SECUREBOOT_BACKUP_DIR'] == str(backup)
        callback({'type': 'status', 'text': 'fixture flash workflow'})
        return expected
    monkeypatch.setattr(fpt, 'flash_bios_with_recovery', flash)
    assert elevation.helper_main(request) == 0
    result = json.loads((tmp_path / 'result.json').read_text())
    assert result['result'] == asdict(expected)
    assert json.loads((tmp_path / 'events.jsonl').read_text())['text'] == 'fixture flash workflow'
