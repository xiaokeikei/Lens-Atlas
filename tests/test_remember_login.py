import os
import socket
import threading
import time
import pytest
import uvicorn
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.config import Config
from backend.credentials import CredentialStore
from backend.db import Database


@pytest.mark.skipif(os.name!='nt',reason='Windows DPAPI user-bound credential store')
def test_dpapi_encrypted_user_storage(tmp_path):
    db=Database(tmp_path/'test.sqlite3')
    store=CredentialStore(db)
    token='synthetic-sensitive-session'
    store.save('peer',token)
    assert token not in db.setting('credential:peer')
    assert store.load('peer')==token
    store.forget('peer')
    assert store.load('peer') is None


@pytest.mark.skipif(os.name!='nt',reason='Windows remembered desktop login')
def test_remember_survives_desktop_restart_and_logout_revokes(tmp_path):
    nas_config=Config(data_dir=tmp_path/'nas')
    nas=create_app(nas_config,start_scanner=False)
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(nas,log_level='error',access_log=False))
    thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
    deadline=time.monotonic()+10
    while not server.started and time.monotonic()<deadline:time.sleep(.02)
    assert server.started
    cfg=Config(data_dir=tmp_path/'desktop',desktop=True,local_token='test-client')
    try:
        first=create_app(cfg,start_scanner=False)
        with TestClient(first,headers={'Authorization':'Bearer test-client'}) as c:
            peer=c.post('/api/connections',json={'name':'Test','url':f'http://127.0.0.1:{port}'}).json()
            prefix=f'/api/remote/{peer["id"]}'
            setup=(nas_config.data_dir/'setup-code.txt').read_text()
            assert c.post(prefix+'/api/auth/setup',json={'password':'synthetic-password','setup_code':setup}).status_code==200
            assert c.post(prefix+'/api/auth/login',json={'password':'synthetic-password','remember':True}).status_code==200
            stored=first.state.db.setting('credential:'+peer['id'])
            assert stored and 'synthetic-password' not in stored
            assert c.get('/api/desktop/preferences').json()['last_connection']==peer['id']
            session=nas.state.db.one('SELECT expires FROM sessions')
            assert session['expires']>time.time()+29*86400
        second=create_app(cfg,start_scanner=False)
        with TestClient(second,headers={'Authorization':'Bearer test-client'}) as c:
            assert c.get(prefix+'/api/info').status_code==200
            assert c.get('/api/connections').json()[0]['remembered'] is True
            assert c.post(prefix+'/api/auth/logout',json={}).status_code==200
            assert c.get(prefix+'/api/info').status_code==401
            assert second.state.db.setting('credential:'+peer['id']) is None
            assert nas.state.db.one('SELECT COUNT(*) n FROM sessions')['n']==0
            assert c.post(prefix+'/api/auth/login',json={'password':'synthetic-password','remember':False}).status_code==200
        third=create_app(cfg,start_scanner=False)
        with TestClient(third,headers={'Authorization':'Bearer test-client'}) as c:
            assert c.get(prefix+'/api/info').status_code==401
            assert c.get('/api/connections').json()[0]['remembered'] is False
    finally:
        server.should_exit=True;thread.join(10)


@pytest.mark.skipif(os.name!='nt',reason='Windows remembered desktop login')
def test_unreachable_peer_does_not_clear_saved_credentials(env):
    app,c,tmp=env
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
    peer=c.post('/api/connections',json={'name':'Offline','url':f'http://127.0.0.1:{port}'}).json()
    CredentialStore(app.state.db).save(peer['id'],'synthetic-offline-session')
    assert c.get(f'/api/remote/{peer["id"]}/api/info').status_code==502
    assert CredentialStore(app.state.db).load(peer['id'])=='synthetic-offline-session'
    # Logout clears this connection even without network access.
    c.post(f'/api/remote/{peer["id"]}/api/auth/logout',json={})
    assert CredentialStore(app.state.db).load(peer['id']) is None
