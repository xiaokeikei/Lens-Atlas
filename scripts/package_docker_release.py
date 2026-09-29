"""Create allowlisted online sources and an optional self-contained Docker bundle.

No registry publishing, dependency downloads, personal configuration or app data.
The supplied offline archive must come from `docker image save`, never `commit`.
"""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import __version__

SOURCE_FILES = ['Dockerfile', 'compose.yaml', 'compose.registry.yaml', '.dockerignore', '.gitignore',
                '.env.example', 'requirements-server.txt', 'README.md', 'DOCKER_RELEASES.md',
                'LICENSE', 'THIRD_PARTY_NOTICES.md', 'VALIDATION.md', 'CHANGELOG.md',
                'frontend/package.json', 'frontend/package-lock.json', 'frontend/index.html',
                'frontend/tsconfig.json', 'frontend/tsconfig.app.json', 'frontend/tsconfig.node.json',
                'frontend/vite.config.ts', 'scripts/reset_admin.py', 'scripts/package_docker_release.py']


def source_files():
    files = [ROOT / name for name in SOURCE_FILES]
    for folder in ['backend', 'frontend/src', 'frontend/public', 'docs/screenshots']:
        files.extend(path for path in (ROOT / folder).rglob('*')
                     if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc')
    return sorted(set(path for path in files if path.is_file()))


def inspect_image(archive, expected_tag):
    with tarfile.open(archive, 'r:*') as tar:
        members = {member.name: member for member in tar.getmembers()}
        if 'manifest.json' not in members:
            raise ValueError('Expected a Docker image save archive with manifest.json')
        manifest = json.load(tar.extractfile(members['manifest.json']))
        if len(manifest) != 1 or expected_tag not in (manifest[0].get('RepoTags') or []):
            raise ValueError('Archive must contain exactly the requested versioned image')
        entry = manifest[0]
        for name in [entry['Config'], *entry['Layers']]:
            if PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts or name not in members:
                raise ValueError('Invalid or missing image member')
        config = json.load(tar.extractfile(members[entry['Config']]))
        if config.get('os') != 'linux' or config.get('architecture') != 'amd64':
            raise ValueError('Only a verified linux/amd64 image can enter this release')
        runtime = config.get('config', {})
        if runtime.get('User') not in {'app', '1000'} or '52032' not in runtime.get('Cmd', []):
            raise ValueError('Unexpected runtime user or default port')
        # Inspect the image rather than trusting the uploader's filename. Application
        # volumes must not have been baked into a committed container image.
        for layer in entry['Layers']:
            with tarfile.open(fileobj=tar.extractfile(members[layer]), mode='r|*') as contents:
                for member in contents:
                    name = member.name.lstrip('./')
                    parts = PurePosixPath(name).parts
                    if member.isfile() and (name.startswith(('data/', 'media/')) or
                                             '.runtime' in parts or
                                             PurePosixPath(name).name in {'.env', 'library.sqlite3', 'setup-code.txt'}):
                        raise ValueError('Private application data found in image layer')
        return {'tag': expected_tag, 'platform': 'linux/amd64',
                'config_sha256': hashlib.sha256(tar.extractfile(members[entry['Config']]).read()).hexdigest(),
                'layers': len(entry['Layers']), 'private_data_audit': 'passed'}


def checksum(path):
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    path.with_suffix(path.suffix + '.sha256').write_text(digest + '  ' + path.name + '\n', encoding='utf-8')
    return digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image-archive', type=Path)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist', help='Directory for installation packages and checksums')
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(exist_ok=True)
    online = output / f'LensAtlas-{__version__}-docker-online.zip'
    with zipfile.ZipFile(online, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in source_files():
            bundle.write(path, 'LensAtlas/' + path.relative_to(ROOT).as_posix())
    results = [{'package': online.name, 'bytes': online.stat().st_size, 'sha256': checksum(online)}]
    if args.image_archive:
        tag = 'lens-atlas:' + __version__
        evidence = inspect_image(args.image_archive, tag)
        offline = output / f'LensAtlas-{__version__}-docker-offline-amd64.zip'
        compose = (ROOT / 'compose.yaml').read_text(encoding='utf-8')
        compose = compose.replace('    build: .\n', '').replace('    image: ' + tag + '\n',
                                                                  '    image: ' + tag + '\n    pull_policy: never\n')
        with zipfile.ZipFile(offline, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr('LensAtlas/compose.yaml', compose)
            bundle.write(args.image_archive, 'LensAtlas/lens-atlas-image.tar.gz', compress_type=zipfile.ZIP_STORED)
            for name in ['.env.example', 'README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'VALIDATION.md', 'DOCKER_RELEASES.md', 'CHANGELOG.md']:
                bundle.write(ROOT / name, 'LensAtlas/' + name)
            for screenshot in (ROOT / 'docs' / 'screenshots').glob('*.png'):
                bundle.write(screenshot, 'LensAtlas/docs/screenshots/' + screenshot.name)
            bundle.write(ROOT / 'scripts/reset_admin.py', 'LensAtlas/scripts/reset_admin.py')
            bundle.writestr('LensAtlas/image-manifest.json', json.dumps(evidence, indent=2) + '\n')
            bundle.writestr('LensAtlas/lens-atlas-image.tar.gz.sha256', checksum(args.image_archive) + '  lens-atlas-image.tar.gz\n')
        results.append({'package': offline.name, 'bytes': offline.stat().st_size, 'sha256': checksum(offline)})
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
