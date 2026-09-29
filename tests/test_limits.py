from pathlib import Path
import time
import pytest
from conftest import make_jpeg,add_scan


def test_permission_is_distinct_from_parse_failure(env,monkeypatch):
    app,c,tmp=env;root=tmp/'permission';make_jpeg(root/'denied.jpg')
    def denied(args):raise PermissionError('synthetic permission denial')
    monkeypatch.setattr(app.state.scanner,'worker',denied)
    _,job=add_scan(app,c,root)
    assert job['status']=='completed'
    item=app.state.db.one('SELECT * FROM assets')
    assert item['metadata_status']=='permission_denied'
    assert item['preview_status']=='permission_denied'


def test_cache_limit_evicts_oldest_without_changing_index(env):
    app,c,tmp=env
    cache=app.state.config.data_dir/'cache'
    for i in range(3):
        p=cache/f'{i}.jpg';p.write_bytes(b'x'*7000000)
        import os
        os.utime(p,(time.time()+i,time.time()+i))
    response=c.put('/api/cache',json={'limit_bytes':16*1024**2})
    assert response.status_code==200
    assert response.json()['bytes']<=16*1024**2
    assert not (cache/'0.jpg').exists()
    assert (cache/'2.jpg').exists()


def test_random_request_limit_is_bounded(env):
    _,c,_=env
    assert c.post('/api/assets/query',json={'limit':1000000}).status_code==422
    assert c.post('/api/assets/query',json={'offset':-1}).status_code==422


def test_path_traversal_in_index_is_rejected(env):
    app,c,tmp=env;root=tmp/'confined';make_jpeg(root/'safe.jpg');add_scan(app,c,root)
    row=app.state.db.one('SELECT a.*,r.path root_path FROM assets a JOIN roots r ON a.root_id=r.id')
    row['relpath']='../private.jpg'
    with pytest.raises(PermissionError):app.state.scanner.source_path(row)
