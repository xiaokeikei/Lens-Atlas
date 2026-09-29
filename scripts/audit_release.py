"""Verify all release packages and refresh checksums without dropping the installer."""
from pathlib import Path, PurePosixPath
import argparse
import datetime
import hashlib
import json
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import __version__
from scripts.build_installer import digest


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT.parent / 'release')
    args = parser.parse_args()
    output = args.output_dir.resolve()
    version = __version__
    names = [f'LensAtlas-{version}-windows-x64.zip',
             f'LensAtlas-{version}-docker-online.zip',
             f'LensAtlas-{version}-docker-offline-amd64.zip']
    records = []
    for name in names:
        path = output / name
        checksum = digest(path)
        require(path.with_suffix('.zip.sha256').read_text(encoding='utf-8').split()[0] == checksum,
                f'Checksum mismatch: {name}')
        with zipfile.ZipFile(path) as archive:
            require(archive.testzip() is None, f'ZIP CRC failed: {name}')
            members = archive.namelist()
            for member in members:
                item = PurePosixPath(member)
                require(not item.is_absolute() and '..' not in item.parts
                        and '\\' not in member and ':' not in member, 'Unsafe ZIP path')
                require(not ({'.runtime', '.venv', '.git', 'node_modules'} & set(item.parts)),
                        'Private runtime directory in release')
                require(item.name not in {'.env', 'library.sqlite3', 'setup-code.txt'},
                        'Private file in release')
            if 'windows' in name:
                require('LensAtlas/LensAtlas.exe' in members
                        and any(m.startswith('LensAtlas/_internal/') for m in members),
                        'Incomplete Windows bundle')
                executable = hashlib.sha256(archive.read('LensAtlas/LensAtlas.exe')).hexdigest()
                evidence = json.loads((ROOT / '.runtime/final-verification.json').read_text(encoding='utf-8'))
                require(executable == evidence['executable_sha256'] and evidence['path_isolated'],
                        'Windows smoke verification does not match')
                platform = 'windows/x64'
            else:
                compose = archive.read('LensAtlas/compose.yaml').decode()
                require(compose.count('read_only: true') >= 2 and f'lens-atlas:{version}' in compose,
                        'Docker read-only mounts or version mismatch')
                if 'offline' in name:
                    require('build:' not in compose and 'pull_policy: never' in compose,
                            'Offline compose requires no build or pull')
                    manifest = json.loads(archive.read('LensAtlas/image-manifest.json'))
                    require(manifest['platform'] == 'linux/amd64' and manifest['private_data_audit'] == 'passed',
                            'Offline image platform or private data audit failed')
                    expected = archive.read('LensAtlas/lens-atlas-image.tar.gz.sha256').decode().split()[0]
                    with archive.open('LensAtlas/lens-atlas-image.tar.gz') as image:
                        require(hashlib.file_digest(image, 'sha256').hexdigest() == expected,
                                'Embedded image checksum mismatch')
                    source = json.loads((ROOT / '.runtime/release-image-source-check.json').read_text(encoding='utf-8'))
                    require(source['verified_against_current_source'] and expected == source['image_archive_sha256'],
                            'Offline image source verification mismatch')
                    platform = 'linux/amd64'
                else:
                    require('LensAtlas/Dockerfile' in members and 'LensAtlas/backend/app.py' in members,
                            'Incomplete Docker source package')
                    require(version in archive.read('LensAtlas/backend/__init__.py').decode(), 'Version mismatch')
                    platform = 'docker/source-build (compose targets linux/amd64)'
            records.append({'file': name, 'platform': platform, 'bytes': path.stat().st_size,
                            'sha256': checksum, 'zip_crc': 'passed', 'private_runtime_files': 'excluded'})
    installer = output / f'LensAtlas-{version}-Setup-x64.exe'
    if installer.exists():
        checksum = digest(installer)
        build = json.loads(installer.with_suffix('.exe.build.json').read_text(encoding='utf-8'))
        verification = build.get('verification', {})
        require(build['sha256'] == checksum and not build['qa_identity'], 'Installer checksum or identity mismatch')
        require(installer.with_suffix('.exe.sha256').read_text().split()[0] == checksum,
                'Installer checksum sidecar mismatch')
        require(build['portable_sha256'] == records[0]['sha256'], 'Installer payload mismatch')
        require(verification.get('installer_sha256') == checksum
                and verification.get('qa_first_install') == 'passed'
                and verification.get('qa_same_version_overwrite') == 'passed'
                and verification.get('qa_uninstall') == 'passed'
                and verification.get('production_nonempty_directory_rejected') is True
                and verification.get('production_data_directory_rejected') is True
                and verification.get('production_environment_data_rejected') is True
                and verification.get('qa_previous_custom_directory_reused') is True
                and verification.get('application_data_preserved') is True
                and verification.get('synthetic_library_unchanged') is True,
                'Installer lifecycle verification is missing or incomplete')
        records.append({'file': installer.name, 'platform': 'windows/x64', 'bytes': installer.stat().st_size,
                        'sha256': checksum, 'private_runtime_files': 'same verified portable payload',
                        'installer_validation': build['install_upgrade_uninstall'],
                        'code_signed': build['code_signed']})
    report = {'version': version, 'verified_on': datetime.datetime.now().isoformat(timespec='seconds'),
              'windows': 'verified portable bundle; installer lifecycle tested with separate QA identity' if installer.exists()
                         else 'packaged runtime verified; installer not built',
              'docker_offline': 'repackaged verified image; application files matched release source',
              'native_macos_linux_and_arm64': 'not built or claimed', 'packages': records}
    (output / 'SHA256SUMS.txt').write_text(''.join(f'{r["sha256"]}  {r["file"]}\n' for r in records), encoding='utf-8')
    (output / '构建清单.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (ROOT / '.runtime/release-folder-audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()

