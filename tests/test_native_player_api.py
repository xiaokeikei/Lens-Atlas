from pathlib import Path
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.config import Config


def test_native_player_only_opens_scoped_local_media_urls(tmp_path):
    calls=[]
    config=Config(data_dir=tmp_path/'data',desktop=True,local_token='local-test',local_origin='http://127.0.0.1:9876',native_player=lambda *args:calls.append(args),native_player_status=lambda:{'status':'video_ready'})
    with TestClient(create_app(config,start_scanner=False)) as client:
        assert client.post('/api/player/open',json={'url':'/api/assets/1/stream'}).status_code==401
        client.headers['Authorization']='Bearer local-test'
        for url in ['file:///private.mp4','https://untrusted.example/movie.mp4','//untrusted.example/test','/api/auth/login','/api/assets/1/thumbnail','/api/assets/1/stream#fragment']:
            assert client.post('/api/player/open',json={'url':url}).status_code==400
        result=client.post('/api/player/open',json={'url':'/api/assets/1/stream?expires=123&sig=test','title':'test'}).json()
        assert calls[0]==('http://127.0.0.1:9876/api/assets/1/stream?expires=123&sig=test','test',result['request_id'])
        assert client.get('/api/player/status').json()['status']=='video_ready'


def test_browser_server_has_no_native_player(tmp_path):
    with TestClient(create_app(Config(data_dir=tmp_path/'nas'),start_scanner=False)) as c:
        assert c.post('/api/player/open',json={'url':'/api/assets/1/stream'}).status_code==401


def test_media_ranges_and_head(env):
    app,client,tmp=env
    root=tmp/'range-media';root.mkdir()
    (root/'test.mp4').write_bytes(b'0123456789')
    rid=client.post('/api/roots',json={'path':str(root)}).json()['id']
    app.state.db.execute("INSERT INTO assets(root_id,relpath,size,mtime_ns,kind,ext) VALUES(?,'test.mp4',10,1,'video','mp4')",(rid,))
    url=client.post('/api/assets/query',json={}).json()['items'][0]['stream_url']
    assert client.get(url).content==b'0123456789'
    head=client.head(url)
    assert head.status_code==200 and head.content==b'' and head.headers['content-length']=='10'
    for value,expected in [('bytes=2-4',b'234'),('bytes=-3',b'789'),('bytes=8-',b'89'),('bytes=8-99',b'89')]:
        response=client.get(url,headers={'Range':value})
        assert response.status_code==206 and response.content==expected
    for value in ['bytes=99-100','bytes=5-2','bytes=-0','bytes=-','bytes=foo','bytes=0-1,5-6']:
        response=client.get(url,headers={'Range':value})
        assert response.status_code==416 and response.headers['content-range']=='bytes */10'
