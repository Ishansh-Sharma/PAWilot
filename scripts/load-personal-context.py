"""One-time, explicitly authorized local context import. Never run automatically on launch.

Usage: .venv/bin/python scripts/load-personal-context.py PRIVATE_JSON DATA_DIRECTORY
The JSON is private input, never an app resource. Back up SQLite before changes.
"""
import json
import os
from pathlib import Path
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from pawilot.models import ProfileInput, RecordInput
from pawilot.store import Store


def load_context(document, directory):
    profile = ProfileInput.model_validate(document['profile'])
    records = [RecordInput.model_validate(r) for r in document['records']]
    batch = document['import_id']
    if not isinstance(batch, str) or not 1 <= len(batch) <= 120:
        raise ValueError('Invalid import ID')
    source = json.dumps(document['source'])
    path = Path(directory) / 'pawilot.sqlite3'
    store = Store(path)
    marker = 'context_import:' + batch
    if store.setting(marker):
        return {'created':0, 'already_imported':True}
    backup = path.with_name('before-context-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f') + '.sqlite3')
    with sqlite3.connect(path) as origin, sqlite3.connect(backup) as target:
        origin.backup(target)
    os.chmod(backup, 0o600)
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM settings WHERE key=?', (marker,)).fetchone():
            return {'created':0, 'already_imported':True}
        for index, record in enumerate(records):
            row = store.put(record, db=db)
            db.execute('INSERT INTO record_sources VALUES(?,?,?)', (row['id'], batch+':'+str(index), source))
        db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', ('profile', profile.model_dump_json()))
        db.execute('INSERT INTO settings VALUES(?,?)', (marker, json.dumps({'count':len(records), 'source':document['source']})))
    return {'created':len(records), 'already_imported':False, 'backup':str(backup)}


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    print(json.dumps(load_context(json.loads(Path(sys.argv[1]).read_text()), sys.argv[2])))
