from __future__ import annotations
from pathlib import Path
import json
import sys

from PySide6.QtCore import QObject, QThread, Signal, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QScrollArea,
    QSizePolicy, QSpacerItem, QStackedWidget, QTextEdit, QVBoxLayout, QWidget,
)

from .pipeline import inspect_rom, build_secureboot_rom, default_output
from .secureboot import load_bundled_donors, plan_secure_boot
from .tools import app_directory, discover_uefireplace, validate_uefireplace

APP_TITLE = 'X99 Secureboot patcher'

STYLE = r'''
QMainWindow { background: #f4f5f7; }
QWidget { font-family: "Segoe UI"; font-size: 10pt; color: #202124; }
QLabel#appTitle { font-size: 23pt; font-weight: 700; color: #111827; }
QLabel#subtitle { color: #5f6368; font-size: 10.5pt; }
QLabel#sectionTitle { font-size: 15pt; font-weight: 650; color: #111827; }
QFrame#card { background: white; border: 1px solid #dfe3e8; border-radius: 11px; }
QFrame#goodCard { background: #eef8f0; border: 1px solid #bfdec6; border-radius: 10px; }
QFrame#warnCard { background: #fff7df; border: 1px solid #e5d39b; border-radius: 10px; }
QFrame#badCard { background: #fdeeee; border: 1px solid #e7c0c0; border-radius: 10px; }
QPushButton { background: white; border: 1px solid #c9ced6; border-radius: 7px; padding: 8px 14px; }
QPushButton:hover { background: #f5f7f9; }
QPushButton#primary { background: #1a73e8; border-color: #1a73e8; color: white; font-weight: 650; padding: 10px 18px; }
QPushButton#primary:hover { background: #1765cc; }
QLineEdit { background: white; border: 1px solid #cbd0d7; border-radius: 6px; padding: 7px; }
QTextEdit { background: #111827; color: #e5e7eb; border: 1px solid #2f3747; border-radius: 7px; font-family: Consolas; font-size: 9pt; }
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


def _choose_firmware_file(parent: QWidget, start_dir: str = '') -> str | None:
    dialog = QFileDialog(parent, 'Open firmware image', start_dir)
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
    dialog.setNameFilters(['Firmware images (*.rom *.ROM *.bin *.BIN)', 'All files (*.*)'])
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
    progress = Signal(str, str)
    finished = Signal(object)

    def __init__(self, source: Path, output: Path):
        super().__init__()
        self.source = source
        self.output = output

    def run(self):
        result = build_secureboot_rom(self.source, self.output, lambda state, text: self.progress.emit(state, text))
        self.finished.emit(result)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(930, 720)
        self.setMinimumSize(780, 620)
        self.setAcceptDrops(False)
        self.rom_path: Path | None = None
        self.report: dict | None = None
        self.thread: QThread | None = None
        self.worker: BuildWorker | None = None
        self._make_ui()
        self.setStyleSheet(STYLE)
        self._tool_preflight()

    def _make_ui(self):
        root = QWidget(); self.setCentralWidget(root)
        outer = QVBoxLayout(root); outer.setContentsMargins(28, 22, 28, 22); outer.setSpacing(14)

        title = QLabel(APP_TITLE); title.setObjectName('appTitle')
        subtitle = QLabel('Update outdated Secure Boot factory certificates in AMI X99 BIOS ROMs.')
        subtitle.setObjectName('subtitle')
        outer.addWidget(title); outer.addWidget(subtitle)

        self.stack = QStackedWidget(); outer.addWidget(self.stack, 1)
        self.open_page = QWidget(); op = QVBoxLayout(self.open_page); op.setContentsMargins(0, 4, 0, 0)
        self.drop = DropPanel(); self.drop.fileDropped.connect(self.load_rom)
        op.addStretch(); op.addWidget(self.drop); op.addStretch()
        self.stack.addWidget(self.open_page)

        self.main_page = QWidget(); mp = QVBoxLayout(self.main_page); mp.setContentsMargins(0, 4, 0, 0); mp.setSpacing(12)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget(); self.content_lay = QVBoxLayout(content); self.content_lay.setContentsMargins(0, 0, 4, 4); self.content_lay.setSpacing(12)
        scroll.setWidget(content); mp.addWidget(scroll)

        filecard = QFrame(); filecard.setObjectName('card'); fl = QVBoxLayout(filecard); fl.setContentsMargins(16, 14, 16, 14)
        row = QHBoxLayout(); self.file_label = QLabel(); self.file_label.setStyleSheet('font-weight:650;font-size:11pt;'); row.addWidget(self.file_label, 1)
        self.change_rom_btn = QPushButton('Choose another ROM…')
        self.change_rom_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.change_rom_btn.clicked.connect(self._browse)
        row.addWidget(self.change_rom_btn); fl.addLayout(row)
        self.compat_label = QLabel(); self.compat_label.setWordWrap(True); fl.addWidget(self.compat_label)
        self.content_lay.addWidget(filecard)

        sec = QLabel('Secure Boot factory defaults'); sec.setObjectName('sectionTitle'); self.content_lay.addWidget(sec)
        self.vars_card = QFrame(); self.vars_card.setObjectName('card'); self.vars_grid = QGridLayout(self.vars_card); self.vars_grid.setContentsMargins(16, 12, 16, 12); self.vars_grid.setHorizontalSpacing(14); self.vars_grid.setVerticalSpacing(10)
        self.content_lay.addWidget(self.vars_card)

        self.plan_card = QFrame(); self.plan_card.setObjectName('card'); pl = QVBoxLayout(self.plan_card); pl.setContentsMargins(16, 14, 16, 14)
        self.plan_title = QLabel(); self.plan_title.setStyleSheet('font-weight:650;font-size:11.5pt;'); self.plan_text = QLabel(); self.plan_text.setWordWrap(True); self.plan_text.setStyleSheet('color:#5f6368;')
        pl.addWidget(self.plan_title); pl.addWidget(self.plan_text); self.content_lay.addWidget(self.plan_card)

        outcard = QFrame(); outcard.setObjectName('card'); ol = QGridLayout(outcard); ol.setContentsMargins(16, 14, 16, 14)
        ol.addWidget(QLabel('Output ROM'), 0, 0)
        self.output_edit = QLineEdit(); ol.addWidget(self.output_edit, 0, 1)
        self.output_browse_btn = QPushButton('Browse…')
        self.output_browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.output_browse_btn.clicked.connect(self._browse_output)
        ol.addWidget(self.output_browse_btn, 0, 2)
        self.build_btn = QPushButton('Create Secure Boot-patched ROM'); self.build_btn.setObjectName('primary'); self.build_btn.setCursor(Qt.CursorShape.PointingHandCursor); self.build_btn.clicked.connect(self.start_build); ol.addWidget(self.build_btn, 1, 1, 1, 2)
        self.content_lay.addWidget(outcard)

        self.progress_card = QFrame(); self.progress_card.setObjectName('card'); pgl = QVBoxLayout(self.progress_card); pgl.setContentsMargins(16, 14, 16, 14)
        self.progress_label = QLabel(''); self.progress_label.setWordWrap(True); self.log = QTextEdit(); self.log.setReadOnly(True); self.log.setMinimumHeight(145); self.log.setVisible(False)
        logbtn = QPushButton('Show technical log'); logbtn.clicked.connect(lambda: self.log.setVisible(not self.log.isVisible()))
        pgl.addWidget(self.progress_label); pgl.addWidget(logbtn, 0, Qt.AlignLeft); pgl.addWidget(self.log); self.content_lay.addWidget(self.progress_card)
        self.progress_card.hide()

        after = QLabel('After flashing a patched ROM, clear/re-enroll the firmware’s factory Secure Boot keys so the live UEFI variables are populated from the new ROM defaults. Patching the ROM alone does not rewrite the currently enrolled live keys.')
        after.setWordWrap(True); after.setStyleSheet('background:#fff7df;border:1px solid #ead79c;border-radius:8px;padding:10px;color:#6e5200;')
        self.content_lay.addWidget(after)
        self.content_lay.addStretch(1)
        self.stack.addWidget(self.main_page)

    def _tool_preflight(self):
        try:
            tool = discover_uefireplace()
            if tool is None:
                return
            validate_uefireplace(tool)
            load_bundled_donors(app_directory())
        except Exception as exc:
            QMessageBox.warning(self, 'Bundled files problem', f'The patcher files did not pass self-check:\n\n{exc}')

    def _browse(self):
        start = str(self.rom_path.parent) if self.rom_path else ''
        path = _choose_firmware_file(self, start)
        if path:
            self.load_rom(path)

    def load_rom(self, path: str):
        p = Path(path)
        if not p.is_file(): return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            report = inspect_rom(p)
        except Exception as exc:
            QMessageBox.critical(self, 'Could not inspect ROM', str(exc)); return
        finally:
            QApplication.restoreOverrideCursor()
        self.rom_path = p.resolve(); self.report = report
        self.file_label.setText(f'{p.name}  —  {report["size"]:,} bytes')
        self.output_edit.setText(str(default_output(self.rom_path)))
        self._populate_report()
        self.stack.setCurrentWidget(self.main_page)

    def _clear_grid(self):
        while self.vars_grid.count():
            item = self.vars_grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def _populate_report(self):
        assert self.report is not None
        sb = self.report['secure_boot']
        self._clear_grid()
        if sb['patchable']:
            self.compat_label.clear()
            self.compat_label.hide()
        else:
            self.compat_label.setText('✕ This ROM does not expose the required Secure Boot default variables in a structure this tool can patch safely. ' + '; '.join(sb['errors']))
            self.compat_label.setStyleSheet('color:#9a2929;')
            self.compat_label.show()

        names = [('PkVar','Platform key (PK)'),('KekVar','Key exchange keys (KEK)'),('dbVar','Allowed signatures (db)')]
        for row,(key,label) in enumerate(names):
            item = sb['variables'][key]
            name = QLabel(label); name.setStyleSheet('font-weight:600;')
            cls = item.get('classification') or item.get('error','Unknown')
            if key in sb.get('recommended_targets',[]):
                action = 'Will update'
                kind = 'warn'
            elif item.get('parse_ok'):
                action = 'Keep'
                kind = 'good'
            else:
                action = 'Cannot patch safely'
                kind = 'bad'
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

    def start_build(self):
        if not self.rom_path or not self.report:
            return
        sb = self.report['secure_boot']
        if not sb.get('patchable'):
            reason = '; '.join(sb.get('errors', [])) or 'PK, KEK or db cannot be parsed safely.'
            QMessageBox.warning(self, 'ROM cannot be patched safely', reason)
            return
        if not sb.get('recommended_targets'):
            QMessageBox.information(
                self,
                'No Secure Boot update needed',
                'PK, KEK and db are already current. There is nothing for the patcher to change.'
            )
            return
        out = Path(self.output_edit.text().strip())
        if not out.name:
            QMessageBox.warning(self,'Output missing','Choose an output ROM path.'); return
        if out.resolve() == self.rom_path.resolve():
            QMessageBox.warning(self,'Output must be new','The patcher never overwrites the input ROM. Choose a different output file.'); return
        self.progress_card.show(); self.log.clear(); self.progress_label.setText('Starting…'); self.build_btn.setEnabled(False)
        self.thread = QThread(self); self.worker = BuildWorker(self.rom_path,out); self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run); self.worker.progress.connect(self._progress); self.worker.finished.connect(self._finished)
        self.worker.finished.connect(self.thread.quit); self.thread.finished.connect(self.worker.deleteLater); self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def _progress(self,state:str,text:str):
        self.progress_label.setText(text)
        self.log.append(f'[{state}] {text}')

    def _finished(self,result):
        if result.success:
            self.progress_label.setText(f'✓ ROM created and verified: {Path(result.output_path).name}')
            self.progress_label.setStyleSheet('color:#246b38;font-weight:650;')
            QMessageBox.information(self,'Secure Boot ROM created',
                'The new ROM passed final Secure Boot validation.\n\n'
                'The patcher did NOT flash the motherboard. After flashing, clear/re-enroll factory Secure Boot keys in firmware setup so the live variables use the new defaults.')
        else:
            self.progress_label.setText('✕ Build failed safely — no successful output was accepted.')
            self.progress_label.setStyleSheet('color:#9a2929;font-weight:650;')
            QMessageBox.critical(self,'Patch failed',result.error or 'Unknown error')
        if self.report:
            self._populate_report()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    win = MainWindow(); win.show()
    if len(sys.argv) > 1 and Path(sys.argv[1]).is_file():
        win.load_rom(sys.argv[1])
    return app.exec()
