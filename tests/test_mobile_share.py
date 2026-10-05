from pathlib import Path
import hashlib
import time

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Config
from backend.mobile_share import create_gateway, allowed, MobileShareController
from conftest import make_jpeg


@pytest.fixture
def shared(tmp_path):
    service = create_app(Config(data_dir=tmp_path/'app-data', desktop=True, local_token='SYNTHETIC-local-secret'), start_scanner=False)
    gateway = create_gateway(service)
    gateway.state.credentials.set_password('SyntheticPhone123!')
    with TestClient(gateway, client=('127.0.0.1', 50000)) as client:
        yield service, gateway, client, tmp_path


def login(client):
    result = client.post('/api/auth/login', json={'password': 'SyntheticPhone123!', 'remember': True})
    assert result.status_code == 200
    assert result.json()['expires_in'] == 30*86400
    token = result.json()['token']
    client.headers['Authorization'] = 'Bearer ' + token
    return token


def test_auth_is_separate_and_persists_across_gateway_restart(shared):
    service, gateway, client, _ = shared
    assert client.get('/api/info').status_code == 401
    client.headers['Authorization'] = 'Bearer SYNTHETIC-local-secret'
    assert client.get('/api/info').status_code == 401
    token = login(client)
    assert client.get('/api/info').json()['library_kind'] == 'computer'
    assert client.get('/api/health').json()['desktop'] is False
    new_gateway = create_gateway(service)
    with TestClient(new_gateway, client=('127.0.0.1', 50001)) as restarted:
        restarted.headers['Authorization'] = 'Bearer ' + token
        assert restarted.post('/api/stats', json={}).status_code == 200
        assert restarted.post('/api/auth/logout', json={}).status_code == 200
    assert client.get('/api/info').status_code == 401


def test_phone_scans_registered_root_using_same_index_without_source_changes(shared):
    service, _, client, tmp = shared
    photo = make_jpeg(tmp/'synthetic-media'/'fixture.jpg')
    original = hashlib.sha256(photo.read_bytes()).hexdigest()
    with TestClient(service) as local:
        local.headers['Authorization'] = 'Bearer SYNTHETIC-local-secret'
        root = local.post('/api/roots', json={'path': str(photo.parent), 'label': 'SYNTHETIC FIXTURE'}).json()
        login(client)
        assert client.get('/api/roots').json()[0]['id'] == root['id']
        job = client.post(f'/api/roots/{root["id"]}/scan', json={}).json()
        service.state.scanner.run_job(job)
        stats = client.post('/api/stats', json={}).json()
        assert stats['summary']['count'] == 1
        assert stats == local.post('/api/stats', json={}).json()
        item = client.post('/api/assets/query', json={}).json()['items'][0]
        assert client.get(item['thumbnail_url']).status_code == 200
        assert hashlib.sha256(photo.read_bytes()).hexdigest() == original
        assert sorted(p.name for p in photo.parent.iterdir()) == ['fixture.jpg']


def test_forbidden_operations_and_cross_site_requests(shared):
    _, _, client, _ = shared
    login(client)
    for method, path in [('POST','/api/roots'), ('DELETE','/api/roots/1'), ('PUT','/api/cache'), ('POST','/api/backup'), ('POST','/api/player/open'), ('POST','/api/remote/x/api/stats'), ('GET','/api/browse'), ('POST','/api/roots/1/scan?force=true')]:
        assert client.request(method, path, json={}).status_code == 403
    assert client.post('/api/stats', json={}, headers={'Origin':'https://evil.test'}).status_code == 403


def test_public_peer_cannot_bypass_ip_check_with_forwarded_header(shared):
    _, gateway, _, _ = shared
    with TestClient(gateway, client=('8.8.8.8', 50000)) as external:
        assert external.get('/api/health', headers={'X-Forwarded-For':'127.0.0.1'}).status_code == 403


def test_password_rotation_invalidates_phone_sessions(shared):
    _, gateway, client, _ = shared
    login(client)
    gateway.state.credentials.set_password('NewSyntheticPassword!')
    assert client.get('/api/info').status_code == 401


def test_login_rate_limit_and_payload_limit(shared):
    _, _, client, _ = shared
    for _ in range(10):
        assert client.post('/api/auth/login', json={'password':'wrong'}).status_code == 401
    assert client.post('/api/auth/login', json={'password':'wrong'}).status_code == 429
    assert client.post('/api/auth/login', content=b'x'*65537).status_code == 413


def test_gateway_does_not_expose_streams_or_unbounded_scan_parameters():
    assert not allowed('GET','/api/assets/1/stream')
    assert not allowed('POST','/api/roots/1/scan','force=true')
    assert not allowed('GET','/api/health','url=http://evil.test')
    assert allowed('POST','/api/jobs/12345678-1234-1234-1234-123456789abc/resume')


def test_addresses_prefer_lan_to_vpn_and_exclude_public_addresses(shared, monkeypatch):
    service, _, _, _ = shared
    monkeypatch.setattr('backend.mobile_share.socket.getaddrinfo',lambda *args:[(None,None,None,None,(ip,0)) for ip in ['100.90.0.1','192.168.9.12','8.8.8.8','127.0.0.1']])
    assert MobileShareController(service).addresses()==['http://192.168.9.12:52033','http://100.90.0.1:52033']
