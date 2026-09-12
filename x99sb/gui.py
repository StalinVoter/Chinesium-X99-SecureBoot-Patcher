from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

from PySide6.QtCore import QObject, QThread, Signal, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QTextEdit, QVBoxLayout, QWidget,
    QDialog,
)

from .fpt import (
    FPT_SOURCE_FOLDER_URL,
    FPT_VERSION,
    backup_directory,
    dump_bios,
    flash_bios_with_recovery,
    probe_fpt,
    validate_fpt_installation,
)
from .pipeline import inspect_rom, build_secureboot_rom, default_output
from .buildprogress import BuildProgressTracker
from .secureboot import load_bundled_donors
from .tools import app_directory, discover_uefireplace, validate_uefireplace, sha256_file
from .sessionlog import start_session_log, finish_session_log, install_exception_hook, log
from . import __version__

APP_TITLE = 'X99 Secureboot patcher'

STYLE = r'''
QMainWindow { background: #f4f5f7; }
QWidget { font-family: "Segoe UI"; font-size: 10pt; color: #202124; }
QLabel#appTitle { font-size: 23pt; font-weight: 700; color: #111827; }
QLabel#subtitle { color: #5f6368; font-size: 10.5pt; }
QLabel#sectionTitle { font-size: 15pt; font-weight: 650; color: #111827; }
QFrame#card { background: white; border: 1px solid #dfe3e8; border-radius: 11px; }
QPushButton { background: white; border: 1px solid #c9ced6; border-radius: 7px; padding: 8px 14px; }
QPushButton:hover { background: #f5f7f9; }
QPushButton#primary { background: #1a73e8; border-color: #1a73e8; color: white; font-weight: 650; padding: 10px 18px; }
QPushButton#primary:hover { background: #1765cc; }
QPushButton#danger { background: #b3261e; border-color: #b3261e; color: white; font-weight: 650; }
QPushButton#danger:hover { background: #951f19; }
QLineEdit { background: white; border: 1px solid #cbd0d7; border-radius: 6px; padding: 7px; }
QTextEdit { background: #111827; color: #e5e7eb; border: 1px solid #2f3747; border-radius: 7px; font-family: Consolas; font-size: 9pt; }
QProgressBar { border: 1px solid #cbd0d7; border-radius: 5px; background: #f2f4f7; text-align: center; height: 18px; }
QProgressBar::chunk { background: #1a73e8; border-radius: 4px; }
'''


def _badge(text: str, kind: str) -> QLabel:
    label = QLabel(text)
    colors = {
        'good': ('#eaf6ed', '#226a36', '#b9ddc2'),
        'warn': ('#fff4d6', '#795600', '#ead391'),
        'bad': ('#fde8e8', '#9a2929', '#ebbbbb'),
        'muted': ('#f0f2f4', '#5f6368', '#d8dce1'),
    }
    bg, fg, border = colors[kind]
    label.setStyleSheet(f'background:{bg};color:{fg};border:1px solid {border};border-radius:9px;padding:3px 8px;font-weight:600;')
    label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
    return label


def _choose_firmware_file(parent: QWidget, start_dir: str = '', title: str = 'Open firmware image') -> str | None:
    dialog = QFileDialog(parent, title, start_dir)
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
    dialog.setNameFilters(['Firmware images (*.rom *.ROM *.bin *.BIN)', 'All files (*.*)'])
    if not dialog.exec():
        return None
    files = dialog.selectedFiles()
    return files[0] if files else None


def _choose_dump_output(parent: QWidget) -> str | None:
    root = backup_directory().parent
    root.mkdir(parents=True, exist_ok=True)
    default_name = f'BIOS-Dump-{datetime.now().strftime("%Y%m%d-%H%M%S")}.ROM'
    dialog = QFileDialog(parent, 'Save BIOS dump', str(root))
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
    dialog.setFileMode(QFileDialog.FileMode.AnyFile)
    dialog.setNameFilters(['Firmware image (*.ROM *.rom *.BIN *.bin)', 'All files (*.*)'])
    dialog.selectFile(default_name)
    if not dialog.exec():
        return None
    files = dialog.selectedFiles()
    return files[0] if files else None


