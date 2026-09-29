import io
import json
import tarfile
from pathlib import Path

import pytest
from scripts.package_docker_release import ROOT, inspect_image, source_files


def make_saved_image(path, private_file=None, architecture="amd64"):
    layer = io.BytesIO()
    with tarfile.open(fileobj=layer, mode="w") as tar:
        data = b"application fixture"
        item = tarfile.TarInfo(private_file or "app/backend/__init__.py")
        item.size = len(data)
        tar.addfile(item, io.BytesIO(data))
    config = {"os": "linux", "architecture": architecture,
              "config": {"User": "app", "Cmd": ["python", "-m", "backend", "--port", "52032"]}}
    manifest = [{"Config": "config.json", "RepoTags": ["lens-atlas:0.1.2"], "Layers": ["layer/layer.tar"]}]
    with tarfile.open(path, "w:gz") as tar:
        for name, content in {"manifest.json": json.dumps(manifest).encode(),
                              "config.json": json.dumps(config).encode(),
                              "layer/layer.tar": layer.getvalue()}.items():
            item = tarfile.TarInfo(name)
            item.size = len(content)
            tar.addfile(item, io.BytesIO(content))


@pytest.mark.parametrize("private_file", ["data/library.sqlite3", "app/.env"])
def test_committed_personal_data_cannot_enter_release(tmp_path, private_file):
    archive = tmp_path / "image.tar.gz"
    make_saved_image(archive, private_file)
    with pytest.raises(ValueError, match="Private application data"):
        inspect_image(archive, "lens-atlas:0.1.2")


def test_release_accepts_only_matching_platform_and_tag(tmp_path):
    archive = tmp_path / "image.tar.gz"
    make_saved_image(archive)
    assert inspect_image(archive, "lens-atlas:0.1.2")["private_data_audit"] == "passed"
    with pytest.raises(ValueError, match="versioned image"):
        inspect_image(archive, "lens-atlas:wrong-version")
    make_saved_image(archive, architecture="arm64")
    with pytest.raises(ValueError, match="linux/amd64"):
        inspect_image(archive, "lens-atlas:0.1.2")


def test_source_release_does_not_include_installed_dependencies_or_local_data():
    files = [path.relative_to(ROOT) for path in source_files()]
    assert Path("backend/app.py") in files and Path(".env.example") in files
    assert not any(set(path.parts) & {".runtime", ".venv", "node_modules", "dist"} for path in files)
    assert not any(path.name == ".env" or path.suffix in {".db", ".sqlite3", ".log"} for path in files)
