"""Read-only inventory snapshots and resumable content verification.

All generated data lives in the application database. Originals are only opened rb.
"""
from pathlib import Path, PurePosixPath
import csv
import hashlib
import io
import json
import threading
import time
import uuid
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from .scanner import now

SCHEMA = '''
CREATE TABLE IF NOT EXISTS inventories(
 id TEXT PRIMARY KEY,root_id INTEGER NOT NULL,subpath TEXT NOT NULL,scan_id TEXT NOT NULL,
 created TEXT NOT NULL,last_scan TEXT,label TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'ready',
 total INTEGER NOT NULL DEFAULT 0,processed INTEGER NOT NULL DEFAULT 0,errors INTEGER NOT NULL DEFAULT 0,message TEXT);
CREATE TABLE IF NOT EXISTS inventory_entries(
 inventory_id TEXT NOT NULL,asset_id INTEGER NOT NULL,relpath TEXT NOT NULL,size INTEGER NOT NULL,
 mtime_ns INTEGER NOT NULL,sha256 TEXT,error TEXT,checked INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(inventory_id,relpath));
CREATE INDEX IF NOT EXISTS inventory_pending ON inventory_entries(inventory_id,checked);
CREATE TABLE IF NOT EXISTS comparisons(
 id TEXT PRIMARY KEY,created TEXT NOT NULL,status TEXT NOT NULL,spec TEXT NOT NULL,
 left_inventory TEXT,right_inventory TEXT,message TEXT,processed INTEGER NOT NULL DEFAULT 0,
 snapshots TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS comparison_entries(
 comparison_id TEXT NOT NULL,side TEXT NOT NULL,relpath TEXT NOT NULL,size INTEGER NOT NULL,
 sha256 TEXT,error TEXT,PRIMARY KEY(comparison_id,side,relpath));
CREATE INDEX IF NOT EXISTS comparison_hash ON comparison_entries(comparison_id,side,sha256);
'''


class InventoryInput(BaseModel):
    root_id: int
    subpath: str = Field(default='', max_length=4096)


class ComparisonSide(InventoryInput):
    connection_id: str | None = None


class ComparisonInput(BaseModel):
    left: ComparisonSide
    right: ComparisonSide
    verify: bool = False


class Stopped(Exception):
    pass


