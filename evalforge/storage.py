"""SQLite persistence. Each write commits before returning to the caller."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS records (
                    kind TEXT NOT NULL, id TEXT NOT NULL, created_at TEXT NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY(kind, id));
                CREATE TABLE IF NOT EXISTS spans (
                    span_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL,
                    parent_span_id TEXT, started_at TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS spans_trace ON spans(trace_id, started_at);
            """)

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=15)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=15000")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def put(self, kind, payload):
        payload = {**payload}
        payload.setdefault("id", uuid4().hex)
        payload.setdefault("created_at", now())
        with self.connection() as conn:
            conn.execute("INSERT INTO records VALUES(?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload",
                         (kind, payload["id"], payload["created_at"], json.dumps(payload, ensure_ascii=False)))
        return payload

    def get(self, kind, record_id):
        with self.connection() as conn:
            row = conn.execute("SELECT payload FROM records WHERE kind=? AND id=?", (kind, record_id)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, kind):
        with self.connection() as conn:
            rows = conn.execute("SELECT payload FROM records WHERE kind=? ORDER BY created_at DESC", (kind,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def save_span(self, span):
        with self.connection() as conn:
            conn.execute("INSERT OR REPLACE INTO spans VALUES(?,?,?,?,?)", (
                span["span_id"], span["trace_id"], span["parent_span_id"], span["started_at"],
                json.dumps(span, ensure_ascii=False)))

    def spans(self, trace_id=None, limit=2000):
        with self.connection() as conn:
            if trace_id:
                rows = conn.execute("SELECT payload FROM spans WHERE trace_id=? ORDER BY started_at LIMIT ?", (trace_id, limit)).fetchall()
            else:
                rows = conn.execute("SELECT payload FROM spans ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
        return [json.loads(row[0]) for row in rows]
