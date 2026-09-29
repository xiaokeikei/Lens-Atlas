"""Run inside an isolated release container with temporary /data and /tmp."""
import json
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request
import urllib.error

from PIL import Image
from backend import __version__
from backend.metadata import extract, thumbnail, tool

for attempt in range(40):
    try:
        with urllib.request.urlopen('http://127.0.0.1:52032/api/health', timeout=2) as response:
            health = json.load(response)
        break
    except OSError:
        if attempt == 39:
            raise
        time.sleep(0.5)
assert health['version'] == __version__, health
assert health['setup_required'] is True, health
assert not list(Path('/media').iterdir()), 'Release test must not mount a personal library'
for name in ('exiftool', 'ffmpeg', 'ffprobe'):
    assert tool(name), name
with tempfile.TemporaryDirectory(prefix='lens-release-', dir='/tmp') as temporary:
    directory = Path(temporary)
    source = directory / 'synthetic.jpg'
    Image.new('RGB', (320, 240), '#26755f').save(source)
    assert extract(source)['metadata_status'] == 'ok'
    thumbnail(source, directory / 'photo-preview.jpg')
    video = directory / 'synthetic.mp4'
    subprocess.run([tool('ffmpeg'), '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                    'color=c=green:s=320x240:r=10', '-t', '1', '-c:v', 'mpeg4', str(video)],
                   check=True, timeout=30)
    assert extract(video)['metadata_status'] == 'ok'
    thumbnail(video, directory / 'video-preview.jpg')
    assert (directory / 'photo-preview.jpg').stat().st_size > 100
    assert (directory / 'video-preview.jpg').stat().st_size > 100
javascript = '\n'.join(path.read_text(encoding='utf-8') for path in Path('/app/frontend/dist/assets').glob('*.js'))
assert '使用前请先测试并备份' in javascript
assert '开发者概不负责' in javascript
assert '仅首次使用时提醒' in javascript

def api(path, body=None, token=None):
    request = urllib.request.Request('http://127.0.0.1:52032'+path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type':'application/json', **({'Authorization':'Bearer '+token} if token else {})})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)

try:
    api('/api/usage-notice/accept', {})
except urllib.error.HTTPError as error:
    assert error.code == 401
else:
    raise AssertionError('Unauthenticated notice acceptance was allowed')
api('/api/auth/setup', {'password':'synthetic-release-password','setup_code':Path('/data/setup-code.txt').read_text().strip()})
token = api('/api/auth/login', {'password':'synthetic-release-password'})['token']
assert api('/api/info', token=token)['usage_notice_accepted'] is False
assert api('/api/usage-notice/accept', {}, token)['usage_notice_accepted'] is True
assert api('/api/info', token=token)['usage_notice_accepted'] is True
from backend.db import Database
assert Database(Path('/data/library.sqlite3')).setting('usage_notice_accepted') is True
print(json.dumps({'version': __version__, 'network': 'none', 'temporary_data': True,
                  'health': 'passed', 'photo_and_video': 'passed', 'risk_notice': 'persisted-first-use'}))
