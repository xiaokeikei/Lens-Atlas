import json
from pathlib import Path
import pytest
from backend.metadata import extract,run_exiftool,tool,normalize,refresh_cached_metadata
from conftest import make_jpeg


@pytest.mark.skipif(not tool('exiftool'),reason='ExifTool not installed')
def test_unicode_path_uses_exiftool_itself_not_pillow_fallback(tmp_path):
    path=make_jpeg(tmp_path/'中文 路径'/'日本語 é 测试.jpg')
    result=run_exiftool(['-j','-n','-G1'],path)
    assert result.returncode==0
    tags=json.loads(result.stdout)[0]
    assert tags['ExifTool:ExifToolVersion']
    data=extract(path)
    assert data['metadata_status']=='ok'
    assert data['metadata_error'] is None
    assert data['focal_source']=='ExifIFD:FocalLengthIn35mmFormat'
    assert data['iso']==400
    assert not any(key.startswith('Pillow:') for key in json.loads(data['metadata_json']))


@pytest.mark.skipif(not tool('exiftool'),reason='ExifTool not installed')
def test_unicode_binary_preview_command_returns_real_embedded_jpeg(tmp_path):
    from PIL import Image
    import io
    # Create our own JPEG plus an embedded JPEG thumbnail, never depend on private files.
    path=make_jpeg(tmp_path/'嵌入 预览'/'preview.jpg')
    tiny=tmp_path/'tiny.jpg';Image.new('RGB',(32,24),'green').save(tiny)
    # This write is exclusively to a synthetic temporary test file.
    result=run_exiftool(['-overwrite_original','-ThumbnailImage<='+str(tiny)],path)
    assert result.returncode==0
    extracted=run_exiftool(['-b','-ThumbnailImage'],path)
    with Image.open(io.BytesIO(extracted.stdout)) as im:
        assert im.size==(32,24)


def test_pillow_iso_alias_is_preserved():
    assert normalize({'Pillow:ISOSpeedRatings':800})['iso']==800


def test_descriptive_vendor_lens_beats_raw_composite_identifier():
    result=normalize({'Composite:LensID':'2 26 10','Panasonic:LensType':'Test Lens 25/F1.7','IFD0:Make':'Test Vendor'})
    assert result['lens']=='Test Lens 25/F1.7'
    result=normalize({'Composite:LensID':172,'IFD0:Make':'Test Vendor'})
    assert result['lens']=='Test Vendor · Lens ID 172'


@pytest.mark.parametrize('sentinel',['NO-LENS','Unknown','Unknown (0)','n/a','----'])
def test_unknown_lens_markers_are_missing(sentinel):
    assert normalize({'ExifIFD:LensModel':sentinel})['lens'] is None


def test_cached_normalization_upgrade_preserves_records_and_never_reads_source(env):
    app,_,_=env;db=app.state.db
    rid=db.execute("INSERT INTO roots(path,label) VALUES('X:/deliberately-offline','offline')")
    db.execute("INSERT INTO assets(root_id,relpath,size,mtime_ns,kind,ext,lens,metadata_status,metadata_json) VALUES(?,'test.jpg',10,1,'photo','jpg','NO-LENS','ok',?)",(rid,json.dumps({'ExifIFD:LensModel':'NO-LENS','Pillow:ISOSpeedRatings':800})))
    db.set_setting('normalizer_version',1)
    assert refresh_cached_metadata(db)==1
    row=db.one('SELECT * FROM assets')
    assert row['lens'] is None and row['iso']==800
    assert row['size']==10 and row['metadata_status']=='ok'
    assert refresh_cached_metadata(db)==0
