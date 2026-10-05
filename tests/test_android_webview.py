from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_webview_bridge_only_loads_bundled_assets():
    source = (ROOT / 'android/app/src/main/java/app/lensatlas/android/AndroidActivity.kt').read_text(encoding='utf-8')
    assert 'allowFileAccess=false' in source
    assert 'allowContentAccess=false' in source
    assert 'WebSettings.MIXED_CONTENT_NEVER_ALLOW' in source
    assert 'uri.host=="appassets.androidplatform.net"' in source
    assert '403,"Blocked"' in source
    assert "connect-src 'none'" in source
    assert 'web.addJavascriptInterface(Bridge(),"LensAndroid")' in source
    assert 'else->error("只读客户端禁止此操作")' in source
    assert 'setAllowUniversalAccessFromFileURLs' not in source


def test_mobile_reuses_desktop_charts():
    mobile = (ROOT / 'frontend/src/MobileApp.tsx').read_text(encoding='utf-8')
    desktop = (ROOT / 'frontend/src/App.tsx').read_text(encoding='utf-8')
    assert "from './LibraryWidgets'" in mobile and "from './LibraryWidgets'" in desktop
    assert "from './FocalChart'" in mobile and "from './FocalChart'" in desktop
    assert '<Chart title="相机"' in mobile
    assert '<FocalChart' in mobile
    assert 'photo-grid' in mobile
