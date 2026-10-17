import json
import sqlite3
from contextlib import contextmanager
from .config import DATA_DIR

@contextmanager
def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA_DIR / 'app.db', timeout=10)
    try:
        db.execute('CREATE TABLE IF NOT EXISTS records (kind TEXT NOT NULL, id TEXT NOT NULL, ws TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(kind,id))')
        yield db
        db.commit()
    finally:
        db.close()

def put(kind, record_id, ws, body):
    with connect() as db:
        db.execute('INSERT INTO records VALUES (?, ?, ?, ?) ON CONFLICT(kind,id) DO UPDATE SET ws=excluded.ws, body=excluded.body', (kind, record_id, ws, json.dumps(body)))

def get(kind, record_id):
    with connect() as db:
        row = db.execute('SELECT body FROM records WHERE kind=? AND id=?', (kind, record_id)).fetchone()
    if row is None:
        raise KeyError(f'{kind} {record_id} not found')
    return json.loads(row[0])

def list_records(kind, ws=None):
    with connect() as db:
        rows = db.execute('SELECT body FROM records WHERE kind=?' + (' AND ws=?' if ws else '') + ' ORDER BY rowid', (kind, ws) if ws else (kind,)).fetchall()
    return [json.loads(row[0]) for row in rows]

def delete(kind, record_id):
    with connect() as db:
        db.execute('DELETE FROM records WHERE kind=? AND id=?', (kind, record_id))
