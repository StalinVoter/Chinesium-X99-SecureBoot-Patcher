from x99sb.buildprogress import BuildProgressTracker


def test_three_target_secureboot_progress_is_monotonic_and_finishes_at_100():
    t = BuildProgressTracker(['PkVar', 'KekVar', 'dbVar'])
    events = [
        ('PASS', 'Input inspected: 16777216 bytes; Secure Boot structures are compatible'),
        ('PASS', 'Auto plan: PkVar, KekVar, dbVar'),
        ('RUNNING', 'Update PkVar'),
        ('PASS', 'PkVar: 0x494 -> 0x3E8; donor verified'),
        ('RUNNING', 'Update KekVar'),
        ('PASS', 'KekVar: 0x93B -> 0x958; donor verified'),
        ('RUNNING', 'Update dbVar'),
        ('PASS', 'dbVar: 0xD2D -> 0x1400; donor verified'),
        ('PASS', 'Final Secure Boot 2023 validation passed; dbx preserved'),
        ('PASS', 'Output size preserved: 16777216 bytes'),
    ]
    values = [t.update(*event) for event in events]
    assert values == [10, 15, 15, 35, 35, 55, 55, 75, 95, 100]
    assert values == sorted(values)


def test_single_target_build_scales_patch_stage_without_going_backwards():
    t = BuildProgressTracker(['PkVar'])
    assert t.update('PASS', 'Input inspected: 1 bytes; Secure Boot structures are compatible') == 10
    assert t.update('PASS', 'Auto plan: PkVar') == 15
    assert t.update('RUNNING', 'Update PkVar') == 15
    assert t.update('PASS', 'PkVar: 0x494 -> 0x3E8; donor verified') == 75
    assert t.update('PASS', 'Final Secure Boot 2023 validation passed; dbx preserved') == 95
    assert t.update('PASS', 'Output size preserved: 1 bytes') == 100


def test_gui_wires_secureboot_progress_bar_to_build_worker():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    text = (root / 'x99sb' / 'gui.py').read_text(encoding='utf-8')
    assert "self.build_progress = QProgressBar()" in text
    assert "self.worker = BuildWorker(self.rom_path, out, targets)" in text
    assert "self.worker.progress.connect(self._progress)" in text
    assert "self.build_progress.setValue(percent)" in text
    assert "self.build_progress.setValue(100)" in text
