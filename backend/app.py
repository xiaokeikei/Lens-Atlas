from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
import uuid
import asyncio
import mimetypes
import httpx
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.requests import ClientDisconnect
from pydantic import BaseModel, Field
from . import __version__
from .config import Config
from .db import Database
from .metadata import tool, refresh_cached_metadata
from .query import Filters, clause, statistics, focal_distribution
from .scanner import Scanner
from .credentials import CredentialStore
from .comparison import ComparisonService, register_comparison


class Password(BaseModel):
    password: str = Field(min_length=10, max_length=256)
    setup_code: str = ""
    remember: bool = False


class DesktopPreferences(BaseModel):
    last_connection: str | None = None


class RootInput(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    label: str = Field(default="", max_length=100)


class QueryInput(BaseModel):
    filters: Filters = Field(default_factory=Filters)
    limit: int = Field(default=24, ge=1, le=120)
    offset: int = Field(default=0, ge=0)
    random: bool = True


class ConnectionInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=2048)


class CacheInput(BaseModel):
    limit_bytes: int = Field(ge=16*1024**2, le=1024**4)


class MediaInput(BaseModel):
    url: str = Field(max_length=1024)


class NativePlayerInput(BaseModel):
    url: str = Field(max_length=4096)
    title: str = Field(default='视频',max_length=256)


