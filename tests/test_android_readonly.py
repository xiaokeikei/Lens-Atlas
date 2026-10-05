"""Safety tripwire for the Android client's original-media access surface."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ANDROID = Path(__file__).resolve().parents[1] / "android"

def test_no_media_write_permissions_or_media_mutators():
    manifest = ET.parse(ANDROID / "app/src/main/AndroidManifest.xml")
    permissions = {p.attrib["{http://schemas.android.com/apk/res/android}name"] for p in manifest.findall("uses-permission")}
    assert not permissions & {"android.permission.WRITE_EXTERNAL_STORAGE", "android.permission.MANAGE_EXTERNAL_STORAGE", "android.permission.MANAGE_MEDIA"}
    sources = "\n".join(p.read_text(encoding="utf-8") for p in (ANDROID / "app/src/main/java").rglob("*.kt"))
    assert not re.search(r"(?:resolver|contentResolver)\s*\.\s*(?:insert|update|delete|applyBatch|bulkInsert|openOutputStream)\s*\(", sources)
    assert not re.search(r"\b(?:saveAttributes|createWriteRequest|createDeleteRequest|createTrashRequest|setRequireOriginal)\s*\(", sources)
    assert "openInputStream(uri)" in sources

def test_nas_redirects_cannot_bypass_readonly_policy():
    source = (ANDROID / "app/src/main/java/app/lensatlas/android/ReadOnlyNas.kt").read_text(encoding="utf-8")
    assert "require(NasPolicy.validTarget(method, path))" in source
    assert "instanceFollowRedirects = false" in source
    assert not re.search(r"(?:HostnameVerifier|TrustManager|setDefaultSSLSocketFactory)", source)
