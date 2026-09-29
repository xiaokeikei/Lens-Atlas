from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import threading
import tempfile
import time
import uuid
from .config import bundle_root
from .metadata import classify


def now():
    return datetime.now(timezone.utc).isoformat()


class ScanStopped(Exception):
    pass


class Scanner:
    def __init__(self, db, config):
        self.db, self.config = db, config
        self.stop = threading.Event()
        self.thread = None
        self.current_root = None
        self.preview_lock = threading.Lock()
        self.worker_slots = threading.BoundedSemaphore(config.workers)
        # A crash never turns a partial traversal into deletions.
        db.execute("UPDATE jobs SET status='paused',message='服务重启：任务已保留，请恢复',updated=? WHERE status IN ('running','queued')", (now(),))
        db.execute("UPDATE roots SET status='interrupted' WHERE status='scanning'")

    def start(self):
        self.thread = threading.Thread(target=self.loop, daemon=True, name="library-scan")
        self.thread.start()

    def close(self):
        self.stop.set()
        self.db.execute("UPDATE jobs SET status='paused',message='服务停止，任务可恢复',updated=? WHERE status IN ('queued','running')", (now(),))
        if self.thread:
            self.thread.join(timeout=self.config.timeout + 5)

    def enqueue(self, root_id, force=False):
        existing = self.db.one("SELECT * FROM jobs WHERE root_id=? AND status IN ('queued','running','paused')", (root_id,))
        if existing:
            return existing
        job_id = str(uuid.uuid4())
        self.db.execute("INSERT INTO jobs(id,root_id,status,started,updated,force) VALUES(?,?,'queued',?,?,?)", (job_id, root_id, now(), now(), int(force)))
        return self.db.one("SELECT * FROM jobs WHERE id=?", (job_id,))

    def control(self, job_id, action):
        job = self.db.one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if not job:
            raise ValueError("任务不存在")
        status = {"pause": "paused", "cancel": "cancelled", "resume": "queued"}[action]
        if action == "resume" and job["status"] not in {"paused", "failed", "cancelled"}:
            raise ValueError("仅暂停、失败或取消的任务可恢复")
        if action in {"pause", "cancel"} and job["status"] not in {"queued", "running", "paused"}:
            raise ValueError("任务已结束")
        if action == "resume":
            conflict = self.db.one("SELECT id FROM jobs WHERE root_id=? AND id<>? AND status IN ('queued','running','paused')", (job["root_id"], job_id))
            if conflict:
                raise ValueError("此目录已有任务，请先完成或取消它")
        self.db.execute("UPDATE jobs SET status=?,message=?,updated=? WHERE id=?", (status, {"pause":"已暂停", "cancel":"已取消；索引保留", "resume":"等待恢复"}[action], now(), job_id))

    def check(self, job_id):
        row = self.db.one("SELECT status FROM jobs WHERE id=?", (job_id,))
        if self.stop.is_set() or row["status"] != "running":
            raise ScanStopped()

    def loop(self):
        while not self.stop.wait(.25):
            job = self.db.one("SELECT * FROM jobs WHERE status='queued' ORDER BY started LIMIT 1")
            if not job:
                continue
            self.current_root = job['root_id']
            try:
                self.run_job(job)
            finally:
                self.current_root = None

    def run_job(self, job):
        jid, rid = job["id"], job["root_id"]
        root = self.db.one("SELECT * FROM roots WHERE id=?", (rid,))
        path = Path(root["path"])
        self.db.execute("UPDATE jobs SET status='running',message=NULL,updated=? WHERE id=?", (now(), jid))
        try:
            self.check(jid)
            if not self.config.desktop and not any(path.resolve().is_relative_to(p) for p in self.config.allowed_roots):
                raise PermissionError('目录已指向服务端授权映射范围之外')
            if not path.is_dir():
                raise FileNotFoundError("目录离线或不存在；原索引已保留")
            self.db.execute("UPDATE roots SET status='scanning',error=NULL WHERE id=?", (rid,))
            if not job["enumeration_complete"]:
                self.enumerate(job, path)
            for phase, column in (("metadata", "metadata_status"), ("preview", "preview_status")):
                self.check(jid)
                total = self.db.one(f"SELECT COUNT(*) n FROM assets WHERE root_id=? AND deleted=0 AND kind IN ('photo','video') AND {column}='pending'", (rid,))["n"]
                self.db.execute("UPDATE jobs SET phase=?,processed=0,total=?,updated=? WHERE id=?", (phase, total, now(), jid))
                done = 0
                with ThreadPoolExecutor(max_workers=self.config.workers) as pool:
                    while True:
                        self.check(jid)
                        batch = self.db.rows(f"SELECT a.*,r.path root_path FROM assets a JOIN roots r ON a.root_id=r.id WHERE a.root_id=? AND a.deleted=0 AND a.kind IN ('photo','video') AND a.{column}='pending' LIMIT ?", (rid, self.config.workers * 2))
                        if not batch:
                            break
                        futures = [pool.submit(self.process, item, phase) for item in batch]
                        for future in as_completed(futures):
                            failed = future.result()
                            done += 1
                            self.db.execute("UPDATE jobs SET processed=?,errors=errors+?,updated=? WHERE id=?", (done, int(failed), now(), jid))
            self.check(jid)
            self.trim_cache()
            self.db.execute("UPDATE jobs SET status='completed',phase='complete',message='扫描完成',updated=? WHERE id=?", (now(), jid))
            self.db.execute("UPDATE roots SET status='online',last_scan=?,error=NULL WHERE id=?", (now(), rid))
        except ScanStopped:
            self.db.execute("UPDATE roots SET status='interrupted' WHERE id=?", (rid,))
        except Exception as e:
            status = "permission_denied" if isinstance(e, PermissionError) else "offline" if isinstance(e, (FileNotFoundError, OSError)) else "error"
            self.db.execute("UPDATE roots SET status=?,error=? WHERE id=?", (status, str(e), rid))
            self.db.execute("UPDATE jobs SET status='failed',message=?,updated=? WHERE id=?", (str(e), now(), jid))

    def enumerate(self, job, root):
        jid, rid = job["id"], job["root_id"]
        initial = root.stat()
        old_count = self.db.one("SELECT COUNT(*) n FROM assets WHERE root_id=? AND deleted=0", (rid,))["n"]
        count = 0
        self.db.execute("UPDATE jobs SET phase='enumerate',enumerated=0,updated=? WHERE id=?", (now(), jid))
        def onerror(error):
            raise error
        for directory, dirs, files in os.walk(root, followlinks=False, onerror=onerror):
            self.check(jid)
            dirs[:] = [d for d in dirs if not (Path(directory) / d).is_symlink() and not (Path(directory) / d).is_junction()]
            for name in files:
                self.check(jid)
                source = Path(directory) / name
                if source.is_symlink():
                    continue
                try:
                    stat = source.stat()
                except FileNotFoundError:
                    # A disappearing file makes reconciliation unsafe for this traversal.
                    raise OSError("枚举期间文件消失，保留已有索引；请重试")
                relative = source.relative_to(root).as_posix()
                kind, ext = classify(source)
                with self.db.connect() as db:
                    prior = db.execute("SELECT * FROM assets WHERE root_id=? AND relpath=?", (rid, relative)).fetchone()
                    if not prior:
                        state = "pending" if kind in {"photo", "video"} else "not_applicable"
                        db.execute("INSERT INTO assets(root_id,relpath,size,mtime_ns,kind,ext,seen,metadata_status,preview_status) VALUES(?,?,?,?,?,?,?,?,?)", (rid,relative,stat.st_size,stat.st_mtime_ns,kind,ext,jid,state,state))
                    else:
                        changed = prior["size"] != stat.st_size or prior["mtime_ns"] != stat.st_mtime_ns or job["force"] or prior["deleted"]
                        db.execute("UPDATE assets SET seen=?,deleted=0,size=?,mtime_ns=? WHERE id=?", (jid,stat.st_size,stat.st_mtime_ns,prior["id"]))
                        if kind in {"photo", "video"}:
                            if changed:
                                db.execute("UPDATE assets SET metadata_status='pending',preview_status='pending',metadata_error=NULL,preview_error=NULL,camera=NULL,lens=NULL,focal_native=NULL,focal_equiv=NULL,focal_source=NULL,taken_at=NULL,time_source=NULL,aperture=NULL,shutter=NULL,iso=NULL,metadata_json=NULL WHERE id=?", (prior["id"],))
                            else:
                                db.execute("UPDATE assets SET metadata_status=CASE WHEN metadata_status IN ('failed','permission_denied') THEN 'pending' ELSE metadata_status END, preview_status=CASE WHEN preview_status IN ('failed','permission_denied') THEN 'pending' ELSE preview_status END WHERE id=?", (prior["id"],))
                count += 1
                if count % 50 == 0:
                    self.db.execute("UPDATE jobs SET enumerated=?,updated=? WHERE id=?", (count,now(),jid))
        self.check(jid)
        final = root.stat()
        if (initial.st_dev, initial.st_ino) != (final.st_dev, final.st_ino) or (old_count > 0 and count == 0):
            raise OSError("目录身份改变或已有图库突然为空；不标记删除，请检查挂载")
        # Conservative first-release behavior: absence is a candidate, never automatic deletion.
        # Read access reports source_missing separately. Explicit root removal is the only purge.
        self.db.execute("UPDATE jobs SET enumeration_complete=1,enumerated=?,updated=? WHERE id=?", (count,now(),jid))

    def source_path(self, item):
        root = Path(item["root_path"]).resolve()
        if not self.config.desktop and not any(root.is_relative_to(p) for p in self.config.allowed_roots):
            raise PermissionError('素材根目录超出服务端授权映射范围')
        path = (root / item["relpath"]).resolve()
        if not path.is_relative_to(root):
            raise PermissionError("素材路径超出授权目录")
        return path

    def worker(self, args):
        fd, filename = tempfile.mkstemp(prefix='worker-',suffix='.json',dir=self.config.data_dir)
        os.close(fd)
        result_path = Path(filename)
        args = ['--output',filename,*args]
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--worker", *args]
        else:
            cmd = [sys.executable, "-m", "backend.worker", *args]
        try:
            with self.worker_slots:
                p = subprocess.run(cmd, cwd=str(bundle_root()), capture_output=True, timeout=self.config.timeout,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                value = json.loads(result_path.read_text(encoding='utf-8'))
            except ValueError:
                raise ValueError("工作进程异常退出，无法读取结果")
        finally:
            result_path.unlink(missing_ok=True)
        if p.returncode or "error" in value:
            if value.get("type") == "PermissionError":
                raise PermissionError(value.get("error"))
            raise ValueError(value.get("error", "处理失败"))
        return value

    def cache_path(self, item):
        key = hashlib.sha256(f'{item["id"]}:{item["size"]}:{item["mtime_ns"]}'.encode()).hexdigest()
        return self.config.data_dir / "cache" / (key + ".jpg")

    def process(self, item, phase):
        try:
            path = self.source_path(item)
            if phase == "metadata":
                value = self.worker(["metadata", str(path)])
                self.db.execute("UPDATE assets SET " + ",".join(f"{key}=?" for key in value) + " WHERE id=? AND mtime_ns=?", (*value.values(),item["id"],item["mtime_ns"]))
                return value.get("metadata_status") != "ok"
            self.make_preview(item)
            return False
        except Exception as e:
            status = "permission_denied" if isinstance(e, PermissionError) else "failed"
            error = "单文件处理超时" if isinstance(e, subprocess.TimeoutExpired) else str(e)
            self.db.execute(f"UPDATE assets SET {phase}_status=?,{phase}_error=? WHERE id=?", (status,error,item["id"]))
            return True

    def make_preview(self, item):
        target = self.cache_path(item)
        with self.preview_lock:
            if target.is_file():
                target.touch()
                self.db.execute("UPDATE assets SET preview_status='ready',preview_error=NULL WHERE id=?", (item["id"],))
                return target
            path = self.source_path(item)
            temporary = target.with_suffix(".tmp.jpg")
            try:
                self.worker(["preview", str(path), str(temporary)])
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
            self.db.execute("UPDATE assets SET preview_status='ready',preview_error=NULL WHERE id=?", (item["id"],))
            self.trim_cache(keep=target)
        return target

    def cache_info(self):
        files = list((self.config.data_dir / "cache").glob("*.jpg"))
        size = 0
        for path in files:
            try:
                size += path.stat().st_size
            except FileNotFoundError:
                pass
        return {"bytes": size, "files": len(files), "limit_bytes": self.db.setting("cache_bytes",self.config.cache_bytes)}

    def trim_cache(self, keep=None):
        limit = self.db.setting("cache_bytes", self.config.cache_bytes)
        files = []
        for p in (self.config.data_dir / "cache").glob("*.jpg"):
            try:
                s = p.stat()
                files.append((s.st_mtime, s.st_size, p))
            except FileNotFoundError:
                pass
        total = sum(s for _, s, _ in files)
        for _, size, p in sorted(files):
            if total <= limit:
                break
            if p == keep:
                continue
            p.unlink(missing_ok=True)
            total -= size

    def clear_cache(self):
        with self.preview_lock:
            for p in (self.config.data_dir / "cache").glob("*.jpg"):
                p.unlink(missing_ok=True)
            self.db.execute("UPDATE assets SET preview_status='evicted' WHERE preview_status='ready'")
