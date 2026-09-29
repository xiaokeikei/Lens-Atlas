import hashlib
import os
import time
from pathlib import Path
import pytest
from backend.comparison import ComparisonInput, InventoryInput
from conftest import make_jpeg, add_scan


def run_comparison(app, client, left, right, verify=False):
    payload={'left': {'root_id':left['id']}, 'right': {'root_id':right['id']}, 'verify':verify}
    response=client.post('/api/comparisons',json=payload)
    assert response.status_code==200,response.text
    rid=response.json()['id']
    app.state.comparisons.start()
    deadline=time.monotonic()+25
    while time.monotonic()<deadline:
        result=client.get(f'/api/comparisons/{rid}').json()
        if result['run']['status'] in {'completed','failed'}:
            assert result['run']['status']=='completed',result
            return rid,result
        time.sleep(.05)
    pytest.fail('comparison timeout')


def test_quick_and_full_comparison_readonly_and_moves(env):
    app,c,tmp=env
    left,right=tmp/'A 相册',tmp/'B 相册'
    for root in [left,right]:
        make_jpeg(root/'same.jpg')
        (root/'same-size.bin').write_bytes(b'AAA' if root==left else b'BBB')
        (root/'different.bin').write_bytes(b'A' if root==left else b'BB')
    (left/'=left-only.txt').write_bytes(b'left')
    (right/'right-only.txt').write_bytes(b'right')
    (left/'old-name.bin').write_bytes(b'moved content')
    (right/'new-name.bin').write_bytes(b'moved content')
    roots=[add_scan(app,c,r)[0] for r in [left,right]]
    before={str(p):(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns,p.stat().st_size) for r in [left,right] for p in r.rglob('*') if p.is_file()}
    rid,result=run_comparison(app,c,*roots)
    groups={s['category']:s['count'] for s in result['summary']}
    assert groups=={'different':1,'only_left':2,'only_right':2,'pending':2}
    assert not result['move_hints']
    export=c.get(f'/api/comparisons/{rid}/export')
    assert export.status_code==200 and "'=left-only.txt" in export.text
    # Start only once; service loop already runs.
    response=c.post('/api/comparisons',json={'left':{'root_id':roots[0]['id']},'right':{'root_id':roots[1]['id']},'verify':True})
    rid=response.json()['id']
    deadline=time.monotonic()+25
    while time.monotonic()<deadline:
        result=c.get(f'/api/comparisons/{rid}').json()
        if result['run']['status'] in {'completed','failed'}:break
        time.sleep(.05)
    assert result['run']['status']=='completed',result
    groups={s['category']:s['count'] for s in result['summary']}
    assert groups=={'different':2,'only_left':2,'only_right':2,'same':1}
    assert result['move_hints']==[{'left_path':'old-name.bin','right_path':'new-name.bin','size':13}]
    page=c.get(f'/api/comparisons/{rid}?category=different').json()
    assert page['total']==2 and all(r['category']=='different' for r in page['items'])
    after={str(p):(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns,p.stat().st_size) for r in [left,right] for p in r.rglob('*') if p.is_file()}
    assert before==after


def test_inventory_rejects_incomplete_offline_traversal_and_excludes_stale(env):
    app,c,tmp=env
    root=tmp/'source';make_jpeg(root/'one.jpg');make_jpeg(root/'gone.jpg')
    rid,_=add_scan(app,c,root)
    # Simulate a user moving a source between scans, outside application operations.
    (root/'gone.jpg').rename(tmp/'moved-fixture.jpg')
    add_scan(app,c,root)
    assert app.state.db.one('SELECT COUNT(*) n FROM assets')['n']==2
    inv=c.post('/api/inventories',json={'root_id':rid['id']}).json()
    assert inv['total']==1
    assert c.get(f'/api/inventories/{inv["id"]}/entries').json()['items'][0]['relpath']=='one.jpg'
    assert c.post('/api/inventories',json={'root_id':rid['id'],'subpath':'../escape'}).status_code==400
    c.post(f'/api/roots/{rid["id"]}/scan',json={})
    assert c.post('/api/inventories',json={'root_id':rid['id']}).status_code==409
    assert c.get(f'/api/inventories/{inv["id"]}').status_code==409
    root.rename(tmp/'offline-fixture')
    assert c.post('/api/inventories',json={'root_id':rid['id']}).status_code==409


def test_changed_file_is_error_not_same_and_hash_can_resume(env):
    app,c,tmp=env
    root=tmp/'source';make_jpeg(root/'a.jpg');make_jpeg(root/'b.jpg')
    rid,_=add_scan(app,c,root)
    inv=c.post('/api/inventories',json={'root_id':rid['id']}).json()
    (root/'a.jpg').write_bytes(b'changed fixture')
    assert c.post(f'/api/inventories/{inv["id"]}/resume',json={}).status_code==200
    assert c.post(f'/api/inventories/{inv["id"]}/pause',json={}).status_code==200
    assert c.get(f'/api/inventories/{inv["id"]}').json()['status']=='paused'
    assert c.post(f'/api/inventories/{inv["id"]}/resume',json={}).status_code==200
    app.state.comparisons.start()
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        info=c.get(f'/api/inventories/{inv["id"]}').json()
        if info['status']=='completed':break
        time.sleep(.05)
    assert info['processed']==2 and info['errors']==1
    entries=c.get(f'/api/inventories/{inv["id"]}/entries').json()['items']
    assert entries[0]['error'] and entries[0]['sha256'] is None
    assert len(entries[1]['sha256'])==64


def test_comparison_requires_auth_and_subdirectory_mapping(env):
    app,c,tmp=env
    root=tmp/'source';make_jpeg(root/'nested'/'one.jpg');make_jpeg(root/'other.jpg')
    rid,_=add_scan(app,c,root)
    inv=c.post('/api/inventories',json={'root_id':rid['id'],'subpath':'nested'}).json()
    assert inv['total']==1
    assert c.get(f'/api/inventories/{inv["id"]}/entries').json()['items'][0]['relpath']=='one.jpg'
    c.headers.pop('Authorization')
    for path in ['/api/comparisons',f'/api/inventories/{inv["id"]}',f'/api/inventories/{inv["id"]}/entries']:
        assert c.get(path).status_code==401
