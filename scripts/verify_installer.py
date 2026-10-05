"""Exercise the separately registered QA installer; never install over a user's app."""
from pathlib import Path
import argparse
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
import zipfile
import winreg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import __version__
from scripts.build_installer import digest


def snapshot(directory):
    return {str(p.relative_to(directory)): digest(p) for p in directory.rglob('*') if p.is_file()}


def registered():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion\Uninstall\LensAtlas.InstallerQA_is1',
                            0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY):
            return True
    except FileNotFoundError:
        return False


def shell_folder(number):
    value = ctypes.create_unicode_buffer(32768)
    result = ctypes.windll.shell32.SHGetFolderPathW(None, number, None, 0, value)
    if result:
        raise RuntimeError(f'Unable to locate shell folder {number}: {result}')
    return Path(value.value)


def invoke(executable, arguments):
    process = subprocess.run([str(executable), *arguments], timeout=600)
    if process.returncode:
        raise RuntimeError(f'{executable.name} failed with exit code {process.returncode}')


def verify_payload(installed, archive):
    with zipfile.ZipFile(archive) as bundle:
        count = 0
        for info in bundle.infolist():
            if info.is_dir():
                continue
            target = installed.joinpath(*Path(info.filename).parts[1:])
            with bundle.open(info) as stream:
                expected = hashlib.file_digest(stream, 'sha256').hexdigest()
            if not target.is_file() or digest(target) != expected:
                raise RuntimeError(f'Installed file mismatch: {info.filename}')
            count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-dir', type=Path, default=ROOT.parent / 'release')
    parser.add_argument('--install-base', type=Path, default=ROOT / '.runtime' / 'custom-install-paths')
    parser.add_argument('--mobile-share', action='store_true', help='Also verify the installed phone access APIs')
    args = parser.parse_args()
    release = args.release_dir.resolve()
    name = f'LensAtlas-{__version__}-Setup'
    installer = ROOT / '.runtime' / 'installer-qa' / (name + '-QA-x64.exe')
    record = json.loads(installer.with_suffix('.exe.build.json').read_text(encoding='utf-8'))
    production = release / (name + '-x64.exe')
    production_record = json.loads(production.with_suffix('.exe.build.json').read_text(encoding='utf-8'))
    if (not record.get('qa_identity') or record['sha256'] != digest(installer)
            or production_record.get('qa_identity') or production_record['sha256'] != digest(production)
            or record['portable_sha256'] != production_record['portable_sha256']):
        raise RuntimeError('QA/production installer identity or payload verification failed')
    portable = release / f'LensAtlas-{__version__}-windows-x64.zip'
    if digest(portable) != record['portable_sha256']:
        raise RuntimeError('Portable release changed after compilation')
    tag = 'installer-' + uuid.uuid4().hex[:10]
    base = args.install_base.resolve()
    base_existed = base.exists()
    installed = base / tag / '镜迹 自选目录'
    default_qa = Path(os.environ['LOCALAPPDATA']) / 'Programs' / 'LensAtlasInstallerQA'
    shortcuts = [shell_folder(2) / 'Lens Atlas Installer QA.lnk',
                 shell_folder(16) / 'Lens Atlas Installer QA.lnk']
    if installed.exists() or default_qa.exists() or registered() or any(p.exists() for p in shortcuts):
        raise RuntimeError('QA installation already exists; inspect it before running again')
    fixture = ROOT / '.runtime' / '合成 测试图库'
    if not fixture.is_dir():
        raise RuntimeError('Synthetic fixture missing. Run scripts/create_fixture.py first.')
    fixture_before = snapshot(fixture)
    logs = ROOT / '.runtime' / tag
    logs.mkdir()
    print(f'QA logs: {logs}', flush=True)

    # Reject a nonempty directory before any user files are overwritten.
    protected = logs / 'synthetic-library'
    protected.mkdir()
    (protected / 'original.txt').write_text('Synthetic original; must remain unchanged.', encoding='utf-8')
    protected_before = snapshot(protected)
    rejected = subprocess.run([str(production), '/VERYSILENT', '/SUPPRESSMSGBOXES',
                               '/NORESTART', '/SP-', f'/DIR={protected}',
                               f'/LOG={logs / "rejected-directory.log"}'], timeout=120)
    if rejected.returncode != 7 or snapshot(protected) != protected_before:
        raise RuntimeError('Production installer failed directory override protection')
    rejected_qa = subprocess.run([str(installer), '/VERYSILENT', '/SUPPRESSMSGBOXES',
                                 '/NORESTART', '/SP-', f'/DIR={protected}',
                                 f'/LOG={logs / "rejected-nonempty-fresh-install.log"}'], timeout=120)
    if (rejected_qa.returncode != 7 or snapshot(protected) != protected_before
            or 'This folder already contains files.' not in (logs / 'rejected-nonempty-fresh-install.log').read_text(encoding='utf-8-sig')):
        raise RuntimeError('Fresh QA installer failed nonempty-directory protection')
    print('Nonempty library-directory installation rejected without changing its files.', flush=True)
    simulated_data = logs / 'synthetic-app-data'
    simulated_data.mkdir()
    (simulated_data / 'library.sqlite3').write_bytes(b'synthetic data protection sentinel')
    data_sentinel = snapshot(simulated_data)
    rejected_data = subprocess.run([str(production), '/VERYSILENT', '/SUPPRESSMSGBOXES',
                                    '/NORESTART', '/SP-', f'/DIR={simulated_data / "nested-app"}',
                                    f'/LOG={logs / "rejected-data-directory.log"}'], timeout=120)
    if rejected_data.returncode != 7 or snapshot(simulated_data) != data_sentinel:
        raise RuntimeError('Production installer failed application-data-directory protection')
    environment_data = logs / 'empty-environment-data'
    environment_data.mkdir()
    environment = dict(os.environ, LENS_DATA_DIR=str(environment_data))
    rejected_env = subprocess.run([str(production), '/VERYSILENT', '/SUPPRESSMSGBOXES',
                                  '/NORESTART', '/SP-', f'/DIR={environment_data}',
                                  f'/LOG={logs / "rejected-environment-data.log"}'],
                                 env=environment, timeout=120)
    if rejected_env.returncode != 7 or snapshot(environment_data):
        raise RuntimeError('Production installer failed environment data-directory protection')

    flags = ['/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/NORESTARTAPPLICATIONS',
             '/TASKS=desktopicon']
    invoke(installer, flags + [f'/DIR={installed}', f'/LOG={logs / "install.log"}'])
    if not registered() or not all(p.is_file() for p in shortcuts):
        raise RuntimeError('Per-user registration or shortcut creation failed')
    count = verify_payload(installed, portable)
    unowned = installed / 'user-created-qa.txt'
    unowned.write_text('Untracked user file must survive uninstall.', encoding='utf-8')
    unowned_hash = digest(unowned)
    # The tag isolates every application write from the real LocalAppData data.
    smoke = [sys.executable, str(ROOT / 'scripts' / 'verify_bundle.py'),
             '--exe', str(installed / 'LensAtlas.exe'), '--tag', tag]
    if args.mobile_share:
        smoke.append('--mobile-share')
    subprocess.run(smoke, cwd=ROOT, check=True, timeout=240)
    data = ROOT / '.runtime' / f'{tag}-verification-data'
    (data / 'preserve-settings-qa.txt').write_text('Settings preservation sentinel.', encoding='utf-8')
    before_upgrade = snapshot(data)
    invoke(installer, flags + [f'/LOG={logs / "upgrade.log"}'])
    verify_payload(installed, portable)
    if default_qa.exists():
        raise RuntimeError('Upgrade ignored the previous custom installation directory')
    if snapshot(data) != before_upgrade or digest(unowned) != unowned_hash:
        raise RuntimeError('Overwrite installation modified application data or user files')
    subprocess.run(smoke, cwd=ROOT, check=True, timeout=240)
    before_uninstall = snapshot(data)
    invoke(installed / 'unins000.exe',
           ['/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', f'/LOG={logs / "uninstall.log"}'])
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and (installed / 'unins000.exe').exists():
        time.sleep(0.2)
    if (installed / 'LensAtlas.exe').exists() or registered() or any(p.exists() for p in shortcuts):
        raise RuntimeError('QA uninstall failed to remove the registered app and shortcuts')
    if snapshot(data) != before_uninstall or digest(unowned) != unowned_hash:
        raise RuntimeError('Uninstall modified data or untracked files')
    if snapshot(fixture) != fixture_before or snapshot(protected) != protected_before:
        raise RuntimeError('Synthetic original files changed during verification')
    # Only these two paths were created by this test, and rmdir refuses nonempty dirs.
    unowned.unlink()
    installed.rmdir()
    installed.parent.rmdir()
    if not base_existed:
        base.rmdir()
    report = {
        'version': __version__, 'installer_sha256': production_record['sha256'],
        'qa_installer_sha256': record['sha256'], 'portable_sha256': record['portable_sha256'],
        'production_nonempty_directory_rejected': True,
        'production_data_directory_rejected': True,
        'production_environment_data_rejected': True,
        'qa_custom_directory': 'passed with spaces and Chinese characters',
        'qa_previous_custom_directory_reused': True,
        'qa_fresh_nonempty_directory_rejected': True,
        'qa_install_drive': installed.drive,
        'qa_first_install': 'passed', 'qa_same_version_overwrite': 'passed',
        'qa_uninstall': 'passed', 'installed_files_verified': count,
        'desktop_smoke_after_install_and_overwrite': 'passed',
        'application_data_preserved': True, 'untracked_files_preserved': True,
        'synthetic_library_unchanged': True, 'qa_registration_and_shortcuts_removed': True,
        'test_scope': 'Separate QA identity; custom local path; production rejects nonempty/data paths; no existing user app replaced.',
        'future_version_database_migration': 'not claimed'
    }
    report_path = ROOT / '.runtime' / 'installer-verification.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    production_record['install_upgrade_uninstall'] = 'passed with separate QA identity; same-version overwrite'
    production_record['verification'] = report
    production.with_suffix('.exe.build.json').write_text(
        json.dumps(production_record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()

