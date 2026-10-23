"""Create a tool-free release ZIP only after both real EXE self-tests pass."""
from pathlib import Path
from hashlib import sha256
import json
import shutil
import zipfile
import sys

ROOT = Path(__file__).resolve().parents[1]


def package(root: Path = ROOT) -> Path:
    sys.path.insert(0, str(ROOT))
    from scripts.verify_exe import verify
    overall = json.loads((root / 'build' / 'windows-runtime-tests.json').read_text(encoding='utf-8-sig'))
    if overall.get('success') is not True or {c['case'] for c in overall.get('cases', [])} != {'gui', 'cli', 'conflicting-dlls', 'helper-transport'}:
        raise RuntimeError('The actual EXE and conflicting-DLL tests have not all passed.')
    for kind in ('gui', 'cli'):
        report = json.loads((root / 'build' / f'smoke-{kind}.json').read_text(encoding='utf-8'))
        if report.get('success') is not True or report.get('version') != '0.967':
            raise RuntimeError(f'{kind} packaged self-test has not passed.')
        name = 'X99-Secureboot-patcher' + ('-CLI' if kind == 'cli' else '') + '.exe'
        if report.get('exe_sha256') != sha256((root / 'dist' / name).read_bytes()).hexdigest():
            raise RuntimeError(f'{kind} self-test is for a different executable.')
        if kind == 'gui' and report.get('platform') != 'windows':
            raise RuntimeError('The actual Windows Qt platform has not passed.')
        if kind == 'gui' and report.get('drag_drop_verified') is not True:
            raise RuntimeError('The packaged GUI file-drop test has not passed.')
        verify(root / 'dist' / name)
    poison = json.loads((root / 'build' / 'smoke-conflicting-dlls.json').read_text(encoding='utf-8'))
    if poison.get('success') is not True or poison.get('drag_drop_verified') is not True or poison.get('exe_sha256') != sha256((root / 'dist' / 'X99-Secureboot-patcher.exe').read_bytes()).hexdigest():
        raise RuntimeError('The conflicting-DLL test did not pass for this GUI executable.')
    helper = json.loads((root / 'build' / 'smoke-helper-transport.json').read_text(encoding='utf-8'))
    if (helper.get('success') is not True or helper.get('hardware_access') is not False
            or helper.get('result', {}).get('transport_verified') is not True
            or helper.get('result', {}).get('helper_exe_sha256') != sha256((root / 'dist' / 'X99-Secureboot-patcher-CLI.exe').read_bytes()).hexdigest()
            or helper.get('exe_sha256') != sha256((root / 'dist' / 'X99-Secureboot-patcher.exe').read_bytes()).hexdigest()):
        raise RuntimeError('The packaged helper exchange has not passed for this GUI executable.')
    stage = root / 'build' / 'release-staging'
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    for name in ('X99-Secureboot-patcher.exe', 'X99-Secureboot-patcher-CLI.exe', 'README.txt'):
        shutil.copy2(root / 'dist' / name, stage / name)
    shutil.copy2(root / 'TEST-ELEVATED-HELPER.cmd', stage / 'TEST-ELEVATED-HELPER.cmd')
    for folder, names in (('secureboot_donors', ('PkVar.ffs', 'KekVar.ffs', 'dbVar.ffs')),
                          ('fpt_support', ('fparts.txt',))):
        (stage / folder).mkdir()
        for name in names:
            shutil.copy2(root / 'dist' / folder / name, stage / folder / name)
    (stage / 'tools').mkdir()
    shutil.copy2(root / 'tools' / 'README.txt', stage / 'tools' / 'README.txt')
    shutil.copytree(root / 'dist' / 'licenses', stage / 'licenses')
    (stage / 'runtime-info').mkdir()
    for kind in ('gui', 'cli'):
        shutil.copy2(root / 'build' / f'verified-{kind}.json', stage / 'runtime-info' / f'{kind}.json')
    archive = root / 'Chinesium-X99-SecureBoot-Patcher-v0.967-Windows-x64.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as output:
        for path in sorted(stage.rglob('*')):
            if path.is_file():
                output.write(path, str(Path('Chinesium-X99-SecureBoot-Patcher-v0.967-Windows-x64') / path.relative_to(stage)))
    archive.with_suffix('.zip.sha256').write_text(sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n', encoding='utf-8')
    return archive


if __name__ == '__main__':
    print(package())
