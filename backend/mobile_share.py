"""Opt-in authenticated phone access to the live desktop library.

Forwards a narrow set of read/index-scan APIs into the existing application.
Never opens a second database owner or grants remote directory/file management.
"""
from contextlib import asynccontextmanager
import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import socket
import threading
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
import httpx
import uvicorn

from backend import __version__

PREFIX = 'mobile-share:session:'
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(n) for n in ('127.0.0.0/8', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '100.64.0.0/10', '::1/128'))


def allowed(method, path, query=''):
    if query:
        return method == 'GET' and bool(re.fullmatch(r'/api/assets/[0-9]+/thumbnail', path)) and bool(re.fullmatch(r'expires=[0-9]+&sig=[0-9a-f]{64}', query))
    if method == 'GET':
        return path in {'/api/health', '/api/info', '/api/roots', '/api/jobs'} or bool(re.fullmatch(r'/api/assets/[0-9]+(?:/thumbnail)?', path))
    if method == 'POST':
        return path in {'/api/auth/login', '/api/auth/logout', '/api/stats', '/api/stats/focals', '/api/assets/query'} or bool(re.fullmatch(r'/api/roots/[1-9][0-9]*/scan', path)) or bool(re.fullmatch(r'/api/jobs/[0-9a-fA-F-]{36}/(?:pause|resume|cancel)', path))
    return False


class MobileCredentials:
    def __init__(self, db):
        self.db = db
        self.attempts = {}
        self.lock = threading.Lock()

    def configured(self):
        return bool(self.db.setting('mobile-share:password'))

    def set_password(self, password):
        if not 10 <= len(password) <= 256:
            raise ValueError('手机连接密码需要 10 至 256 个字符')
        salt = secrets.token_hex(16)
        value = {'salt': salt, 'hash': hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 310000).hex()}
        self.db.set_setting('mobile-share:password', value)
        self.db.execute('DELETE FROM settings WHERE key LIKE ?', (PREFIX + '%',))

    def login(self, password, remember, peer):
        with self.lock:
            stamp, count = self.attempts.get(peer, (time.monotonic(), 0))
            if time.monotonic() - stamp > 60:
                stamp, count = time.monotonic(), 0
            if count >= 10:
                raise HTTPException(429, '尝试过多，请一分钟后重试')
            self.attempts[peer] = stamp, count + 1
        saved = self.db.setting('mobile-share:password') or {}
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), saved.get('salt', 'invalid').encode(), 310000).hex()
        if not saved or not hmac.compare_digest(digest, saved['hash']):
            raise HTTPException(401, '手机连接密码错误或电脑端尚未设置')
        with self.lock:
            self.attempts.pop(peer, None)
        for row in self.db.rows('SELECT key,value FROM settings WHERE key LIKE ?', (PREFIX + '%',)):
            if json.loads(row['value'])['expires'] < time.time():
                self.db.execute('DELETE FROM settings WHERE key=?', (row['key'],))
        token = secrets.token_urlsafe(40)
        lifetime = 30 * 86400 if remember else 12 * 3600
        key = PREFIX + hashlib.sha256(token.encode()).hexdigest()
        self.db.set_setting(key, {'expires': time.time() + lifetime})
        return {'token': token, 'expires_in': lifetime}

    def identity(self, request):
        header = request.headers.get('authorization', '')
        token = header[7:] if header.startswith('Bearer ') else ''
        if not token or len(token) > 256:
            raise HTTPException(401, '请登录电脑图库')
        key = PREFIX + hashlib.sha256(token.encode()).hexdigest()
        saved = self.db.setting(key)
        if not saved or saved['expires'] <= time.time():
            raise HTTPException(401, '登录已过期，请重新登录')
        return key