def create_app(config=None, start_scanner=True):
    config = config or Config()
    db = Database(config.data_dir / "library.sqlite3")
    refresh_cached_metadata(db)
    scanner = Scanner(db, config)
    signing_key = secrets.token_bytes(32)
    remote_sessions = {}
    credentials = CredentialStore(db)
    comparisons = ComparisonService(db, config, scanner, remote_sessions, credentials)
    login_attempts = {}
    setup_path = config.data_dir / "setup-code.txt"
    if not config.desktop and not db.setting("password"):
        if not setup_path.exists():
            setup_path.write_text(secrets.token_urlsafe(18), encoding="utf-8")
            try:
                setup_path.chmod(0o600)
            except OSError:
                pass

    @asynccontextmanager
    async def lifespan(app):
        if start_scanner:
            scanner.start()
            comparisons.start()
        yield
        comparisons.close()
        scanner.close()

    app = FastAPI(title="Lens Atlas", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.db, app.state.scanner, app.state.config = db, scanner, config
    app.state.comparisons = comparisons

    def authorized(request: Request):
        auth = request.headers.get("authorization", "")
        token = auth.removeprefix("Bearer ") if auth.startswith("Bearer ") else ""
        if config.desktop and token and hmac.compare_digest(token, config.local_token):
            return "desktop"
        digest = hashlib.sha256(token.encode()).hexdigest()
        if token and db.one("SELECT token_hash FROM sessions WHERE token_hash=? AND expires>?", (digest,time.time())):
            return digest
        raise HTTPException(401, "请登录当前图库")

    def local_only(identity=Depends(authorized)):
        if not config.desktop:
            raise HTTPException(404, "仅桌面本机服务提供此功能")
        return identity

    def remote_authorized(request: Request, cid: str, path: str):
        if not config.desktop:
            return authorized(request)
        try:
            return authorized(request)
        except HTTPException:
            expires = request.query_params.get('local_expires','0')
            sig = request.query_params.get('local_sig','')
            pairs = [(k,v) for k,v in request.query_params.multi_items() if k not in {'local_expires','local_sig'}]
            upstream = path+'?'+str(httpx.QueryParams(pairs))
            expected = hmac.new(signing_key,f'{cid}:{upstream}:{expires}'.encode(),hashlib.sha256).hexdigest()
            if request.method not in {'GET','HEAD'} or not re.fullmatch(r'api/assets/\d+/stream',path) or not expires.isdigit() or int(expires)<time.time() or not hmac.compare_digest(expected,sig):
                raise HTTPException(401,'预览会话已过期')

    def asset(aid):
        row = db.one("SELECT a.*,r.path root_path,r.label root_label,r.status root_status FROM assets a JOIN roots r ON a.root_id=r.id WHERE a.id=? AND a.deleted=0", (aid,))
        if not row:
            raise HTTPException(404, "素材不在索引中")
        return row

    def sign(aid, purpose):
        expires = int(time.time()) + 3600
        sig = hmac.new(signing_key, f"{aid}:{purpose}:{expires}".encode(), hashlib.sha256).hexdigest()
        return f"/api/assets/{aid}/{purpose}?expires={expires}&sig={sig}"

    def verify(aid, purpose, expires, sig):
        expected = hmac.new(signing_key, f"{aid}:{purpose}:{expires}".encode(), hashlib.sha256).hexdigest()
        if expires < time.time() or not hmac.compare_digest(sig, expected):
            raise HTTPException(401, "预览链接已过期，请刷新")

    def public_asset(row, details=False):
        result = {k:v for k,v in row.items() if k not in {"root_path", "metadata_json"}}
        result["thumbnail_url"] = sign(row["id"], "thumbnail")
        result["stream_url"] = sign(row["id"], "stream") if row["kind"] == "video" else None
        if details:
            result["metadata"] = json.loads(row.get("metadata_json") or "{}")
            try:
                path = scanner.source_path(row)
                path.stat()
                result["availability"] = "available"
            except PermissionError:
                result["availability"] = "permission_denied"
            except OSError:
                result["availability"] = "library_offline" if not Path(row["root_path"]).is_dir() else "source_missing"
        return result

    @app.middleware("http")
    async def security(request, call_next):
        if request.method in {"POST", "DELETE", "PUT", "PATCH"}:
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail":"拒绝跨站请求"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api") else "no-cache"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'"
        return response

    @app.get("/api/health")
    def health():
        return {"ok":True,"version":__version__,"api_version":1,"desktop":config.desktop,"setup_required":not config.desktop and not bool(db.setting("password"))}

    @app.post("/api/auth/setup")
    def setup(data: Password):
        if config.desktop or db.setting("password"):
            raise HTTPException(409, "管理员已设置")
        code = setup_path.read_text(encoding="utf-8").strip()
        if not hmac.compare_digest(data.setup_code, code):
            raise HTTPException(403, "初始化码不正确，请读取应用数据目录中的 setup-code.txt")
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256",data.password.encode(),salt.encode(),310000).hex()
        with db.connect() as connection:
            try:
                connection.execute("INSERT INTO settings VALUES('password',?)", (json.dumps({"salt":salt,"hash":digest}),))
            except sqlite3.IntegrityError:
                raise HTTPException(409,"管理员已设置")
        setup_path.unlink(missing_ok=True)
        return {"ok": True}

    @app.post("/api/auth/login")
    def login(data: Password, request: Request):
        key = request.client.host if request.client else "unknown"
        stamp, attempts = login_attempts.get(key, (time.monotonic(),0))
        if time.monotonic()-stamp > 60:
            stamp, attempts = time.monotonic(),0
        if attempts >= 10:
            raise HTTPException(429,"尝试过多，请一分钟后重试")
        login_attempts[key] = (stamp, attempts+1)
        password = db.setting("password")
        digest = hashlib.pbkdf2_hmac("sha256",data.password.encode(),(password or {}).get("salt", "invalid").encode(),310000).hex()
        if not password or not hmac.compare_digest(digest,password["hash"]):
            raise HTTPException(401,"密码错误或管理员尚未初始化")
        login_attempts.pop(key,None)
        token = secrets.token_urlsafe(40)
        db.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
        lifetime = 30*86400 if data.remember else 12*3600
        db.execute("INSERT INTO sessions VALUES(?,?)",(hashlib.sha256(token.encode()).hexdigest(),time.time()+lifetime))
        return {"token":token,"expires_in":lifetime}

    @app.post("/api/auth/logout")
    def logout(identity=Depends(authorized)):
        db.execute("DELETE FROM sessions WHERE token_hash=?",(identity,))
        remote_sessions.clear()
        return {"ok": True}

    @app.get("/api/info", dependencies=[Depends(authorized)])
    def info():
        return {"version":__version__,"api_version":1,"library_id":db.setting("library_id"),"desktop":config.desktop,
                "native_player_available":bool(config.native_player),
                "tools":{name:bool(tool(name)) for name in ["exiftool","ffmpeg","ffprobe"]},
                "allowed_roots":[str(p) for p in config.allowed_roots],"cache":scanner.cache_info(),
                "scan_workers":config.workers,"single_file_timeout":config.timeout}

    @app.post('/api/player/open',dependencies=[Depends(local_only)])
    def open_native_player(data: NativePlayerInput):
        if not config.native_player or not config.local_origin:
            raise HTTPException(409,'当前客户端未启用原生播放器')
        parsed=urlparse(data.url)
        if parsed.scheme or parsed.netloc or parsed.fragment or not re.fullmatch(r'/api/(?:assets/\d+/stream|remote/[a-f0-9-]+/api/assets/\d+/stream)',parsed.path):
            raise HTTPException(400,'仅允许当前本机服务签发的媒体地址')
        # The stream endpoints verify their own media signatures. Never launch arbitrary URLs/files.
        request_id=str(uuid.uuid4())
        config.native_player(config.local_origin+data.url,data.title,request_id)
        return {'ok':True,'request_id':request_id}

    @app.get('/api/player/status',dependencies=[Depends(local_only)])
    def native_player_status():
        return config.native_player_status() if config.native_player_status else {'status':'unavailable'}

    @app.get("/api/roots", dependencies=[Depends(authorized)])
    def roots():
        return db.rows("SELECT r.*,(SELECT COUNT(*) FROM assets a WHERE a.root_id=r.id AND a.deleted=0) file_count FROM roots r ORDER BY id")

    @app.post("/api/roots", dependencies=[Depends(authorized)])
    def add_root(data: RootInput):
        path = Path(data.path).expanduser().resolve()
        if not config.desktop and not any(path.is_relative_to(p) for p in config.allowed_roots):
            raise HTTPException(403,"只能添加服务端授权映射目录；检查 LENS_MEDIA_ROOTS")
        if path.is_relative_to(config.data_dir) or config.data_dir.is_relative_to(path):
            raise HTTPException(400,"素材目录不能包含应用数据目录，也不能位于其中")
        for root in db.rows("SELECT path FROM roots"):
            old = Path(root["path"])
            if path.is_relative_to(old) or old.is_relative_to(path):
                raise HTTPException(409,"目录已添加或与现有目录重叠，避免重复计数")
        if not path.is_dir():
            raise HTTPException(400,"服务端无法访问此目录，请检查路径及权限")
        rid = db.execute("INSERT INTO roots(path,label) VALUES(?,?)", (str(path), data.label.strip() or path.name or str(path)))
        return db.one("SELECT * FROM roots WHERE id=?", (rid,))

    @app.delete("/api/roots/{rid}", dependencies=[Depends(authorized)])
    def delete_root(rid: int):
        if scanner.current_root == rid or db.one("SELECT id FROM jobs WHERE root_id=? AND status IN ('running','queued','paused')",(rid,)):
            raise HTTPException(409,"请先取消该目录的扫描任务，并等待正在处理的文件结束")
        with db.connect() as c:
            c.execute("DELETE FROM jobs WHERE root_id=?",(rid,))
            c.execute("DELETE FROM assets WHERE root_id=?",(rid,))
            c.execute("DELETE FROM roots WHERE id=?",(rid,))
        return {"ok":True,"message":"仅移除索引，原片未修改"}

    @app.get("/api/browse", dependencies=[Depends(authorized)])
    def browse(path: str = ""):
        if not path:
            choices = config.allowed_roots if not config.desktop else [Path(f"{chr(d)}:/") for d in range(65,91) if Path(f"{chr(d)}:/").is_dir()]
            return {"path":"","parent":None,"directories":[{"name":str(p),"path":str(p)} for p in choices]}
        target = Path(path).resolve()
        if not config.desktop and not any(target.is_relative_to(p) for p in config.allowed_roots):
            raise HTTPException(403,"超出服务端授权目录")
        try:
            directories = []
            with os.scandir(target) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False) and not Path(entry.path).is_junction():
                        directories.append({"name":entry.name,"path":entry.path})
                    if len(directories) >= 1000:
                        break
            parent = target.parent if target.parent != target else None
            if parent and not config.desktop and not any(parent.is_relative_to(p) for p in config.allowed_roots):
                parent = None
            return {"path":str(target),"parent":str(parent) if parent else None,"directories":sorted(directories,key=lambda d:d["name"].lower())}
        except OSError as e:
            raise HTTPException(400,str(e))

    @app.post("/api/roots/{rid}/scan", dependencies=[Depends(authorized)])
    def scan(rid: int, force: bool = False):
        if not db.one("SELECT id FROM roots WHERE id=?", (rid,)):
            raise HTTPException(404,"目录不存在")
        return scanner.enqueue(rid,force)

    @app.get("/api/jobs", dependencies=[Depends(authorized)])
    def jobs():
        return db.rows("SELECT j.*,r.label root_label FROM jobs j JOIN roots r ON r.id=j.root_id ORDER BY started DESC LIMIT 50")

    @app.post("/api/jobs/{jid}/{action}", dependencies=[Depends(authorized)])
    def control(jid: str, action: Literal["pause","resume","cancel"]):
        try:
            scanner.control(jid,action)
            return {"ok":True}
        except (ValueError,sqlite3.IntegrityError) as e:
            raise HTTPException(409,str(e))

    @app.post("/api/stats", dependencies=[Depends(authorized)])
    def stats(filters: Filters):
        return statistics(db,filters)

    @app.post('/api/stats/focals', dependencies=[Depends(authorized)])
    def focal_stats(filters: Filters):
        return focal_distribution(db, filters)

    @app.post("/api/assets/query", dependencies=[Depends(authorized)])
    def query(data: QueryInput):
        where, args, _ = clause(data.filters)
        order = "random()" if data.random else "id DESC"
        # SQLite reservoir/top-N selection operates over the complete matching index, not a UI page.
        with db.connect() as connection:
            connection.execute('BEGIN')
            total = connection.execute(f"SELECT COUNT(*) n FROM assets WHERE {where}",args).fetchone()['n']
            selected = [dict(row) for row in connection.execute(f"SELECT * FROM assets WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?", (*args,data.limit,0 if data.random else data.offset))]
        return {"total":total,"items":[public_asset(r) for r in selected]}

    @app.get("/api/assets/{aid}", dependencies=[Depends(authorized)])
    def detail(aid: int):
        return public_asset(asset(aid),True)

    @app.get("/api/assets/{aid}/thumbnail")
    def thumbnail(aid: int, expires: int, sig: str):
        verify(aid,"thumbnail",expires,sig)
        item = asset(aid)
        try:
            target = scanner.make_preview(item)
            return Response(target.read_bytes(),media_type="image/jpeg")
        except Exception as e:
            status = "permission_denied" if isinstance(e,PermissionError) else "failed"
            db.execute("UPDATE assets SET preview_status=?,preview_error=? WHERE id=?",(status,str(e),aid))
            raise HTTPException(422,str(e))

    @app.api_route("/api/assets/{aid}/stream",methods=['GET','HEAD'])
    async def stream(aid: int, expires: int, sig: str, request: Request):
        verify(aid,"stream",expires,sig)
        item = asset(aid)
        if item["kind"] != "video":
            raise HTTPException(400,"不是视频")
        path = scanner.source_path(item)
        if not path.is_file():
            raise HTTPException(404,"原片离线或已移除")
        size=path.stat().st_size
        start,end=0,size-1
        range_header=request.headers.get('range')
        headers={'Accept-Ranges':'bytes'}
        if range_header:
            match=re.fullmatch(r'bytes=(\d*)-(\d*)',range_header)
            if not match or not any(match.groups()) or size==0:
                return Response(status_code=416,headers={'Content-Range':f'bytes */{size}'})
            left,right=match.groups()
            if left:
                start=int(left)
                end=min(int(right),size-1) if right else size-1
            else:
                suffix=int(right)
                start=max(0,size-suffix)
            if start>=size or end<start:
                return Response(status_code=416,headers={'Content-Range':f'bytes */{size}'})
            headers['Content-Range']=f'bytes {start}-{end}/{size}'
        length=max(0,end-start+1)
        headers['Content-Length']=str(length)
        content_type=mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        status=206 if range_header else 200
        if request.method=='HEAD':
            return Response(status_code=status,headers=headers,media_type=content_type)
        async def chunks():
            # Stop reading a multi-GB original immediately when a player disconnects/seeks.
            with path.open('rb') as source:
                source.seek(start)
                remaining=length
                while remaining>0:
                    if await request.is_disconnected():break
                    chunk=await asyncio.to_thread(source.read,min(256*1024,remaining))
                    if not chunk:break
                    remaining-=len(chunk)
                    yield chunk
        return StreamingResponse(chunks(),status_code=status,headers=headers,media_type=content_type)

    @app.get("/api/cache", dependencies=[Depends(authorized)])
    def cache():
        return scanner.cache_info()

    @app.put("/api/cache", dependencies=[Depends(authorized)])
    def configure_cache(data: CacheInput):
        db.set_setting("cache_bytes",data.limit_bytes)
        scanner.trim_cache()
        return scanner.cache_info()

    @app.delete("/api/cache", dependencies=[Depends(authorized)])
    def clear_cache():
        scanner.clear_cache()
        return scanner.cache_info()

    @app.post("/api/backup", dependencies=[Depends(authorized)])
    def backup():
        path = config.data_dir / "backup.sqlite3"
        db.backup(path)
        return {"ok":True,"filename":path.name,"message":"已写入服务端应用数据目录（包含管理员配置，需保密）"}

    @app.get("/api/connections", dependencies=[Depends(local_only)])
    def connections():
        return [{**row, 'remembered': bool(db.setting('credential:' + row['id']))} for row in db.rows("SELECT * FROM connections ORDER BY name")]

    @app.get('/api/desktop/preferences', dependencies=[Depends(local_only)])
    def desktop_preferences():
        return {'last_connection': db.setting('last_connection')}

    @app.put('/api/desktop/preferences', dependencies=[Depends(local_only)])
    def set_desktop_preferences(data: DesktopPreferences):
        if data.last_connection and not db.one('SELECT id FROM connections WHERE id=?', (data.last_connection,)):
            raise HTTPException(404, '连接不存在')
        db.set_setting('last_connection', data.last_connection)
        return {'ok': True}

    @app.post("/api/connections", dependencies=[Depends(local_only)])
    def connection(data: ConnectionInput):
        url = data.url.rstrip("/")
        parsed = urlparse(url)
        if parsed.scheme not in {"http","https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"","/"}:
            raise HTTPException(400,"请输入 http(s)://主机:端口，不要附带路径或凭据")
        cid = str(uuid.uuid4())
        db.execute("INSERT INTO connections VALUES(?,?,?)", (cid,data.name,url))
        return {"id":cid,"name":data.name,"url":url}

    @app.delete("/api/connections/{cid}", dependencies=[Depends(local_only)])
    def remove_connection(cid: str):
        db.execute("DELETE FROM connections WHERE id=?",(cid,))
        remote_sessions.pop(cid,None)
        credentials.forget(cid)
        if db.setting('last_connection') == cid:
            db.set_setting('last_connection', None)
        return {"ok":True}

    # Browser users may add peers for read-only comparison as well. On NAS these
    # credentials remain in memory; persistent Windows login is desktop-only.
    @app.get('/api/peers', dependencies=[Depends(authorized)])
    def peers():
        return connections()

    @app.post('/api/peers', dependencies=[Depends(authorized)])
    def add_peer(data: ConnectionInput):
        return connection(data)

    @app.delete('/api/peers/{cid}', dependencies=[Depends(authorized)])
    def remove_peer(cid: str):
        return remove_connection(cid)

    @app.post('/api/connections/{cid}/media',dependencies=[Depends(local_only)])
    def remote_media(cid: str, data: MediaInput):
        if not db.one('SELECT id FROM connections WHERE id=?',(cid,)):
            raise HTTPException(404)
        parsed=urlparse(data.url)
        if parsed.scheme or parsed.netloc or not re.fullmatch(r'/api/assets/\d+/stream',parsed.path):
            raise HTTPException(400,'无效媒体地址')
        upstream=parsed.path.lstrip('/')+'?'+str(httpx.QueryParams(parsed.query))
        expires=int(time.time())+3600
        sig=hmac.new(signing_key,f'{cid}:{upstream}:{expires}'.encode(),hashlib.sha256).hexdigest()
        return {'url':f'/api/remote/{cid}/{upstream}&local_expires={expires}&local_sig={sig}'}

    @app.api_route("/api/remote/{cid}/{path:path}", methods=["GET","HEAD","POST","PUT","DELETE"], dependencies=[Depends(remote_authorized)])
    async def remote(cid: str, path: str, request: Request):
        if not path.startswith("api/") or ".." in path or path.startswith(("api/remote", "api/connections")):
            raise HTTPException(400,"无效远端接口")
        connection = db.one("SELECT * FROM connections WHERE id=?",(cid,))
        if not connection:
            raise HTTPException(404,"连接不存在")
        headers = {"content-type":request.headers.get("content-type","application/json")}
        if cid not in remote_sessions:
            stored = credentials.load(cid)
            if stored:
                remote_sessions[cid] = stored
        if cid in remote_sessions:
            headers["authorization"] = "Bearer " + remote_sessions[cid]
        if path == 'api/auth/logout':
            # Logout forgets local credentials even if the NAS is temporarily unreachable.
            remote_sessions.pop(cid, None)
            credentials.forget(cid)
            if db.setting('last_connection') == cid:
                db.set_setting('last_connection', None)
        if request.headers.get("range"):
            headers["range"] = request.headers["range"]
        client = httpx.AsyncClient(timeout=httpx.Timeout(60,connect=8),follow_redirects=False,trust_env=False)
        try:
            params=[(k,v) for k,v in request.query_params.multi_items() if k not in {'local_expires','local_sig'}]
            body=b'' if request.method in {'GET','HEAD'} else await request.body()
            req = client.build_request(request.method,connection["url"]+"/"+path,params=params,headers=headers,content=body)
            response = await client.send(req,stream=True)
        except ClientDisconnect:
            await client.aclose()
            return Response(status_code=499)
        except httpx.HTTPError:
            await client.aclose()
            raise HTTPException(502,"NAS 无法连接，请检查地址、网络及证书")
        if path == "api/auth/login" and response.status_code == 200:
            data = json.loads(await response.aread())
            remote_sessions[cid] = data["token"]
            await response.aclose()
            await client.aclose()
            remember = config.desktop and json.loads(body).get('remember', False)
            if remember:
                try:
                    credentials.save(cid, data['token'])
                    db.set_setting('last_connection', cid)
                except (OSError, RuntimeError):
                    credentials.forget(cid)
                    return {'ok': True, 'remembered': False, 'warning': '已登录，但安全凭据存储不可用；本次不会保存登录'}
            else:
                credentials.forget(cid)
            return {"ok":True}
        if path == "api/auth/logout":
            remote_sessions.pop(cid,None)
        elif response.status_code == 401 and path != 'api/auth/login':
            remote_sessions.pop(cid, None)
            credentials.forget(cid)
        async def content():
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()
                await client.aclose()
        allowed = {k:v for k,v in response.headers.items() if k in {"content-type","content-length","content-range","accept-ranges"}}
        return StreamingResponse(content(),status_code=response.status_code,headers=allowed)

    register_comparison(app, comparisons, authorized, authorized)

    if config.static_dir.is_dir():
        app.mount("/",StaticFiles(directory=config.static_dir,html=True),name="web")
    return app


app = None  # Use uvicorn backend.app:create_app --factory to avoid import-time private state.
