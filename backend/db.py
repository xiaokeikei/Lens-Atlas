from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3
import uuid

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS roots(
 id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, label TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'new', error TEXT, last_scan TEXT);
CREATE TABLE IF NOT EXISTS assets(
 id INTEGER PRIMARY KEY, root_id INTEGER NOT NULL REFERENCES roots(id), relpath TEXT NOT NULL,
 size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL, kind TEXT NOT NULL, ext TEXT NOT NULL,
 seen TEXT, deleted INTEGER NOT NULL DEFAULT 0,
 metadata_status TEXT NOT NULL DEFAULT 'pending', metadata_error TEXT,
 preview_status TEXT NOT NULL DEFAULT 'pending', preview_error TEXT,
 playback_status TEXT NOT NULL DEFAULT 'unknown',
 camera TEXT, lens TEXT, focal_native REAL, focal_equiv REAL, focal_source TEXT,
 taken_at TEXT, time_source TEXT, aperture REAL, shutter TEXT, iso REAL,
 width INTEGER, height INTEGER, duration REAL, codec TEXT, metadata_json TEXT,
 UNIQUE(root_id, relpath));
CREATE INDEX IF NOT EXISTS idx_assets_root_active ON assets(root_id,deleted,kind);
CREATE INDEX IF NOT EXISTS idx_assets_camera ON assets(camera);
CREATE INDEX IF NOT EXISTS idx_assets_lens ON assets(lens);
CREATE INDEX IF NOT EXISTS idx_assets_equiv ON assets(focal_equiv);
CREATE INDEX IF NOT EXISTS idx_assets_native ON assets(focal_native);
CREATE INDEX IF NOT EXISTS idx_assets_time ON assets(taken_at);
CREATE INDEX IF NOT EXISTS idx_assets_statistics ON assets(
 deleted,kind,camera,lens,focal_equiv,focal_native,taken_at,size,root_id,metadata_status,preview_status);
CREATE TABLE IF NOT EXISTS jobs(
 id TEXT PRIMARY KEY, root_id INTEGER NOT NULL REFERENCES roots(id), status TEXT NOT NULL,
 phase TEXT NOT NULL DEFAULT 'enumerate', enumerated INTEGER NOT NULL DEFAULT 0,
 processed INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0,
 errors INTEGER NOT NULL DEFAULT 0, message TEXT, started TEXT NOT NULL,
 updated TEXT NOT NULL, enumeration_complete INTEGER NOT NULL DEFAULT 0, force INTEGER NOT NULL DEFAULT 0);
CREATE UNIQUE INDEX IF NOT EXISTS idx_active_root ON jobs(root_id)
 WHERE status IN ('queued','running','paused');
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS connections(id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
            db.execute("INSERT OR IGNORE INTO settings VALUES('library_id',?)", (json.dumps(str(uuid.uuid4())),))
            db.execute("INSERT OR IGNORE INTO settings VALUES('schema_version','1')")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=30000")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def rows(self, sql, params=()):
        with self.connect() as db:
            return [dict(r) for r in db.execute(sql, params)]

    def one(self, sql, params=()):
        rows = self.rows(sql, params)
        return rows[0] if rows else None

    def execute(self, sql, params=()):
        with self.connect() as db:
            return db.execute(sql, params).lastrowid

    def setting(self, key, default=None):
        row = self.one("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(row["value"]) if row else default

    def set_setting(self, key, value):
        self.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, json.dumps(value)))

    def backup(self, target: Path):
        with self.connect() as source, sqlite3.connect(target) as dest:
            source.backup(dest)