class ComparisonService:
    def __init__(self, db, config, scanner, sessions, credentials):
        self.db, self.config, self.scanner = db, config, scanner
        self.sessions, self.credentials = sessions, credentials
        self.stop = threading.Event()
        self.threads = []
        with db.connect() as c:
            c.executescript(SCHEMA)
            c.execute("UPDATE inventories SET status='paused',message='服务重启，可恢复内容校验' WHERE status IN ('running','queued')")
            c.execute("UPDATE comparisons SET status='paused',message='服务重启，可恢复比对' WHERE status IN ('running','queued')")

    def start(self):
        if self.threads:
            return
        for table, callback in [('inventories', self.hash_inventory), ('comparisons', self.run_comparison)]:
            thread = threading.Thread(target=self.loop, args=(table, callback), daemon=True, name=table)
            thread.start()
            self.threads.append(thread)

    def close(self):
        self.stop.set()
        for table in ['inventories', 'comparisons']:
            self.db.execute(f"UPDATE {table} SET status='paused',message='服务停止，可恢复' WHERE status IN ('running','queued')")
        for thread in self.threads:
            thread.join(timeout=5)

    def loop(self, table, callback):
        while not self.stop.wait(.3):
            row = self.db.one(f"SELECT * FROM {table} WHERE status='queued' ORDER BY created LIMIT 1")
            if row:
                self.db.execute(f"UPDATE {table} SET status='running',message=NULL WHERE id=? AND status='queued'", (row['id'],))
                try:
                    callback(row['id'])
                except Stopped:
                    pass
                except Exception as exc:
                    self.db.execute(f"UPDATE {table} SET status='failed',message=? WHERE id=? AND status='running'", (str(exc), row['id']))

    def check(self, table, rid):
        row = self.db.one(f'SELECT status FROM {table} WHERE id=?', (rid,))
        if self.stop.is_set() or not row or row['status'] != 'running':
            raise Stopped()

    def inventory(self, data):
        root = self.db.one('SELECT * FROM roots WHERE id=?', (data.root_id,))
        if not root:
            raise HTTPException(404, '目录不存在')
        if data.subpath.startswith(('/', '\\')):
            raise HTTPException(400, '请输入相对子目录，不要使用绝对路径')
        sub = data.subpath.replace('\\', '/').strip('/')
        if PurePosixPath(sub).is_absolute() or '..' in PurePosixPath(sub).parts or ':' in sub:
            raise HTTPException(400, '子目录必须是根目录内的相对路径')
        # The scanner's source resolver enforces authorized roots and containment.
        target = self.scanner.source_path({'root_path': root['path'], 'relpath': sub or '.'})
        if not target.is_dir():
            raise HTTPException(409, '素材目录离线或子目录不存在；不能判定文件缺失')
        iid = str(uuid.uuid4())
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            root = dict(c.execute('SELECT * FROM roots WHERE id=?', (data.root_id,)).fetchone())
            latest = c.execute('SELECT * FROM jobs WHERE root_id=? ORDER BY started DESC LIMIT 1', (data.root_id,)).fetchone()
            active = c.execute("SELECT id FROM jobs WHERE root_id=? AND status IN ('running','queued','paused')", (data.root_id,)).fetchone()
            if root['status'] != 'online' or not latest or latest['status'] != 'completed' or not latest['enumeration_complete'] or active:
                raise HTTPException(409, '请先完成两边目录的扫描；离线、暂停或不完整索引不能用于差异判定')
            c.execute('INSERT INTO inventories(id,root_id,subpath,scan_id,created,last_scan,label) VALUES(?,?,?,?,?,?,?)',
                      (iid, data.root_id, sub, latest['id'], now(), root['last_scan'], root['label']))
            prefix = sub + '/' if sub else ''
            # Only entries seen by the successful snapshot are compared; preserved historical
            # missing entries must never masquerade as current files.
            c.execute('INSERT INTO inventory_entries(inventory_id,asset_id,relpath,size,mtime_ns) '
                      'SELECT ?,id,substr(relpath,?),size,mtime_ns FROM assets WHERE root_id=? AND deleted=0 '
                      'AND seen=? AND substr(relpath,1,?)=?',
                      (iid, len(prefix) + 1, data.root_id, latest['id'], len(prefix), prefix))
            c.execute('UPDATE inventories SET total=(SELECT COUNT(*) FROM inventory_entries WHERE inventory_id=?) WHERE id=?', (iid, iid))
        return self.db.one('SELECT * FROM inventories WHERE id=?', (iid,))

    def validate_inventory(self, iid):
        row = self.db.one('SELECT * FROM inventories WHERE id=?', (iid,))
        if not row:
            raise HTTPException(404, '清单不存在')
        root = self.db.one('SELECT * FROM roots WHERE id=?', (row['root_id'],))
        if not root:
            raise HTTPException(409, '目录索引已移除，请重新比对')
        target = self.scanner.source_path({'root_path': root['path'], 'relpath': row['subpath'] or '.'})
        latest = self.db.one('SELECT id FROM jobs WHERE root_id=? ORDER BY started DESC LIMIT 1', (row['root_id'],))
        if not target.is_dir() or root['status'] != 'online' or not latest or latest['id'] != row['scan_id']:
            raise HTTPException(409, '图库离线或扫描快照已变化，请重新比对')
        return row, root

    def hash_inventory(self, iid):
        snapshot, root = self.validate_inventory(iid)
        while True:
            self.check('inventories', iid)
            entry = self.db.one('SELECT * FROM inventory_entries WHERE inventory_id=? AND checked=0 ORDER BY relpath LIMIT 1', (iid,))
            if not entry:
                break
            digest, error = None, None
            try:
                path = self.scanner.source_path({'root_path': root['path'], 'relpath': '/'.join(p for p in [snapshot['subpath'], entry['relpath']] if p)})
                before = path.stat()
                if (before.st_size, before.st_mtime_ns) != (entry['size'], entry['mtime_ns']):
                    raise ValueError('文件已变化，请重新扫描并比对')
                value = hashlib.sha256()
                deadline = time.monotonic() + 3600
                with path.open('rb') as stream:
                    while block := stream.read(1024 * 1024):
                        self.check('inventories', iid)
                        if time.monotonic() > deadline:
                            raise TimeoutError('单文件校验超过一小时')
                        value.update(block)
                after = path.stat()
                if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                    raise ValueError('校验期间文件发生变化，结果不采用')
                digest = value.hexdigest()
            except Stopped:
                raise
            except (OSError, ValueError) as exc:
                error = str(exc)
            with self.db.connect() as c:
                c.execute('UPDATE inventory_entries SET checked=1,sha256=?,error=? WHERE inventory_id=? AND relpath=?', (digest, error, iid, entry['relpath']))
                c.execute('UPDATE inventories SET processed=processed+1,errors=errors+? WHERE id=?', (int(bool(error)), iid))
        self.validate_inventory(iid)
        self.db.execute("UPDATE inventories SET status='completed' WHERE id=? AND status='running'", (iid,))

    def control(self, table, rid, action):
        row = self.db.one(f'SELECT * FROM {table} WHERE id=?', (rid,))
        if not row:
            raise HTTPException(404, '任务不存在')
        if action not in {'pause', 'resume', 'cancel'}:
            raise HTTPException(400, '无效操作')
        if row['status'] == 'completed' or (action == 'resume' and row['status'] in {'running', 'queued'}):
            raise HTTPException(409, '当前状态不能执行该操作')
        state = {'pause': 'paused', 'resume': 'queued', 'cancel': 'cancelled'}[action]
        self.db.execute(f'UPDATE {table} SET status=?,message=NULL WHERE id=?', (state, rid))
        return {'ok': True}

    def call(self, side, path, body=None):
        cid = side.connection_id
        if not cid:
            if path == '/api/inventories':
                return self.inventory(InventoryInput(**body))
            parts = path.split('?')[0].split('/')
            iid = parts[3]
            if len(parts) > 4 and parts[4] == 'entries':
                offset = int(path.split('offset=')[1])
                self.validate_inventory(iid)
                return {'items': self.db.rows('SELECT relpath,size,sha256,error FROM inventory_entries WHERE inventory_id=? ORDER BY relpath LIMIT 1000 OFFSET ?', (iid, offset))}
            if len(parts) > 4:
                return self.control('inventories', iid, parts[4])
            return self.validate_inventory(iid)[0]
        connection = self.db.one('SELECT * FROM connections WHERE id=?', (cid,))
        if not connection:
            raise ValueError('连接已移除')
        token = self.sessions.get(cid) or self.credentials.load(cid)
        if not token:
            raise ValueError('请先登录两边 NAS，然后恢复任务')
        with httpx.Client(timeout=httpx.Timeout(45, connect=8), trust_env=False, follow_redirects=False) as client:
            response = client.request('POST' if body is not None else 'GET', connection['url'] + path, json=body,
                                      headers={'Authorization': 'Bearer ' + token})
        if response.status_code != 200:
            if response.status_code == 401:
                raise ValueError('NAS 登录已过期，请重新登录后恢复任务')
            try:
                detail = response.json().get('detail', '')
            except ValueError:
                detail = ''
            raise ValueError(f'NAS 请求失败 ({response.status_code})：{detail or "请检查网络及两边服务版本"}')
        return response.json()

    def run_comparison(self, rid):
        row = self.db.one('SELECT * FROM comparisons WHERE id=?', (rid,))
        spec = ComparisonInput.model_validate_json(row['spec'])
        snapshots = json.loads(row['snapshots'])
        try:
            for name, side in [('left', spec.left), ('right', spec.right)]:
                self.check('comparisons', rid)
                iid = row[name + '_inventory']
                if not iid:
                    inv = self.call(side, '/api/inventories', {'root_id': side.root_id, 'subpath': side.subpath})
                    iid = inv['id']
                    self.db.execute(f'UPDATE comparisons SET {name}_inventory=? WHERE id=?', (iid, rid))
                snapshots[name] = self.call(side, f'/api/inventories/{iid}')
                self.db.execute('UPDATE comparisons SET snapshots=? WHERE id=?', (json.dumps(snapshots), rid))
                if spec.verify:
                    state = snapshots[name]['status']
                    if state not in {'running', 'queued', 'completed'}:
                        self.call(side, f'/api/inventories/{iid}/resume', {})
                    while True:
                        self.check('comparisons', rid)
                        inv = self.call(side, f'/api/inventories/{iid}')
                        self.db.execute('UPDATE comparisons SET message=? WHERE id=?', (f'{"A" if name == "left" else "B"} 内容校验 {inv["processed"]}/{inv["total"]}，异常 {inv["errors"]}', rid))
                        if inv['status'] == 'completed':
                            break
                        if inv['status'] not in {'running', 'queued'}:
                            raise ValueError(inv.get('message') or '远端校验已暂停，可恢复比对')
                        if self.stop.wait(.7):
                            raise Stopped()
                self.db.execute('DELETE FROM comparison_entries WHERE comparison_id=? AND side=?', (rid, name))
                offset = 0
                while True:
                    self.check('comparisons', rid)
                    batch = self.call(side, f'/api/inventories/{iid}/entries?offset={offset}')['items']
                    if not batch:
                        break
                    with self.db.connect() as c:
                        c.executemany('INSERT INTO comparison_entries VALUES(?,?,?,?,?,?)',
                                      [(rid, name, e['relpath'], e['size'], e.get('sha256'), e.get('error')) for e in batch])
                    offset += len(batch)
                    self.db.execute('UPDATE comparisons SET processed=(SELECT COUNT(*) FROM comparison_entries WHERE comparison_id=?),message=? WHERE id=?', (rid, f'读取 {name} 清单：{offset}', rid))
            # Revalidate both snapshots after collection; don't claim a finished comparison
            # if a rescan/offline event invalidated the original inventories.
            row = self.db.one('SELECT * FROM comparisons WHERE id=?', (rid,))
            for name, side in [('left', spec.left), ('right', spec.right)]:
                self.call(side, f'/api/inventories/{row[name + "_inventory"]}')
            self.check('comparisons', rid)
            self.db.execute("UPDATE comparisons SET status='completed',message='只读比对完成；结果基于所列扫描快照，不代表之后的实时文件状态' WHERE id=? AND status='running'", (rid,))
        except BaseException:
            # Pause owned hash jobs on either peer; never modify source files.
            row = self.db.one('SELECT * FROM comparisons WHERE id=?', (rid,))
            if spec.verify:
                for name, side in [('left', spec.left), ('right', spec.right)]:
                    iid = row[name + '_inventory']
                    if iid:
                        try:
                            inv = self.call(side, f'/api/inventories/{iid}')
                            if inv['status'] in {'running', 'queued'}:
                                self.call(side, f'/api/inventories/{iid}/pause', {})
                        except Exception:
                            pass
            raise

    def result_sql(self):
        return '''WITH pairs AS (
          SELECT a.relpath,a.size left_size,b.size right_size,a.sha256 left_hash,b.sha256 right_hash,
                 a.error left_error,b.error right_error
          FROM comparison_entries a LEFT JOIN comparison_entries b
          ON b.comparison_id=a.comparison_id AND b.side='right' AND b.relpath=a.relpath
          WHERE a.comparison_id=? AND a.side='left'
          UNION ALL
          SELECT b.relpath,NULL,b.size,NULL,b.sha256,NULL,b.error FROM comparison_entries b
          WHERE b.comparison_id=? AND b.side='right' AND NOT EXISTS (
          SELECT 1 FROM comparison_entries a WHERE a.comparison_id=b.comparison_id AND a.side='left' AND a.relpath=b.relpath)
        ), results AS (SELECT *,CASE
          WHEN left_error IS NOT NULL OR right_error IS NOT NULL THEN 'error'
          WHEN left_size IS NULL THEN 'only_right'
          WHEN right_size IS NULL THEN 'only_left'
          WHEN left_size<>right_size THEN 'different'
          WHEN left_hash IS NULL OR right_hash IS NULL THEN 'pending'
          WHEN left_hash=right_hash THEN 'same' ELSE 'different' END category FROM pairs) '''

    def results(self, rid, category='', offset=0, limit=100):
        run = self.db.one('SELECT * FROM comparisons WHERE id=?', (rid,))
        if not run:
            raise HTTPException(404)
        run['spec'] = json.loads(run['spec'])
        run['snapshots'] = json.loads(run['snapshots'])
        if run['status'] != 'completed':
            return {'run': run, 'summary': [], 'items': [], 'total': 0, 'move_hints': []}
        query = self.result_sql()
        summary = self.db.rows(query + 'SELECT category,COUNT(*) count,COALESCE(SUM(left_size),0) left_bytes,COALESCE(SUM(right_size),0) right_bytes FROM results GROUP BY category', (rid, rid))
        where, args = (' WHERE category=?', (rid, rid, category)) if category else ('', (rid, rid))
        items = self.db.rows(query + 'SELECT * FROM results' + where + ' ORDER BY relpath LIMIT ? OFFSET ?', (*args, limit, offset))
        total = self.db.one(query + 'SELECT COUNT(*) n FROM results' + where, args)['n']
        moves = self.db.rows('''SELECT a.relpath left_path,b.relpath right_path,a.size FROM comparison_entries a
          JOIN comparison_entries b ON b.comparison_id=a.comparison_id AND b.side='right' AND b.sha256=a.sha256 AND b.size=a.size
          WHERE a.comparison_id=? AND a.side='left' AND a.sha256 IS NOT NULL AND a.relpath<>b.relpath
          AND NOT EXISTS(SELECT 1 FROM comparison_entries r WHERE r.comparison_id=a.comparison_id AND r.side='right' AND r.relpath=a.relpath)
          AND NOT EXISTS(SELECT 1 FROM comparison_entries l WHERE l.comparison_id=b.comparison_id AND l.side='left' AND l.relpath=b.relpath)
          ORDER BY a.relpath,b.relpath LIMIT 100''', (rid,))
        return {'run': run, 'summary': summary, 'items': items, 'total': total, 'move_hints': moves}