class DropPanel(QFrame):
    fileDropped = Signal(str)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName('card')
        self.setStyleSheet('QFrame#card{background:white;border:2px dashed #b8c1cc;border-radius:12px;}')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 26, 28, 26)
        title = QLabel('Drop a BIOS / ROM file here')
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet('font-size:14pt;font-weight:650;')
        sub = QLabel('or choose a .ROM / .BIN file manually')
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet('color:#6b7280;')
        self.open_btn = QPushButton('Open ROM…')
        self.open_btn.setFixedWidth(150)
        self.open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_btn.clicked.connect(self._browse)
        row = QHBoxLayout(); row.addStretch(); row.addWidget(self.open_btn); row.addStretch()
        lay.addWidget(title); lay.addWidget(sub); lay.addLayout(row)

    def _browse(self):
        path = _choose_firmware_file(self)
        if path:
            self.fileDropped.emit(path)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls() and len(event.mimeData().urls()) == 1:
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            self.fileDropped.emit(urls[0].toLocalFile())
            event.acceptProposedAction()


class BuildWorker(QObject):
    progress = Signal(str, str, int)
    finished = Signal(object)

    def __init__(self, source: Path, output: Path, targets: list[str]):
        super().__init__()
        self.source = source
        self.output = output
        self.tracker = BuildProgressTracker(targets)

    def _on_progress(self, state: str, text: str) -> None:
        self.progress.emit(state, text, self.tracker.update(state, text))

    def run(self):
        result = build_secureboot_rom(self.source, self.output, self._on_progress)
        self.finished.emit(result)


class FptProbeWorker(QObject):
    finished = Signal(object)

    def run(self):
        self.finished.emit(probe_fpt())


class FptWorker(QObject):
    event = Signal(object)
    finished = Signal(object)

    def __init__(self, mode: str, path: Path):
        super().__init__()
        self.mode = mode
        self.path = path

    def run(self):
        callback = lambda event: self.event.emit(event)
        if self.mode == 'dump':
            result = dump_bios(self.path, callback)
        else:
            result = flash_bios_with_recovery(self.path, callback)
        self.finished.emit(result)


