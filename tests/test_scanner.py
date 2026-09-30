from pathlib import Path
import hashlib
import os
import subprocess
import pytest
from backend.db import Database
from backend.scanner import Scanner
from backend.config import Config
from conftest import make_jpeg,add_scan


def test_actual_scan_unicode_space_preview_and_persistence(env):
    app,c,tmp=env
    root=tmp/'合成 摄影测试'/'多层 子目录';root.mkdir(parents=True)
    p=make_jpeg(root/'中文 sample.jpg')
    original=hashlib.sha256(p.read_bytes()).hexdigest()
    (root/'notes.txt').write_text('synthetic')
    (root/'unidentified.zzz').write_bytes(b'unknown')
    _,job=add_scan(app,c,root)
    assert job['status']=='completed',job
    data=c.post('/api/assets/query',json={}).json()
    assert data['total']==1
    item=data['items'][0]
    assert item['camera']=='Test Camera A'
    assert item['lens']=='Test Lens 35'
    assert item['focal_native']==35 and item['focal_equiv']==50
    assert item['taken_at'].startswith('2024-05-06T12:30:00')
    assert c.get(item['thumbnail_url']).status_code==200
    assert hashlib.sha256(p.read_bytes()).hexdigest()==original
    reopened=Database(app.state.db.path)
    assert reopened.one('SELECT COUNT(*) n FROM assets')['n']==3
    assert reopened.setting('library_id')==app.state.db.setting('library_id')


def test_incremental_unchanged_skips_worker_changed_reextracts(env,monkeypatch):
    app,c,tmp=env;root=tmp/'pictures';p=make_jpeg(root/'one.jpg');add_scan(app,c,root)
    original=app.state.scanner.worker;calls=[]
    def tracked(args):calls.append(args[0]);return original(args)
    monkeypatch.setattr(app.state.scanner,'worker',tracked)
    _,job=add_scan(app,c,root)
    assert job['status']=='completed' and calls==[]
    make_jpeg(p,camera='Changed Camera',native=85,equiv=85,color='#728390')
    _,job=add_scan(app,c,root)
    assert 'metadata' in calls and 'preview' in calls
    assert c.post('/api/assets/query',json={}).json()['items'][0]['camera']=='Changed Camera'


def test_pause_resume_after_partial_enumeration(env,monkeypatch):
    app,c,tmp=env;root=tmp/'resume files';make_jpeg(root/'a.jpg');make_jpeg(root/'b.jpg')
    rid=c.post('/api/roots',json={'path':str(root)}).json()['id']
    job=c.post(f'/api/roots/{rid}/scan').json()
    original=app.state.scanner.check;checks=[0]
    def pause(jid):
        checks[0]+=1
        if checks[0]==4:app.state.scanner.control(jid,'pause')
        original(jid)
    monkeypatch.setattr(app.state.scanner,'check',pause)
    app.state.scanner.run_job(job)
    assert app.state.db.one('SELECT status FROM jobs WHERE id=?',(job['id'],))['status']=='paused'
    monkeypatch.setattr(app.state.scanner,'check',original)
    app.state.scanner.control(job['id'],'resume')
    app.state.scanner.run_job(app.state.db.one('SELECT * FROM jobs WHERE id=?',(job['id'],)))
    assert c.post('/api/stats',json={}).json()['summary']['count']==2
    assert len(app.state.db.rows('SELECT * FROM assets'))==2


def test_crash_restart_preserves_work_and_marks_paused(env):
    app,c,tmp=env;root=tmp/'restart';make_jpeg(root/'a.jpg');r,_=add_scan(app,c,root)
    job=c.post(f"/api/roots/{r['id']}/scan").json()
    app.state.db.execute("UPDATE jobs SET status='running' WHERE id=?",(job['id'],))
    restarted=Scanner(Database(app.state.db.path),app.state.config)
    saved=app.state.db.one('SELECT * FROM jobs WHERE id=?',(job['id'],))
    assert saved['status']=='paused'
    restarted.control(job['id'],'resume')
    restarted.run_job(app.state.db.one('SELECT * FROM jobs WHERE id=?',(job['id'],)))
    assert c.post('/api/stats',json={}).json()['summary']['count']==1