def register_comparison(app, service, authorized, local_only):
    router = APIRouter(prefix='/api', dependencies=[Depends(authorized)])

    @router.post('/inventories')
    def create_inventory(data: InventoryInput):
        return service.inventory(data)

    @router.get('/inventories/{iid}')
    def inventory_status(iid: str):
        return service.validate_inventory(iid)[0]

    @router.get('/inventories/{iid}/entries')
    def inventory_entries(iid: str, offset: int = Query(0, ge=0)):
        service.validate_inventory(iid)
        return {'items': service.db.rows('SELECT relpath,size,sha256,error FROM inventory_entries WHERE inventory_id=? ORDER BY relpath LIMIT 1000 OFFSET ?', (iid, offset))}

    @router.post('/inventories/{iid}/{action}')
    def inventory_action(iid: str, action: str):
        service.validate_inventory(iid)
        return service.control('inventories', iid, action)

    @router.post('/comparisons', dependencies=[Depends(local_only)])
    def create_comparison(data: ComparisonInput):
        if data.left == data.right:
            raise HTTPException(400, '请选择两个不同的目录或连接')
        for side in [data.left, data.right]:
            if side.connection_id and not service.db.one('SELECT id FROM connections WHERE id=?', (side.connection_id,)):
                raise HTTPException(404, '连接不存在')
        rid = str(uuid.uuid4())
        service.db.execute("INSERT INTO comparisons(id,created,status,spec) VALUES(?,?,'queued',?)", (rid, now(), data.model_dump_json()))
        return {'id': rid}

    @router.get('/comparisons', dependencies=[Depends(local_only)])
    def comparison_list():
        return service.db.rows('SELECT id,created,status,message,processed FROM comparisons ORDER BY created DESC LIMIT 50')

    @router.get('/comparisons/{rid}', dependencies=[Depends(local_only)])
    def comparison_detail(rid: str, category: str = '', offset: int = Query(0, ge=0)):
        return service.results(rid, category, offset)

    @router.post('/comparisons/{rid}/{action}', dependencies=[Depends(local_only)])
    def comparison_action(rid: str, action: str):
        return service.control('comparisons', rid, action)

    @router.get('/comparisons/{rid}/export', dependencies=[Depends(local_only)])
    def export_comparison(rid: str):
        if service.results(rid)['run']['status'] != 'completed':
            raise HTTPException(409, '请等待比对完成后导出')
        def chunks():
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            yield '\ufeff'
            writer.writerow(['相对路径', '结果', 'A 字节数', 'B 字节数', 'A SHA256', 'B SHA256', 'A 错误', 'B 错误'])
            yield buffer.getvalue()
            buffer.seek(0); buffer.truncate(0)
            offset = 0
            while True:
                rows = service.db.rows(service.result_sql() + 'SELECT * FROM results ORDER BY relpath LIMIT 1000 OFFSET ?', (rid, rid, offset))
                if not rows:
                    break
                for row in rows:
                    values = [row[k] for k in ['relpath', 'category', 'left_size', 'right_size', 'left_hash', 'right_hash', 'left_error', 'right_error']]
                    writer.writerow(["'" + v if isinstance(v, str) and (v.lstrip().startswith(('=', '+', '-', '@')) or v.startswith(('\t', '\r'))) else v for v in values])
                yield buffer.getvalue()
                buffer.seek(0); buffer.truncate(0)
                offset += len(rows)
        return StreamingResponse(chunks(), media_type='text/csv; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="comparison-{rid}.csv"'})

    app.include_router(router)
