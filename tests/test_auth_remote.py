import threading
import time
import socket
import pytest
import uvicorn
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.config import Config
from conftest import make_jpeg,add_scan


def test_nas_initialization_auth_and_allowed_mapping(tmp_path):
    media=tmp_path/'mapped media';media.mkdir()
    config=Config(data_dir=tmp_path/'nas app',allowed_roots=[media])
    app=create_app(config,start_scanner=False)
    with TestClient(app) as c:
        assert c.get('/api/info').status_code==401
        assert c.get('/api/health').json()['setup_required']
        assert c.post('/api/auth/setup',json={'password':'safe-test-password','setup_code':'bad'}).status_code==403
        code=(config.data_dir/'setup-code.txt').read_text()
        assert c.post('/api/auth/setup',json={'password':'safe-test-password','setup_code':code}).status_code==200
        assert not (config.data_dir/'setup-code.txt').exists()
        assert c.post('/api/auth/setup',json={'password':'safe-test-password','setup_code':code}).status_code==409
        assert c.post('/api/auth/login',json={'password':'wrong-password'}).status_code==401
        token=c.post('/api/auth/login',json={'password':'safe-test-password'}).json()['token']
        c.headers['Authorization']='Bearer '+token
        assert c.get('/api/info').json()['desktop'] is False
        assert c.post('/api/roots',json={'path':str(tmp_path)}).status_code==403
        assert c.get('/api/browse',params={'path':str(tmp_path)}).status_code==403
        assert c.post('/api/roots',json={'path':str(media)}).status_code==200
        assert c.post('/api/roots',json={'path':str(media)},headers={'Origin':'http://evil.invalid'}).status_code==403
        assert c.get('/api/connections').status_code==404
        assert c.post('/api/auth/logout').status_code==200
        assert c.get('/api/info').status_code==401


def test_preview_tickets_reject_tampering_and_expiry(env):
    app,c,tmp=env;root=tmp/'signed';make_jpeg(root/'a.jpg');add_scan(app,c,root)
    url=c.post('/api/assets/query',json={}).json()['items'][0]['thumbnail_url']
    c.headers.pop('Authorization')
    assert c.get(url).status_code==200
    assert c.get(url+'&sig=bad').status_code==401
    assert c.get(url.replace('expires=','expires=0')).status_code==200  # numeric leading zero is same expiry
    assert c.get(url.split('?')[0]+'?expires=1&sig=bad').status_code==401
    assert c.post('/api/assets/query',json={}).status_code==401


def test_real_http_remote_connection_and_shared_library(env):
    local_app,client,tmp=env
    media=tmp/'NAS 合成 目录';make_jpeg(media/'remote.jpg')
    nas_config=Config(data_dir=tmp/'nas-data',allowed_roots=[media])
    nas=create_app(nas_config,start_scanner=False)
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(nas,host='127.0.0.1',port=port,log_level='error',access_log=False))
    thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
    deadline=time.time()+10
    while not server.started and time.time()<deadline:time.sleep(.02)
    assert server.started
    try:
        connection=client.post('/api/connections',json={'name':'Test NAS','url':f'http://127.0.0.1:{port}'}).json()
        cid=connection['id'];prefix=f'/api/remote/{cid}'
        assert client.get(prefix+'/api/health').json()['api_version']==1
        assert client.get(prefix+'/api/info').status_code==401
        code=(nas_config.data_dir/'setup-code.txt').read_text()
        assert client.post(prefix+'/api/auth/setup',json={'password':'test-nas-password','setup_code':code}).status_code==200
        login=client.post(prefix+'/api/auth/login',json={'password':'test-nas-password'})
        assert login.status_code==200 and 'token' not in login.json()
        assert client.get(prefix+'/api/info').status_code==200
        root=client.post(prefix+'/api/roots',json={'path':str(media)}).json()
        job=client.post(prefix+f"/api/roots/{root['id']}/scan").json()
        nas.state.scanner.run_job(job)
        result=client.post(prefix+'/api/assets/query',json={}).json()
        assert result['total']==1
        assert client.get(prefix+result['items'][0]['thumbnail_url']).status_code==200
        assert client.post('/api/stats',json={}).json()['summary']['count']==0
        # Independent clients carry filters in the request; no global filter mutation.
        assert client.post(prefix+'/api/stats',json={'cameras':['unmatched']}).json()['summary']['count']==0
        assert client.post(prefix+'/api/stats',json={}).json()['summary']['count']==1
        # Real HTTP read-only comparison: local snapshot + remote snapshot/hash worker.
        mirror=tmp/'mirror';make_jpeg(mirror/'remote.jpg')
        local_root,_=add_scan(local_app,client,mirror)
        nas.state.comparisons.start()
        local_app.state.comparisons.start()
        compare=client.post('/api/comparisons',json={'left':{'root_id':local_root['id']},'right':{'connection_id':cid,'root_id':root['id']},'verify':True})
        assert compare.status_code==200,compare.text
        compare_id=compare.json()['id']
        deadline=time.time()+20
        while time.time()<deadline:
            compared=client.get(f'/api/comparisons/{compare_id}').json()
            if compared['run']['status'] in {'completed','failed'}:break
            time.sleep(.05)
        assert compared['run']['status']=='completed',compared
        assert compared['summary'][0]['category']=='same' and compared['summary'][0]['count']==1
        # A remote stream ticket authorizes only the exact media URL and method.
        media_url=client.post(f'/api/connections/{cid}/media',json={'url':'/api/assets/1/stream?expires=9999999999&sig=fake'}).json()['url']
        client.headers.pop('Authorization')
        assert client.get(media_url).status_code==401  # upstream signature still required
        assert client.get(media_url.replace('/stream?','/thumbnail?')).status_code==401
        assert client.post(media_url).status_code==401
    finally:
        server.should_exit=True;thread.join(10)


def test_connection_validation_does_not_accept_credentials(env):
    _,c,_=env
    for url in ['file:///etc/passwd','http://user:password@nas:8765','http://nas/path','http://nas/?token=bad']:
        assert c.post('/api/connections',json={'name':'invalid','url':url}).status_code==400
    assert c.post('/api/connections',json={'name':'NAS A','url':'https://nas.example:8765'}).status_code==200