def test_offline_or_incomplete_scan_never_removes_index(env,monkeypatch):
    app,c,tmp=env;root=tmp/'drive';make_jpeg(root/'a.jpg');r,_=add_scan(app,c,root)
    root.rename(tmp/'disconnected-drive')
    _,job=add_scan(app,c,root)
    assert job['status']=='failed'
    assert app.state.db.one('SELECT status FROM roots WHERE id=?',(r['id'],))['status']=='offline'
    assert c.post('/api/stats',json={}).json()['summary']['count']==1
    (tmp/'disconnected-drive').rename(root)
    def incomplete(*args,**kwargs):raise PermissionError('simulated unavailable subfolder')
    monkeypatch.setattr('backend.scanner.os.walk',incomplete)
    # Failure is resumable, not automatically selected by a fresh scan request.
    c.post(f"/api/jobs/{job['id']}/resume")
    app.state.scanner.run_job(app.state.db.one('SELECT * FROM jobs WHERE id=?',(job['id'],)))
    assert c.post('/api/stats',json={}).json()['summary']['count']==1


def test_unreadable_subdirectory_is_skipped_and_reported(env,monkeypatch):
    app,c,tmp=env
    root=tmp/'partial';blocked=root/'blocked'
    make_jpeg(root/'visible.jpg');make_jpeg(blocked/'historical.jpg')
    r,_=add_scan(app,c,root)
    original_walk=os.walk

    def partial_walk(top, followlinks=False, onerror=None):
        if Path(top) != root:
            yield from original_walk(top, followlinks=followlinks, onerror=onerror)
            return
        yield str(root), [], ['visible.jpg']
        onerror(PermissionError(13, 'Permission denied', str(blocked)))

    monkeypatch.setattr('backend.scanner.os.walk',partial_walk)
    _,job=add_scan(app,c,root)
    assert job['status']=='completed'
    assert job['errors']==1
    assert '跳过 1 个无权限目录' in job['message']
    saved=app.state.db.one('SELECT * FROM roots WHERE id=?',(r['id'],))
    assert saved['status']=='online'
    assert '历史索引已保留' in saved['error']
    assert c.post('/api/stats',json={}).json()['summary']['count']==2


def test_timeout_and_bad_file_dont_block_valid_statistics(env,monkeypatch):
    app,c,tmp=env;root=tmp/'failures';make_jpeg(root/'good.jpg');(root/'bad.cr3').write_bytes(b'invalid synthetic raw')
    original=app.state.scanner.worker
    def worker(args):
        if 'bad.cr3' in args[1]:raise subprocess.TimeoutExpired('synthetic',.1)
        return original(args)
    monkeypatch.setattr(app.state.scanner,'worker',worker)
    _,job=add_scan(app,c,root)
    assert job['status']=='completed' and job['errors']==2
    data=c.post('/api/stats',json={}).json()
    assert data['summary']['count']==2
    assert data['cameras'][0]['count']==1
    assert app.state.db.one("SELECT metadata_error FROM assets WHERE relpath='bad.cr3'")['metadata_error']=='单文件处理超时'


def test_clear_cache_preserves_originals_and_statistics(env):
    app,c,tmp=env;root=tmp/'cache';p=make_jpeg(root/'a.jpg');add_scan(app,c,root)
    before=c.post('/api/stats',json={}).json()
    assert c.delete('/api/cache').json()['bytes']==0 and p.exists()
    after=c.post('/api/stats',json={}).json()
    assert before['summary']==after['summary']
    item=c.post('/api/assets/query',json={}).json()['items'][0]
    assert c.get(item['thumbnail_url']).status_code==200


def test_reject_overlapping_roots_and_app_data(env):
    app,c,tmp=env;root=tmp/'roots';make_jpeg(root/'child'/'a.jpg');add_scan(app,c,root)
    assert c.post('/api/roots',json={'path':str(root/'child')}).status_code==409
    assert c.post('/api/roots',json={'path':str(app.state.config.data_dir)}).status_code==400


def test_empty_previously_indexed_directory_is_suspect(env):
    app,c,tmp=env;root=tmp/'empty';p=make_jpeg(root/'a.jpg');add_scan(app,c,root)
    p.rename(tmp/'moved-synthetic.jpg')
    _,job=add_scan(app,c,root)
    assert job['status']=='failed'
    assert c.post('/api/stats',json={}).json()['summary']['count']==1


def test_backup_is_consistent_and_reopenable(env):
    app,c,tmp=env;root=tmp/'backup';make_jpeg(root/'a.jpg');add_scan(app,c,root)
    assert c.post('/api/backup').status_code==200
    backup=Database(app.state.config.data_dir/'backup.sqlite3')
    assert backup.one('SELECT COUNT(*) n FROM assets')['n']==1