def create_gateway(service):
    if not service.state.config.desktop:
        raise ValueError('手机访问入口只用于桌面本机图库')
    credentials = MobileCredentials(service.state.db)

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=service, client=('127.0.0.1', 12345)), base_url=service.state.config.local_origin or 'http://127.0.0.1', headers={'Authorization': 'Bearer ' + service.state.config.local_token}, follow_redirects=False) as client:
            app.state.client = client
            yield

    app = FastAPI(title='Lens Atlas mobile access', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.credentials = credentials

    @app.middleware('http')
    async def protect(request, call_next):
        try:
            peer = ipaddress.ip_address(request.client.host)
        except (ValueError, AttributeError):
            return JSONResponse({'detail': '无法确认客户端地址'}, status_code=403)
        if not any(peer in network for network in PRIVATE_NETWORKS):
            return JSONResponse({'detail': '手机访问仅允许局域网或 VPN 地址'}, status_code=403)
        if request.headers.get('origin'):
            return JSONResponse({'detail': '手机访问不接受网页跨站请求'}, status_code=403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.api_route('/{path:path}', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'])
    async def api(path: str, request: Request):
        target = '/' + path
        if not allowed(request.method, target, request.url.query):
            raise HTTPException(403, '手机访问禁止目录管理、素材修改或此接口')
        if target == '/api/health':
            return {'ok': True, 'version': __version__, 'api_version': 1, 'desktop': False, 'setup_required': False, 'library_kind': 'computer'}
        if target != '/api/auth/login':
            identity = credentials.identity(request)
        body = bytearray()
        if request.method == 'POST':
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 65536:
                    raise HTTPException(413, '请求过大')
        if target == '/api/auth/login':
            try:
                data = json.loads(body)
                password = data['password']
                if not isinstance(password, str) or not 1 <= len(password) <= 256 or not isinstance(data.get('remember', False), bool):
                    raise ValueError()
            except (ValueError, KeyError, TypeError):
                raise HTTPException(422, '登录信息格式无效')
            return credentials.login(password, data.get('remember', False), request.client.host)
        if target == '/api/auth/logout':
            service.state.db.execute('DELETE FROM settings WHERE key=?', (identity,))
            return {'ok': True}
        response = await app.state.client.request(request.method, target + ('?' + request.url.query if request.url.query else ''), content=bytes(body) if body else None, headers={'Content-Type': 'application/json'} if body else {})
        if target == '/api/info' and response.status_code == 200:
            info = response.json()
            info.update(desktop=False, library_kind='computer', native_player_available=False)
            return info
        return Response(response.content, status_code=response.status_code, media_type=response.headers.get('content-type', 'application/json'))

    return app


class MobileShareController:
    """Owns only an opt-in socket; uses the already-running desktop service and database."""
    def __init__(self, service):
        self.app = create_gateway(service)
        self.server = None
        self.thread = None
        self.port = None

    def start(self, port=52033, host='0.0.0.0'):
        if self.server and self.server.started:
            return
        if not self.app.state.credentials.configured():
            raise ValueError('请先设置手机连接密码')
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind((host, port))
        except BaseException:
            sock.close()
            raise
        self.port = sock.getsockname()[1]
        self.server = uvicorn.Server(uvicorn.Config(self.app, host=host, port=self.port, access_log=False, log_config=None, proxy_headers=False, timeout_graceful_shutdown=3))
        self.thread = threading.Thread(target=lambda: self.server.run(sockets=[sock]), daemon=True, name='mobile-access')
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started and self.thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.05)
        if not self.server.started:
            self.stop()
            raise RuntimeError('手机访问服务未能启动')

    def stop(self):
        if self.server:
            self.server.should_exit = True
        if self.thread:
            self.thread.join(timeout=5)
        self.server = self.thread = None

    def addresses(self):
        try:
            ips = {a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM)}
        except OSError:
            return []
        ordered = sorted(ips, key=lambda ip: (ipaddress.ip_address(ip) in ipaddress.ip_network('100.64.0.0/10'), ip))
        return [f'http://{ip}:{self.port or 52033}' for ip in ordered if ip != '127.0.0.1' and any(ipaddress.ip_address(ip) in n for n in PRIVATE_NETWORKS)]
