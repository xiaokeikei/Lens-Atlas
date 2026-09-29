"""Build a per-user installer from the already verified portable ZIP.

Never downloads/installs build tools. Compilation is staged; failures do not
replace an existing release. QA builds use a separate installation identity.
"""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import __version__


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def find_compiler(explicit=None):
    if explicit:
        path = Path(explicit).resolve()
        if not path.is_file():
            raise ValueError(f'ISCC.exe not found: {path}')
        return path
    candidates = [shutil.which('ISCC.exe')]
    for key in ('LOCALAPPDATA', 'ProgramFiles(x86)', 'ProgramFiles'):
        base = os.environ.get(key)
        if base:
            candidates.append(str(Path(base) / ('Programs/Inno Setup 6/ISCC.exe'
                                               if key == 'LOCALAPPDATA' else 'Inno Setup 6/ISCC.exe')))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
    raise ValueError('Inno Setup 6 compiler is missing. Install it manually, or pass --iscc <path-to-ISCC.exe>. No download was attempted.')


def validate_member(info):
    name = info.filename
    path = PurePosixPath(name)
    parts = path.parts
    if (not parts or parts[0] != 'LensAtlas' or len(parts) < 2
            or path.is_absolute() or '..' in parts or '\\' in name or ':' in name
            or any(p.endswith((' ', '.')) for p in parts)
            or stat.S_ISLNK(info.external_attr >> 16)):
        raise ValueError(f'Unsafe archive member: {name}')
    lowered = {p.lower() for p in parts}
    if (lowered & {'.runtime', '.venv', '.git', 'node_modules', '.env', 'setup-code.txt'}
            or path.name.lower().endswith(('.db', '.sqlite', '.sqlite3', '.log', '-wal', '-shm'))):
        raise ValueError(f'Private application data in archive: {name}')
    return path


def validate_portable(archive, evidence_path):
    expected = archive.with_suffix('.zip.sha256').read_text(encoding='utf-8').split()[0]
    actual = digest(archive)
    if actual != expected:
        raise ValueError('Portable ZIP checksum mismatch; rebuild the verified release.')
    evidence = json.loads(evidence_path.read_text(encoding='utf-8'))
    if not (evidence.get('path_isolated') and evidence.get('bundled_video_tools_verified')
            and evidence.get('window') and evidence.get('page', {}).get('charts') == 4):
        raise ValueError('Incomplete packaged application verification.')
    with zipfile.ZipFile(archive) as bundle:
        seen = set()
        for info in bundle.infolist():
            member = str(validate_member(info)).casefold()
            if member in seen:
                raise ValueError(f'Duplicate archive member: {member}')
            seen.add(member)
        required = {'lensatlas/lensatlas.exe', 'lensatlas/license',
                    'lensatlas/_internal/assets/lens-atlas.ico', 'lensatlas/third_party_notices.md'}
        if not required <= seen:
            raise ValueError('Incomplete portable bundle.')
        if bundle.testzip() is not None:
            raise ValueError('Portable ZIP CRC verification failed.')
        executable = hashlib.sha256(bundle.read('LensAtlas/LensAtlas.exe')).hexdigest()
        if executable != evidence.get('executable_sha256'):
            raise ValueError('Portable executable does not match the smoke verification.')
    return {'portable_sha256': actual, 'executable_sha256': executable, 'files': len(seen)}


def compile_installer(compiler, archive, output, evidence, qa=False):
    name = f'LensAtlas-{__version__}-Setup' + ('-QA' if qa else '') + '-x64.exe'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='lensatlas-installer-') as temporary:
        stage = Path(temporary)
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(stage)  # only the validated, checksummed portable release
        build_output = stage / 'output'
        command = [str(compiler), f'/DAppVersion={__version__}',
                   f'/DBundleDir={stage / "LensAtlas"}', f'/DBuildOutput={build_output}']
        if qa:
            command.append('/DInstallerQA=1')
        command.append(str(ROOT / 'installer' / 'LensAtlas.iss'))
        subprocess.run(command, cwd=ROOT, check=True)
        compiled = build_output / name
        if not compiled.is_file() or compiled.stat().st_size < 1024:
            raise ValueError('Compiler did not produce the expected installer.')
        with compiled.open('rb') as stream:
            if stream.read(2) != b'MZ':
                raise ValueError('Compiler output is not a Windows executable.')
        record = {**evidence, 'version': __version__, 'file': name,
                  'sha256': digest(compiled), 'bytes': compiled.stat().st_size,
                  'qa_identity': qa, 'compilation': 'passed',
                  'install_upgrade_uninstall': 'not yet verified', 'code_signed': False}
        pending = output / (name + '.pending')
        shutil.copy2(compiled, pending)
        pending.replace(output / name)
    (output / (name + '.sha256')).write_text(f'{record["sha256"]}  {name}\n', encoding='utf-8')
    (output / (name + '.build.json')).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT.parent / 'release')
    parser.add_argument('--portable', type=Path, help='Defaults to the Windows ZIP in output-dir')
    parser.add_argument('--iscc', type=Path)
    parser.add_argument('--check-only', action='store_true', help='Validate the ZIP and report compiler availability without compiling')
    parser.add_argument('--qa', action='store_true', help='Build a separately registered test installer into .runtime/installer-qa')
    args = parser.parse_args()
    output = args.output_dir.resolve()
    archive = (args.portable or output / f'LensAtlas-{__version__}-windows-x64.zip').resolve()
    try:
        evidence = validate_portable(archive, ROOT / '.runtime' / 'final-verification.json')
        if args.check_only:
            try:
                compiler = str(find_compiler(args.iscc))
            except ValueError as error:
                compiler = None
                evidence['compiler_error'] = str(error)
            print(json.dumps({**evidence, 'portable_validation': 'passed', 'compiler': compiler,
                              'ready_to_compile': compiler is not None}, indent=2))
            return 0 if compiler else 2
        compiler = find_compiler(args.iscc)
        if args.qa:
            output = ROOT / '.runtime' / 'installer-qa'
        print(json.dumps(compile_installer(compiler, archive, output, evidence, args.qa), indent=2))
        return 0
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        print(f'Installer build failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
