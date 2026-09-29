import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.config import Config


def test_notice_requires_authorized_explicit_confirmation(env):
    app, client, _ = env
    assert client.get('/api/info').json()['usage_notice_accepted'] is False
    with TestClient(app) as unauthorized:
        assert unauthorized.post('/api/usage-notice/accept').status_code == 401
    assert client.get('/api/info').json()['usage_notice_accepted'] is False
    for _ in range(2):
        assert client.post('/api/usage-notice/accept').json() == {'usage_notice_accepted': True}
    client.delete('/api/cache')
    client.post('/api/auth/logout')
    assert client.get('/api/info').json()['usage_notice_accepted'] is True


@pytest.mark.parametrize('desktop', [True, False])
def test_notice_survives_restart_and_is_scoped_to_data_directory(tmp_path, desktop):
    def make(data):
        return create_app(Config(data_dir=data, desktop=desktop, local_token='test-local-token' if desktop else ''), start_scanner=False)

    data = tmp_path/'original'
    app = make(data)
    with TestClient(app) as client:
        if desktop:
            token = 'test-local-token'
        else:
            code = (data/'setup-code.txt').read_text().strip()
            assert client.post('/api/auth/setup', json={'password':'test-nas-password','setup_code':code}).status_code == 200
            token = client.post('/api/auth/login', json={'password':'test-nas-password'}).json()['token']
        client.headers['Authorization'] = 'Bearer '+token
        assert client.get('/api/info').json()['usage_notice_accepted'] is False
        before = app.state.db.rows('SELECT * FROM settings ORDER BY key')
        assert client.post('/api/usage-notice/accept').status_code == 200
        assert app.state.db.rows("SELECT * FROM settings WHERE key != 'usage_notice_accepted' ORDER BY key") == before
    with TestClient(make(data)) as restarted:
        restarted.headers['Authorization'] = 'Bearer '+token
        assert restarted.get('/api/info').json()['usage_notice_accepted'] is True
    new_app = make(tmp_path/'new-installation')
    assert new_app.state.db.setting('usage_notice_accepted', False) is False


def test_notice_does_not_record_failed_save(env, monkeypatch):
    app, client, _ = env
    def fail(*args):
        raise OSError('Synthetic persistence failure')
    monkeypatch.setattr(app.state.db, 'set_setting', fail)
    with TestClient(app, raise_server_exceptions=False) as failing:
        failing.headers.update(client.headers)
        assert failing.post('/api/usage-notice/accept').status_code == 500
    assert client.get('/api/info').json()['usage_notice_accepted'] is False
