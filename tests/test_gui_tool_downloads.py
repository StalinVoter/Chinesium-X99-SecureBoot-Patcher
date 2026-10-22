import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from hashlib import sha256
import io
import time

import pytest
pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from x99sb import gui, tool_inventory as inventory


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def wait(app, condition):
    deadline = time.monotonic() + 8
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert condition(), 'Qt worker did not complete'


@pytest.fixture
def window(app, monkeypatch, tmp_path):
    monkeypatch.setenv('X99_SECUREBOOT_PATCHER_HOME', str(tmp_path))
    monkeypatch.setattr(gui.MainWindow, '_tool_preflight', lambda self: None)
    calls = []
    def probe():
        calls.append('probe')
        return {'ready': False, 'reason': 'missing-files', 'message': 'fixture check'}
    monkeypatch.setattr(gui, 'probe_fpt', probe)  # Never access firmware in GUI tests.
    win = gui.MainWindow(); win.show()
    wait(app, lambda: not win._probe_running)
    yield win, calls
    wait(app, lambda: not win._download_running and not win._probe_running)
    win.close(); app.processEvents()


def test_empty_startup_shows_four_individual_download_buttons(window):
    win, calls = window
    assert len(win.tool_rows) == 4
    for label, button in win.tool_rows.values():
        assert label.text() == 'Missing'
        assert button.text() == 'Download this file'
        assert button.isEnabled()


@pytest.mark.parametrize('bad_download', [False, True])
def test_real_button_downloads_in_worker_and_refreshes_status(app, window, monkeypatch, tmp_path, bad_download):
    win, calls = window
    data = b'GUI downloaded fixture'
    digest = sha256(data).hexdigest()
    name = 'pmxdll32e.DLL'
    spec = inventory.ToolSpec(name, 'fixture', digest, len(data), 'https://example.invalid/pinned', digest, len(data))
    monkeypatch.setattr(inventory, 'TOOL_SPECS', (spec,))
    monkeypatch.setattr(inventory, 'TOOLS_BY_NAME', {name: spec})
    class Response(io.BytesIO):
        def geturl(self):
            return spec.url
    monkeypatch.setattr(inventory, 'urlopen', lambda *a, **k: Response(b'bad' if bad_download else data))
    warnings = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a: warnings.append(a[2]))
    folder = tmp_path / 'tools'; folder.mkdir()
    (folder / name).write_bytes(b'incorrect version')
    win._refresh_tools()
    label, button = win.tool_rows[name]
    assert 'Incorrect' in label.text()
    QTest.mouseClick(button, Qt.LeftButton)
    assert win._download_running
    assert not button.isEnabled()
    wait(app, lambda: not win._download_running and not win._probe_running)
    if bad_download:
        assert (folder / name).read_bytes() == b'incorrect version'
        assert warnings and button.isEnabled()
    else:
        assert (folder / name).read_bytes() == data
        assert label.text() == 'Ready'
        assert not button.isEnabled()
        assert len(calls) == 2  # Reprobe after installing an FPT companion.
        assert not warnings
