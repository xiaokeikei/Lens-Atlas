import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

import pytest
from scripts import build_installer as installer


def fixture_bundle(tmp_path, extra=None):
    archive = tmp_path / "portable.zip"
    executable = b"MZ synthetic executable"
    files = {
        "LensAtlas/LensAtlas.exe": executable,
        "LensAtlas/LICENSE": b"license",
        "LensAtlas/THIRD_PARTY_NOTICES.md": b"notices",
        "LensAtlas/_internal/assets/lens-atlas.ico": b"icon",
    }
    if extra:
        files.update(extra)
    with zipfile.ZipFile(archive, "w") as bundle:
        for name, content in files.items():
            bundle.writestr(name, content)
    archive.with_suffix(".zip.sha256").write_text(installer.digest(archive) + "  portable.zip")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps({
        "path_isolated": True, "bundled_video_tools_verified": True,
        "window": True, "page": {"charts": 4},
        "executable_sha256": hashlib.sha256(executable).hexdigest(),
    }))
    return archive, evidence


@pytest.mark.parametrize("name", [
    "LensAtlas/../private.txt", "LensAtlas/C:/private.txt",
    "LensAtlas/_internal/../../private.txt", "LensAtlas/.runtime/library.sqlite3",
    "LensAtlas/.env", "LensAtlas/_internal/library.sqlite3-wal",
    "LensAtlas/_internal/private.log", "LensAtlas/_internal./file",
])
def test_reject_unsafe_or_private_bundle_members(tmp_path, name):
    archive, evidence = fixture_bundle(tmp_path, {name: b"private"})
    with pytest.raises(ValueError):
        installer.validate_portable(archive, evidence)


def test_reject_bundle_changed_after_checksum(tmp_path):
    archive, evidence = fixture_bundle(tmp_path)
    with archive.open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        installer.validate_portable(archive, evidence)


def test_reject_executable_not_verified(tmp_path):
    archive, evidence = fixture_bundle(tmp_path)
    report = json.loads(evidence.read_text())
    report["executable_sha256"] = "different"
    evidence.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="smoke verification"):
        installer.validate_portable(archive, evidence)


def test_accept_verified_bundle(tmp_path):
    archive, evidence = fixture_bundle(tmp_path)
    assert installer.validate_portable(archive, evidence)["files"] == 4


def test_case_collisions_rejected_on_windows(tmp_path):
    archive, evidence = fixture_bundle(tmp_path, {"LensAtlas/lensatlas.exe": b"collision"})
    with pytest.raises(ValueError, match="Duplicate"):
        installer.validate_portable(archive, evidence)


def test_failed_compiler_preserves_existing_release(tmp_path, monkeypatch):
    archive, evidence_path = fixture_bundle(tmp_path)
    evidence = installer.validate_portable(archive, evidence_path)
    output = tmp_path / "release"
    output.mkdir()
    target = output / f"LensAtlas-{installer.__version__}-Setup-x64.exe"
    target.write_bytes(b"previous release")
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0])
    monkeypatch.setattr(installer.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        installer.compile_installer(Path("ISCC.exe"), archive, output, evidence)
    assert target.read_bytes() == b"previous release"
    assert list(output.iterdir()) == [target]


def test_missing_explicit_compiler_fails_without_fallback(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        installer.find_compiler(tmp_path / "not-installed" / "ISCC.exe")

