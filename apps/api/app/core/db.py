import json
import re
import sqlite3
from contextlib import contextmanager
from .config import DATA_DIR

# One table per record kind; body is the contract JSON. Other kinds (e.g. Job) get their own table on first use.
TABLES = {'Workspace': 'workspaces', 'Asset': 'assets', 'BrandKit': 'brand_kits', 'Design': 'designs'}

def _table(db, kind):
    name = TABLES.get(kind) or re.sub(r'(?<!^)(?=[A-Z])', '_', kind).lower() + 's'
    if not re.fullmatch(r'[a-z_]+', name):
        raise ValueError(f'Invalid record kind {kind!r}')
    db.execute(f'CREATE TABLE IF NOT EXISTS {name} (id TEXT PRIMARY KEY, ws TEXT NOT NULL, body JSON NOT NULL)')
    db.execute(f'CREATE INDEX IF NOT EXISTS {name}_ws ON {name}(ws)')
    return name

@contextmanager
def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA_DIR / 'app.db', timeout=10)
    try:
        yield db
        db.commit()
    finally:
        db.close()

def put(kind, record_id, ws, body):
    with connect() as db:
        db.execute(f'INSERT INTO {_table(db, kind)} VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET ws=excluded.ws, body=excluded.body',
                   (record_id, ws, json.dumps(body)))

def get(kind, record_id):
    with connect() as db:
        row = db.execute(f'SELECT body FROM {_table(db, kind)} WHERE id=?', (record_id,)).fetchone()
    if row is None:
        raise KeyError(f'{kind} {record_id} not found')
    return json.loads(row[0])

def list_records(kind, ws=None):
    with connect() as db:
        table = _table(db, kind)
        rows = db.execute(f'SELECT body FROM {table}' + (' WHERE ws=?' if ws else '') + ' ORDER BY rowid', (ws,) if ws else ()).fetchall()
    return [json.loads(row[0]) for row in rows]

def delete(kind, record_id):
    with connect() as db:
        db.execute(f'DELETE FROM {_table(db, kind)} WHERE id=?', (record_id,))
