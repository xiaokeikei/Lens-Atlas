from pathlib import Path
import subprocess
import pytest
from backend.metadata import classify,tool,normalize
from conftest import make_jpeg,add_scan


@pytest.mark.parametrize('ext',['CR2','CR3','NEF','NRW','ARW','RAF','ORF','RW2','PEF','DNG'])
def test_raw_extension_recognized_without_claiming_decoder_support(ext):
    assert classify(Path('synthetic.'+ext))==('photo',ext.lower())


def test_valid_jpeg_in_nef_container_name_is_not_real_raw_validation(env):
    app,c,tmp=env;root=tmp/'synthetic renamed fixture';make_jpeg(root/'fake.nef')
    _,job=add_scan(app,c,root)
    assert job['status']=='completed'
    item=c.post('/api/assets/query',json={}).json()['items'][0]
    assert item['camera']=='Test Camera A'
    # This is deliberately JPEG bytes with a RAW suffix: only fallback behavior is tested.
    assert item['preview_status']=='ready'


@pytest.mark.skipif(not tool('ffmpeg') or not tool('ffprobe'),reason='Portable FFmpeg tools unavailable')
def test_synthetic_video_metadata_cover_and_http_range(env):
    app,c,tmp=env;root=tmp/'合成 视频';root.mkdir()
    path=root/'测试 clip.mp4'
    p=subprocess.run([tool('ffmpeg'),'-nostdin','-v','error','-f','lavfi','-i','color=c=green:s=320x240:r=10','-t','1','-c:v','mpeg4','-metadata','creation_time=2024-04-05T06:07:08Z','-y',str(path)],capture_output=True,timeout=30)
    assert p.returncode==0,p.stderr
    _,job=add_scan(app,c,root)
    assert job['status']=='completed'
    item=c.post('/api/assets/query',json={}).json()['items'][0]
    assert item['kind']=='video' and item['duration']>=.9
    assert item['codec']=='mpeg4' and item['width']==320
    assert item['preview_status']=='ready'
    assert c.get(item['thumbnail_url']).status_code==200
    response=c.get(item['stream_url'],headers={'Range':'bytes=0-99'})
    assert response.status_code==206 and len(response.content)==100
    assert response.content==path.read_bytes()[:100]


def test_non_media_unknown_and_time_sources(env):
    assert classify(Path('notes.xmp'))[0]=='nonmedia'
    assert classify(Path('unknown.xyz'))[0]=='unknown'
    assert normalize({'File:FileModifyDate':'2025:01:01 00:00:00','QuickTime:CreateDate':'0000:00:00 00:00:00'})['taken_at'] is None


@pytest.mark.skipif(not tool('exiftool'), reason='ExifTool unavailable')
def test_text_disguised_as_raw_is_failed_not_missing_metadata(env):
    app, client, tmp = env
    root = tmp / '损坏 RAW 测试'
    root.mkdir()
    (root / 'invalid.cr3').write_bytes(b'INTENTIONALLY INVALID SYNTHETIC RAW FIXTURE')
    make_jpeg(root / 'valid.jpg', camera=None, lens=None, native=None, equiv=None, date=None)
    _, job = add_scan(app, client, root)
    assert job['status'] == 'completed'
    rows = app.state.db.rows('SELECT relpath,metadata_status,metadata_error,preview_status FROM assets')
    bad = next(row for row in rows if row['relpath'] == 'invalid.cr3')
    valid = next(row for row in rows if row['relpath'] == 'valid.jpg')
    assert bad['metadata_status'] == 'failed'
    assert '非媒体类型' in bad['metadata_error']
    assert bad['preview_status'] == 'failed'
    assert valid['metadata_status'] == 'ok'
    assert valid['preview_status'] == 'ready'
    assert client.post('/api/stats', json={}).json()['missing']['any']['count'] == 2