class FptOperationDialog(QDialog):
    def __init__(self, parent: QWidget, mode: str, path: Path):
        super().__init__(parent)
        self.mode = mode
        self.path = path
        self.result = None
        self.running = True
        self.thread: QThread | None = None
        self.worker: FptWorker | None = None
        self.phase_widgets: dict[tuple[str, str], tuple[QLabel, QProgressBar]] = {}
        self.group_layouts: dict[str, QVBoxLayout] = {}
        self.setWindowTitle('Dump BIOS' if mode == 'dump' else 'Flash BIOS')
        self.resize(820, 680)
        self.setMinimumSize(700, 560)
        self.setStyleSheet(STYLE)

        lay = QVBoxLayout(self); lay.setContentsMargins(20, 18, 20, 18); lay.setSpacing(10)
        title = QLabel('Dumping BIOS' if mode == 'dump' else 'Flashing BIOS')
        title.setObjectName('sectionTitle'); lay.addWidget(title)
        self.status = QLabel('Starting…'); self.status.setWordWrap(True); lay.addWidget(self.status)

        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        self.phase_host = QWidget(); self.phase_layout = QVBoxLayout(self.phase_host); self.phase_layout.setContentsMargins(0, 0, 4, 0); self.phase_layout.setSpacing(9); self.phase_layout.addStretch(1)
        scroll.setWidget(self.phase_host); scroll.setMinimumHeight(230); lay.addWidget(scroll, 1)

        log_title = QLabel('FPT log'); log_title.setStyleSheet('font-weight:650;'); lay.addWidget(log_title)
        self.log = QTextEdit(); self.log.setReadOnly(True); self.log.setMinimumHeight(210); lay.addWidget(self.log, 1)
        self.close_btn = QPushButton('Close'); self.close_btn.setEnabled(False); self.close_btn.clicked.connect(self.accept)
        row = QHBoxLayout(); row.addStretch(); row.addWidget(self.close_btn); lay.addLayout(row)

        self.thread = QThread(self)
        self.worker = FptWorker(mode, path)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.event.connect(self._event)
        self.worker.finished.connect(self._finished)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def _ensure_group(self, group: str) -> QVBoxLayout:
        if group in self.group_layouts:
            return self.group_layouts[group]
        # insert before the stretch
        card = QFrame(); card.setObjectName('card')
        gl = QVBoxLayout(card); gl.setContentsMargins(12, 10, 12, 10); gl.setSpacing(7)
        heading = QLabel(group); heading.setStyleSheet('font-weight:650;')
        gl.addWidget(heading)
        self.phase_layout.insertWidget(max(0, self.phase_layout.count() - 1), card)
        self.group_layouts[group] = gl
        return gl

    def _event(self, event: dict):
        typ = event.get('type')
        if typ == 'status':
            self.status.setText(event.get('text', ''))
            return
        if typ == 'transcript':
            self.log.moveCursor(QTextCursor.MoveOperation.End)
            self.log.insertPlainText(event.get('text', '') + '\n')
            self.log.ensureCursorVisible()
            return
        if typ == 'group':
            self._ensure_group(event.get('name', 'FPT operation'))
            return
        if typ == 'phase':
            group = event.get('group', 'FPT operation')
            key = event.get('key', 'phase')
            ident = (group, key)
            if ident not in self.phase_widgets:
                gl = self._ensure_group(group)
                label = QLabel(event.get('label', key))
                bar = QProgressBar(); bar.setRange(0, 100); bar.setValue(0); bar.setFormat('%p%')
                gl.addWidget(label); gl.addWidget(bar)
                self.phase_widgets[ident] = (label, bar)
            label, bar = self.phase_widgets[ident]
            label.setText(event.get('label', key))
            bar.setValue(int(event.get('percent', 0)))
            return
        if typ == 'process_end':
            group = event.get('group', '')
            if not event.get('success'):
                self.status.setStyleSheet('color:#9a2929;font-weight:650;')
            return

    def _finished(self, result):
        self.result = result
        self.running = False
        self.close_btn.setEnabled(True)
        if self.mode == 'dump':
            if result.success:
                self.status.setText(f'✓ BIOS dump completed: {result.output_path}')
                self.status.setStyleSheet('color:#246b38;font-weight:650;')
            else:
                self.status.setText('✕ BIOS dump failed. No successful dump was accepted.')
                self.status.setStyleSheet('color:#9a2929;font-weight:650;')
        else:
            if result.success:
                self.status.setText('✓ BIOS flash completed and verified successfully.')
                self.status.setStyleSheet('color:#246b38;font-weight:650;')
            elif result.recovery_attempted and result.recovery_success:
                self.status.setText('⚠ The requested flash failed, but the original BIOS backup was restored and verified successfully.')
                self.status.setStyleSheet('color:#795600;font-weight:650;')
            elif result.recovery_attempted and result.recovery_success is False:
                self.status.setText('✕ AUTOMATIC RECOVERY FAILED — do not reboot or power off the computer.')
                self.status.setStyleSheet('color:#9a2929;font-weight:700;')
            else:
                self.status.setText('✕ BIOS flash was not completed.')
                self.status.setStyleSheet('color:#9a2929;font-weight:650;')


    def reject(self):
        if self.running:
            QMessageBox.information(self, 'Operation in progress', 'The FPT operation is still running. This window must remain open until it finishes.')
            return
        super().reject()

    def closeEvent(self, event):
        if self.running:
            event.ignore()
            QMessageBox.information(self, 'Operation in progress', 'The FPT operation is still running. This window must remain open until it finishes.')
            return
        event.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        log('GUI', 'Constructing main window')
        self.setWindowTitle(APP_TITLE)
        self.resize(960, 780)
        self.setMinimumSize(800, 650)
        self.setAcceptDrops(False)
        self.rom_path: Path | None = None
        self.report: dict | None = None
        self.last_built_rom: Path | None = None
        self.thread: QThread | None = None
        self.worker: BuildWorker | None = None
        self.probe_thread: QThread | None = None
        self.probe_worker: FptProbeWorker | None = None
        self.fpt_probe: dict | None = None
        self.fpt_status_labels: list[QLabel] = []
        self._make_ui()
        self.setStyleSheet(STYLE)
        self._tool_preflight()
        self._start_fpt_probe()

    def _make_bios_access_card(self) -> QFrame:
        card = QFrame(); card.setObjectName('card')
        lay = QVBoxLayout(card); lay.setContentsMargins(16, 14, 16, 14); lay.setSpacing(8)
        title = QLabel('BIOS access'); title.setStyleSheet('font-weight:650;font-size:11.5pt;'); lay.addWidget(title)
        status = QLabel('Checking Intel FPT availability…'); status.setWordWrap(True); status.setStyleSheet('color:#5f6368;'); lay.addWidget(status)
        self.fpt_status_labels.append(status)
        row = QHBoxLayout()
        dump_btn = QPushButton('Dump BIOS…'); dump_btn.setCursor(Qt.CursorShape.PointingHandCursor); dump_btn.clicked.connect(self.start_dump)
        flash_btn = QPushButton('Flash BIOS…'); flash_btn.setObjectName('danger'); flash_btn.setCursor(Qt.CursorShape.PointingHandCursor); flash_btn.clicked.connect(self.start_flash)
        get_btn = QPushButton(f'Get Intel FPT {FPT_VERSION}'); get_btn.setCursor(Qt.CursorShape.PointingHandCursor); get_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(FPT_SOURCE_FOLDER_URL)))
        row.addWidget(dump_btn); row.addWidget(flash_btn); row.addStretch(); row.addWidget(get_btn)
        lay.addLayout(row)
        return card

    def _make_ui(self):
        root = QWidget(); self.setCentralWidget(root)
        outer = QVBoxLayout(root); outer.setContentsMargins(28, 22, 28, 22); outer.setSpacing(14)

        title = QLabel(APP_TITLE); title.setObjectName('appTitle')
        subtitle = QLabel('Update outdated Secure Boot factory certificates in AMI X99 BIOS ROMs.')
        subtitle.setObjectName('subtitle')
        outer.addWidget(title); outer.addWidget(subtitle)

        self.stack = QStackedWidget(); outer.addWidget(self.stack, 1)
        self.open_page = QWidget(); op = QVBoxLayout(self.open_page); op.setContentsMargins(0, 4, 0, 0); op.setSpacing(12)
        op.addWidget(self._make_bios_access_card())
        self.drop = DropPanel(); self.drop.fileDropped.connect(self.load_rom)
        op.addWidget(self.drop, 1)
        self.stack.addWidget(self.open_page)

        self.main_page = QWidget(); mp = QVBoxLayout(self.main_page); mp.setContentsMargins(0, 4, 0, 0); mp.setSpacing(12)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget(); self.content_lay = QVBoxLayout(content); self.content_lay.setContentsMargins(0, 0, 4, 4); self.content_lay.setSpacing(12)
        scroll.setWidget(content); mp.addWidget(scroll)

        self.content_lay.addWidget(self._make_bios_access_card())

        filecard = QFrame(); filecard.setObjectName('card'); fl = QVBoxLayout(filecard); fl.setContentsMargins(16, 14, 16, 14)
        row = QHBoxLayout(); self.file_label = QLabel(); self.file_label.setStyleSheet('font-weight:650;font-size:11pt;'); row.addWidget(self.file_label, 1)
        self.change_rom_btn = QPushButton('Choose another ROM…'); self.change_rom_btn.setCursor(Qt.CursorShape.PointingHandCursor); self.change_rom_btn.clicked.connect(self._browse)
        row.addWidget(self.change_rom_btn); fl.addLayout(row)
        self.compat_label = QLabel(); self.compat_label.setWordWrap(True); fl.addWidget(self.compat_label)
        self.content_lay.addWidget(filecard)

        sec = QLabel('Secure Boot factory defaults'); sec.setObjectName('sectionTitle'); self.content_lay.addWidget(sec)
        self.vars_card = QFrame(); self.vars_card.setObjectName('card'); self.vars_grid = QGridLayout(self.vars_card); self.vars_grid.setContentsMargins(16, 12, 16, 12); self.vars_grid.setHorizontalSpacing(14); self.vars_grid.setVerticalSpacing(10)
        self.content_lay.addWidget(self.vars_card)

        self.plan_card = QFrame(); self.plan_card.setObjectName('card'); pl = QVBoxLayout(self.plan_card); pl.setContentsMargins(16, 14, 16, 14)
        self.plan_title = QLabel(); self.plan_title.setStyleSheet('font-weight:650;font-size:11.5pt;')
        self.plan_text = QLabel(); self.plan_text.setWordWrap(True); self.plan_text.setStyleSheet('color:#5f6368;')
        pl.addWidget(self.plan_title); pl.addWidget(self.plan_text); self.content_lay.addWidget(self.plan_card)

        outcard = QFrame(); outcard.setObjectName('card'); ol = QGridLayout(outcard); ol.setContentsMargins(16, 14, 16, 14)
        ol.addWidget(QLabel('Output ROM'), 0, 0)
        self.output_edit = QLineEdit(); ol.addWidget(self.output_edit, 0, 1)
        self.output_browse_btn = QPushButton('Browse…'); self.output_browse_btn.setCursor(Qt.CursorShape.PointingHandCursor); self.output_browse_btn.clicked.connect(self._browse_output)
        ol.addWidget(self.output_browse_btn, 0, 2)
        self.build_btn = QPushButton('Create Secure Boot-patched ROM'); self.build_btn.setObjectName('primary'); self.build_btn.setCursor(Qt.CursorShape.PointingHandCursor); self.build_btn.clicked.connect(self.start_build)
        ol.addWidget(self.build_btn, 1, 1, 1, 2)
        self.content_lay.addWidget(outcard)

        self.progress_card = QFrame(); self.progress_card.setObjectName('card'); pgl = QVBoxLayout(self.progress_card); pgl.setContentsMargins(16, 14, 16, 14)
        self.progress_label = QLabel(''); self.progress_label.setWordWrap(True)
        self.build_progress = QProgressBar(); self.build_progress.setRange(0, 100); self.build_progress.setValue(0); self.build_progress.setFormat('%p%')
        self.log = QTextEdit(); self.log.setReadOnly(True); self.log.setMinimumHeight(145); self.log.setVisible(False)
        logbtn = QPushButton('Show technical log'); logbtn.clicked.connect(lambda: self.log.setVisible(not self.log.isVisible()))
        pgl.addWidget(self.progress_label); pgl.addWidget(self.build_progress); pgl.addWidget(logbtn, 0, Qt.AlignLeft); pgl.addWidget(self.log); self.content_lay.addWidget(self.progress_card)
        self.progress_card.hide()

        after = QLabel('After flashing a patched ROM, clear/re-enroll the firmware’s factory Secure Boot keys so the live UEFI variables are populated from the new ROM defaults. Patching the ROM alone does not rewrite the currently enrolled live keys.')
        after.setWordWrap(True); after.setStyleSheet('background:#fff7df;border:1px solid #ead79c;border-radius:8px;padding:10px;color:#6e5200;')
        self.content_lay.addWidget(after)
        self.content_lay.addStretch(1)
        self.stack.addWidget(self.main_page)

    def _tool_preflight(self):
        log('PREFLIGHT', 'Starting Secure Boot tool/payload self-check')
        try:
            tool = discover_uefireplace()
            if tool is not None:
                validate_uefireplace(tool)
            else:
                log('PREFLIGHT', 'UEFIReplace.exe not found')
            donors = load_bundled_donors(app_directory())
            for name, path in donors.items():
                log('PREFLIGHT', f'{name} payload: {path}; size={path.stat().st_size}; SHA-256={sha256_file(path)}')
            log('PREFLIGHT', 'Secure Boot payload self-check: PASS')
        except Exception as exc:
            log('PREFLIGHT', f'Secure Boot patcher self-check failed: {type(exc).__name__}: {exc}')
            QMessageBox.warning(self, 'Patcher files problem', f'The Secure Boot patcher files did not pass self-check:\n\n{exc}')

    def _start_fpt_probe(self):
        log('GUI', 'Starting background FPT compatibility probe')
        self.probe_thread = QThread(self)
        self.probe_worker = FptProbeWorker(); self.probe_worker.moveToThread(self.probe_thread)
        self.probe_thread.started.connect(self.probe_worker.run)
        self.probe_worker.finished.connect(self._fpt_probe_finished)
        self.probe_worker.finished.connect(self.probe_thread.quit)
        self.probe_thread.finished.connect(self.probe_worker.deleteLater)
        self.probe_thread.finished.connect(self.probe_thread.deleteLater)
        self.probe_thread.start()

    def _fpt_probe_finished(self, result: dict):
        self.fpt_probe = result
        self._update_fpt_status_labels()

    def _update_fpt_status_labels(self):
        if self.fpt_probe is None:
            text, css = 'Checking Intel FPT availability…', 'color:#5f6368;'
        elif self.fpt_probe.get('ready'):
            hvci_note = ' Memory Integrity is enabled, but this FPT installation is working on the current boot.' if self.fpt_probe.get('hvci') is True else ''
            text, css = '✓ BIOS dump and flash are available.' + hvci_note, 'color:#246b38;font-weight:600;'
        elif self.fpt_probe.get('reason') == 'memory-integrity-block':
            text = ('✕ BIOS dump and flash are unavailable because Windows Memory Integrity is active and Intel FPT cannot access the flash. '
                    'Open Windows Security → Device security → Core isolation details → Memory integrity, turn it Off, then restart Windows.')
            css = 'color:#9a2929;font-weight:600;'
        elif self.fpt_probe.get('reason') in ('missing-files', 'wrong-fpt-version', 'missing-authoritative-fparts', 'wrong-authoritative-fparts'):
            text = 'BIOS dump/flash setup is incomplete. ' + self.fpt_probe.get('message', '')
            css = 'color:#795600;font-weight:600;'
        else:
            text = 'BIOS dump and flash are currently unavailable. ' + self.fpt_probe.get('message', '')
            css = 'color:#9a2929;font-weight:600;'
        for label in self.fpt_status_labels:
            label.setText(text); label.setStyleSheet(css)

    def _ensure_fpt_ready(self) -> bool:
        log('GUI', 'Checking whether BIOS dump/flash action may proceed')
        local = validate_fpt_installation()
        if not local.get('ready'):
            QMessageBox.warning(
                self, 'Intel FPT files required',
                local.get('message', 'Intel FPT is not ready.') + '\n\n'
                f'Download the exact ME System Tools v9.1 r7 → Flash Programming Tool → WIN64 files and place them in the tools folder.\n\n{FPT_SOURCE_FOLDER_URL}'
            )
            log('GUI', 'BIOS access denied: FPT installation validation failed')
            return False
        if self.fpt_probe is None:
            QMessageBox.information(self, 'FPT check still running', 'The Intel FPT compatibility check is still running. Try again in a moment.')
            log('GUI', 'BIOS access denied: launch-time FPT probe still running')
            return False
        if not self.fpt_probe.get('ready'):
            QMessageBox.warning(self, 'BIOS dump/flash unavailable', self.fpt_probe.get('message', 'Intel FPT cannot access the flash on this boot.'))
            log('GUI', f"BIOS access denied by FPT probe: {self.fpt_probe.get('reason')}")
            return False
        log('GUI', 'BIOS access check: PASS')
        return True

    def start_dump(self):
        log('GUI', 'User selected Dump BIOS')
        if not self._ensure_fpt_ready():
            return
        path = _choose_dump_output(self)
        if not path:
            log('GUI', 'Dump BIOS cancelled at output-file dialog')
            return
        log('GUI', f'Dump BIOS output selected: {path}')
        dlg = FptOperationDialog(self, 'dump', Path(path))
        dlg.exec()
        if dlg.result and dlg.result.success:
            self.load_rom(dlg.result.output_path)

    def start_flash(self):
        log('GUI', 'User selected Flash BIOS')
        if not self._ensure_fpt_ready():
            return
        start = ''
        if self.last_built_rom and self.last_built_rom.is_file():
            start = str(self.last_built_rom.parent)
        elif self.rom_path:
            start = str(self.rom_path.parent)
        path = _choose_firmware_file(self, start, 'Choose BIOS ROM to flash')
        if not path:
            log('GUI', 'Flash BIOS cancelled at ROM-selection dialog')
            return
        target = Path(path).resolve()
        log('GUI', f'Flash target selected: {target}')
        answer = QMessageBox.warning(
            self,
            'Confirm BIOS flash',
            f'You are about to flash:\n\n{target}\n\n'
            'Before any erase/programming begins, the app will create TWO independent dumps of the currently installed BIOS and require them to be byte-identical. '
            'The verified backup is kept permanently.\n\n'
            'If the requested flash fails after erase/programming has begun, the app will automatically attempt to restore that verified backup.\n\n'
            'Do not shut down or restart the computer while this operation is running.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            log('GUI', 'Flash BIOS cancelled at destructive-operation confirmation')
            return
        log('GUI', 'Flash BIOS confirmed by user')
        dlg = FptOperationDialog(self, 'flash', target)
        dlg.exec()
        result = dlg.result
        if not result:
            log('GUI', 'Flash operation dialog returned no result')
            return
        if result.success:
            QMessageBox.information(self, 'BIOS flash successful', f'The ROM was flashed and verified successfully.\n\nPre-flash backup:\n{result.backup_path}')
        elif result.recovery_attempted and result.recovery_success:
            QMessageBox.warning(self, 'Flash failed — backup restored', f'The requested ROM was not successfully flashed, but the original BIOS backup was restored and verified.\n\nBackup:\n{result.backup_path}')
        elif result.recovery_attempted and result.recovery_success is False:
            QMessageBox.critical(self, 'AUTOMATIC RECOVERY FAILED', f'Do NOT reboot or power off the computer.\n\nThe requested flash failed and the automatic backup restore also failed.\n\nVerified backup:\n{result.backup_path}\n\nUse an appropriate recovery method before power is removed.')
        else:
            QMessageBox.critical(self, 'BIOS flash not completed', (result.error or 'FPT did not complete the flash.') + f'\n\nVerified backup:\n{result.backup_path or "Not created"}')

    def _browse(self):
        start = str(self.rom_path.parent) if self.rom_path else ''
        path = _choose_firmware_file(self, start)
        if path:
            self.load_rom(path)

    def load_rom(self, path: str):
        p = Path(path)
        log('GUI', f'ROM load requested: {p}')
        if not p.is_file():
            log('GUI', 'ROM load ignored: path is not a file')
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            report = inspect_rom(p)
        except Exception as exc:
            log('GUI', f'ROM inspection failed: {type(exc).__name__}: {exc}')
            QMessageBox.critical(self, 'Could not inspect ROM', str(exc)); return
        finally:
            QApplication.restoreOverrideCursor()
        self.rom_path = p.resolve(); self.report = report
        log('GUI', f'ROM loaded successfully: {self.rom_path}')
        self.file_label.setText(f'{p.name}  —  {report["size"]:,} bytes')
        self.output_edit.setText(str(default_output(self.rom_path)))
        self._populate_report()
        self.stack.setCurrentWidget(self.main_page)

    def _clear_grid(self):
        while self.vars_grid.count():
            item = self.vars_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _populate_report(self):
        assert self.report is not None
        sb = self.report['secure_boot']
        self._clear_grid()
        if sb['patchable']:
            self.compat_label.clear(); self.compat_label.hide()
        else:
            self.compat_label.setText('✕ This ROM does not expose the required Secure Boot default variables in a structure this tool can patch safely. ' + '; '.join(sb['errors']))
            self.compat_label.setStyleSheet('color:#9a2929;'); self.compat_label.show()

        names = [('PkVar','Platform key (PK)'),('KekVar','Key exchange keys (KEK)'),('dbVar','Allowed signatures (db)')]
        for row,(key,label) in enumerate(names):
            item = sb['variables'][key]
            name = QLabel(label); name.setStyleSheet('font-weight:600;')
            cls = item.get('classification') or item.get('error','Unknown')
            if key in sb.get('recommended_targets',[]):
                action, kind = 'Will update', 'warn'
            elif item.get('parse_ok'):
                action, kind = 'Keep', 'good'
            else:
                action, kind = 'Cannot patch safely', 'bad'
            self.vars_grid.addWidget(name,row,0); self.vars_grid.addWidget(QLabel(cls),row,1); self.vars_grid.addWidget(_badge(action,kind),row,2)

        targets = sb.get('recommended_targets',[])
        self.build_btn.setEnabled(True)
        if not sb['patchable']:
            self.plan_title.setText('This ROM cannot be patched safely')
            self.plan_text.setText('PK, KEK or db is missing, duplicated, or stored in a firmware structure this app cannot patch safely.')
            self.build_btn.setText('Show why this ROM cannot be patched')
        elif not targets:
            self.plan_title.setText('Secure Boot certificates are already current')
            self.plan_text.setText('PK, KEK and db do not need updating.')
            self.build_btn.setText('Secure Boot certificates are already current')
        else:
            human = {'PkVar':'replace the AMI test Platform Key','KekVar':'add the validated Microsoft 2023 KEK set','dbVar':'add the validated Microsoft 2023 db certificates'}
            self.plan_title.setText('Recommended automatic patch')
            self.plan_text.setText('The patcher will ' + '; '.join(human[x] for x in targets) + '.')
            self.build_btn.setText('Create Secure Boot-patched ROM')

    def _browse_output(self):
        if not self.rom_path:
            return
        dialog = QFileDialog(self, 'Save patched ROM', str(self.rom_path.parent))
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setNameFilters(['Firmware image (*.ROM *.rom *.BIN *.bin)', 'All files (*.*)'])
        dialog.selectFile(self.output_edit.text())
        if dialog.exec():
            files = dialog.selectedFiles()
            if files:
                self.output_edit.setText(files[0])
                log('GUI', f'Patched-ROM output path selected: {files[0]}')

    def start_build(self):
        log('GUI', 'User selected Create Secure Boot-patched ROM')
        if not self.rom_path or not self.report:
            log('GUI', 'Build ignored because no ROM/report is loaded')
            return
        sb = self.report['secure_boot']
        if not sb.get('patchable'):
            reason = '; '.join(sb.get('errors', [])) or 'PK, KEK or db cannot be parsed safely.'
            log('GUI', f'Build blocked: ROM cannot be patched safely: {reason}')
            QMessageBox.warning(self, 'ROM cannot be patched safely', reason); return
        if not sb.get('recommended_targets'):
            log('GUI', 'Build blocked: Secure Boot certificates already current')
            QMessageBox.information(self, 'No Secure Boot update needed', 'PK, KEK and db are already current. There is nothing for the patcher to change.'); return
        out = Path(self.output_edit.text().strip())
        if not out.name:
            QMessageBox.warning(self,'Output missing','Choose an output ROM path.'); return
        if out.resolve() == self.rom_path.resolve():
            QMessageBox.warning(self,'Output must be new','The patcher never overwrites the input ROM. Choose a different output file.'); return
        log('GUI', f'Starting Secure Boot build: input={self.rom_path} output={out.resolve()}')
        self.progress_card.show(); self.log.clear(); self.progress_label.setText('Starting…'); self.progress_label.setStyleSheet(''); self.build_progress.setValue(0); self.build_progress.setFormat('%p%'); self.build_progress.setStyleSheet(''); self.build_btn.setEnabled(False)
        targets = list(sb.get('recommended_targets', []))
        self.thread = QThread(self); self.worker = BuildWorker(self.rom_path, out, targets); self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run); self.worker.progress.connect(self._progress); self.worker.finished.connect(self._finished)
        self.worker.finished.connect(self.thread.quit); self.thread.finished.connect(self.worker.deleteLater); self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def _progress(self, state: str, text: str, percent: int):
        self.progress_label.setText(text)
        self.build_progress.setValue(percent)
        self.log.append(f'[{state}] {text}')

    def _finished(self,result):
        if result.success:
            self.last_built_rom = Path(result.output_path).resolve()
            self.build_progress.setValue(100)
            self.progress_label.setText(f'✓ ROM created and verified: {Path(result.output_path).name}')
            self.progress_label.setStyleSheet('color:#246b38;font-weight:650;')
            answer = QMessageBox.question(
                self, 'Secure Boot ROM created',
                'The new ROM passed final Secure Boot validation.\n\nWould you like to flash it now? The flash workflow will first create and verify two byte-identical backups of the currently installed BIOS.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                # Select the freshly created ROM without asking the user to find it again.
                if self._ensure_fpt_ready():
                    target = self.last_built_rom
                    confirm = QMessageBox.warning(
                        self, 'Confirm BIOS flash',
                        f'You are about to flash:\n\n{target}\n\nTwo independent pre-flash BIOS dumps will be created and verified before any erase/programming begins. Continue?',
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    if confirm == QMessageBox.StandardButton.Yes:
                        dlg = FptOperationDialog(self, 'flash', target); dlg.exec()
        else:
            self.progress_label.setText('✕ Build failed safely — no successful output was accepted.')
            self.progress_label.setStyleSheet('color:#9a2929;font-weight:650;')
            QMessageBox.critical(self,'Patch failed',result.error or 'Unknown error')
        if self.report:
            self._populate_report()


def main() -> int:
    session_path = start_session_log(__version__, APP_TITLE)
    install_exception_hook()
    log('SESSION', f'GUI entrypoint arguments: {sys.argv!r}')
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.aboutToQuit.connect(lambda: finish_session_log('Qt application exit'))
    win = MainWindow(); win.show()
    log('GUI', f'Main window shown; session log is {session_path}')
    if len(sys.argv) > 1 and Path(sys.argv[1]).is_file():
        win.load_rom(sys.argv[1])
    code = app.exec()
    finish_session_log(f'Qt event loop returned {code}')
    return code
