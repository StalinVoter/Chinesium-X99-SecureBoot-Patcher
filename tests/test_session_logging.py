from __future__ import annotations

from pathlib import Path

from x99sb import pipeline
from x99sb import sessionlog

ROOT = Path(__file__).resolve().parents[1]


def test_session_log_is_created_in_logs_folder_at_app_home(monkeypatch, tmp_path):
    sessionlog.finish_session_log('reset before test')
    monkeypatch.setenv('X99_SECUREBOOT_PATCHER_HOME', str(tmp_path))
    path = sessionlog.start_session_log('0.964', 'Test Patcher')
    sessionlog.log('TEST', 'hello from session')
    sessionlog.finish_session_log('test complete')
    assert path.parent == tmp_path / 'LOGS'
    assert path.is_file()
    text = path.read_text(encoding='utf-8')
    assert 'Test Patcher v0.964 session started' in text
    assert '[TEST] hello from session' in text
    assert 'Session ended: test complete' in text


def test_secureboot_build_reports_are_routed_to_logs_folder(monkeypatch, tmp_path):
    monkeypatch.setenv('X99_SECUREBOOT_PATCHER_HOME', str(tmp_path))
    output = tmp_path / 'elsewhere' / 'board_SB2023.ROM'
    build_log, report_txt, report_json = pipeline._report_paths(output)
    assert build_log == tmp_path / 'LOGS' / 'board_SB2023.ROM.build.log'
    assert report_txt == tmp_path / 'LOGS' / 'board_SB2023.ROM.report.txt'
    assert report_json == tmp_path / 'LOGS' / 'board_SB2023.ROM.report.json'


def test_gui_starts_session_log_before_main_window():
    text = (ROOT / 'x99sb' / 'gui.py').read_text(encoding='utf-8')
    main = text[text.index('def main() -> int:'):]
    assert 'start_session_log(__version__, APP_TITLE)' in main
    assert main.index('start_session_log(__version__, APP_TITLE)') < main.index('MainWindow()')
    assert "app.aboutToQuit.connect" in main


def test_session_log_records_raw_tool_output_once_and_avoids_result_replay():
    fpt = (ROOT / 'x99sb' / 'fpt.py').read_text(encoding='utf-8')
    tools = (ROOT / 'x99sb' / 'tools.py').read_text(encoding='utf-8')
    pipeline_text = (ROOT / 'x99sb' / 'pipeline.py').read_text(encoding='utf-8')
    gui_text = (ROOT / 'x99sb' / 'gui.py').read_text(encoding='utf-8')
    replacer_text = (ROOT / 'x99sb' / 'replacer.py').read_text(encoding='utf-8')

    # Raw external output remains authoritative and complete.
    assert "log('FPT OUTPUT', f'[{group}] {record}')" in fpt
    assert "log_block('MEMORY INTEGRITY', 'PowerShell stdout/stderr'" in fpt
    assert "log_block('TOOL', 'stdout/stderr', decoded)" in tools

    # The same FPT progress line is not logged again as a derived progress event.
    assert "log('FPT PROGRESS'" not in fpt

    # Launch probe is summarized once without re-serializing its transcript.
    assert "log_json('FPT PREFLIGHT', 'Launch-time FPT probe result'" not in fpt
    assert "FPT probe delivered to GUI" not in gui_text
    assert "run = _run_fpt(['-i'], 'FPT compatibility probe', callback, timeout=60, prevalidated=True)" in fpt

    # Operation summaries contain workflow-level results only; raw run/transcript fields are not replayed.
    assert "'run':" not in fpt[fpt.index('def _log_dump_summary'):fpt.index('def _log_backup_summary')]
    assert "'first_run':" not in fpt[fpt.index('def _log_backup_summary'):fpt.index('def _log_flash_summary')]
    assert "'flash_run':" not in fpt[fpt.index('def _log_flash_summary'):fpt.index('def _dump_once')]
    assert "Manual BIOS dump summary" in fpt
    assert "Verified backup summary" in fpt
    assert "Flash workflow summary" in fpt

    # UEFIReplace raw stdout/stderr is owned by run_tool and is not replayed by replacer/pipeline.
    assert "log_block('UEFIREPLACE'" not in replacer_text
    assert "UEFIReplace result for" not in pipeline_text

    # ROM inspection/plan remain present, while final build logging is concise.
    assert "log_json('ROM', 'ROM inspection result', report)" in pipeline_text
    assert "log_json('BUILD', 'Secure Boot patch plan', plan)" in pipeline_text
    assert "Secure Boot build summary" in pipeline_text
    assert "Secure Boot build final result" not in pipeline_text

