import json
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from .models import RecordInput, SettingsInput, ProfileInput
from . import activity as activity_rules


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = path
        self.lock = threading.RLock()
        with self.db() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS records (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,
                    detail TEXT NOT NULL, status TEXT NOT NULL, due TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY, role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS actions (
                    id TEXT PRIMARY KEY, type TEXT NOT NULL, payload TEXT NOT NULL,
                    status TEXT NOT NULL, result_id TEXT, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE VIRTUAL TABLE IF NOT EXISTS record_search USING fts5(id UNINDEXED, title, detail);
                CREATE TRIGGER IF NOT EXISTS records_ai AFTER INSERT ON records BEGIN
                    INSERT INTO record_search(id,title,detail) VALUES(new.id,new.title,new.detail);
                END;
                CREATE TRIGGER IF NOT EXISTS records_ad AFTER DELETE ON records BEGIN
                    DELETE FROM record_search WHERE id=old.id;
                END;
                CREATE TRIGGER IF NOT EXISTS records_au AFTER UPDATE ON records BEGIN
                    DELETE FROM record_search WHERE id=old.id;
                    INSERT INTO record_search(id,title,detail) VALUES(new.id,new.title,new.detail);
                END;
            """)
            columns = {r[1] for r in db.execute("PRAGMA table_info(records)")}
            for name, declaration in [("goal_id", "TEXT REFERENCES records(id) ON DELETE SET NULL"),
                                      ("priority", "TEXT NOT NULL DEFAULT 'normal'"), ("effort_minutes", "INTEGER")]:
                if name not in columns:
                    db.execute(f"ALTER TABLE records ADD COLUMN {name} {declaration}")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS record_sources (
                    record_id TEXT PRIMARY KEY REFERENCES records(id) ON DELETE CASCADE,
                    fingerprint TEXT UNIQUE NOT NULL, source TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS embeddings (
                    record_id TEXT PRIMARY KEY REFERENCES records(id) ON DELETE CASCADE,
                    digest TEXT NOT NULL, model TEXT NOT NULL, vector TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, app TEXT NOT NULL, bundle_id TEXT NOT NULL,
                    title TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT NOT NULL
                );
                PRAGMA user_version=2;
            """)
            db.execute("""INSERT INTO record_search(id,title,detail)
                       SELECT r.id,r.title,r.detail FROM records r
                       WHERE NOT EXISTS (SELECT 1 FROM record_search s WHERE s.id=r.id)""")
        os.chmod(path, 0o600)

    @contextmanager
    def db(self):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=10)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

    def records(self):
        with self.db() as db:
            return [dict(r) for r in db.execute("""SELECT r.*, s.source FROM records r
                       LEFT JOIN record_sources s ON r.id=s.record_id ORDER BY r.created_at DESC""")]

    def validate_record(self, record, db, existing_id=None):
        if record.goal_id:
            goal = db.execute("SELECT kind,status FROM records WHERE id=?", (record.goal_id,)).fetchone()
            existing = db.execute("SELECT goal_id FROM records WHERE id=?", (existing_id,)).fetchone() if existing_id else None
            kept_link = existing and existing["goal_id"] == record.goal_id
            if not goal or goal["kind"] != "goal" or (goal["status"] != "active" and not kept_link):
                raise ValueError("Choose an existing active goal for this task")

    def put(self, record: RecordInput, record_id=None, db=None):
        if db is None:
            with self.db() as conn:
                return self.put(record, record_id, conn)
        self.validate_record(record, db, record_id)
        ident, timestamp = record_id or str(uuid4()), now()
        if record_id:
            old = db.execute("SELECT kind FROM records WHERE id=?", (record_id,)).fetchone()
            if not old:
                raise KeyError(record_id)
            if old["kind"] == "goal" and record.kind != "goal":
                raise ValueError("A goal cannot change type; create a different record instead")
            db.execute("""UPDATE records SET kind=?,title=?,detail=?,status=?,due=?,goal_id=?,priority=?,
                                   effort_minutes=?,updated_at=? WHERE id=?""",
                                (*record.model_dump().values(), timestamp, ident))
            db.execute("DELETE FROM embeddings WHERE record_id=?", (ident,))
        else:
            db.execute("""INSERT INTO records (id,kind,title,detail,status,due,goal_id,priority,effort_minutes,created_at,updated_at)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (ident, *record.model_dump().values(), timestamp, timestamp))
        return dict(db.execute("SELECT * FROM records WHERE id=?", (ident,)).fetchone())

    def profile(self):
        return ProfileInput.model_validate(self.setting("profile", {})).model_dump()

    def delete(self, record_id):
        with self.db() as db:
            if not db.execute("DELETE FROM records WHERE id=?", (record_id,)).rowcount:
                raise KeyError(record_id)
            # The action ledger retains status but not copies of a deleted personal memory.
            db.execute("UPDATE actions SET payload='{}' WHERE result_id=?", (record_id,))
            db.execute("DELETE FROM settings WHERE key='last_retrieval'")

    def message(self, role, content):
        with self.db() as db:
            db.execute("INSERT INTO messages VALUES(?,?,?,?)", (str(uuid4()), role, content, now()))

    def messages(self, limit=100):
        with self.db() as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM (SELECT * FROM messages ORDER BY rowid DESC LIMIT ?) ORDER BY created_at", (limit,))]

    def clear_history(self):
        with self.db() as db:
            db.execute("DELETE FROM messages")
            db.execute("UPDATE actions SET status='rejected',payload='{}' WHERE status='pending'")

    def propose(self, record: RecordInput):
        return self.propose_many([record])[0]

    def propose_many(self, records):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            for record in records:
                self.validate_record(record, db)
            pending = {a["payload"]: a["id"] for a in db.execute("SELECT id,payload FROM actions WHERE status='pending'")}
            ids = []
            for record in records:
                payload = record.model_dump_json()
                ident = pending.get(payload)
                if not ident:
                    ident = str(uuid4())
                    db.execute("INSERT INTO actions VALUES(?,?,?,?,?,?)",
                               (ident, "create_record", payload, "pending", None, now()))
                    pending[payload] = ident
                ids.append(ident)
        return ids

    def actions(self):
        with self.db() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM actions ORDER BY rowid DESC LIMIT 200")]
        for row in rows:
            row["payload"] = json.loads(row["payload"])
        return rows

    def decide(self, action_id, approve):
        # Serialized transaction: approving twice never creates duplicate records.
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone()
            if row is None:
                raise KeyError(action_id)
            if row["status"] != "pending":
                return {"status": row["status"], "result_id": row["result_id"]}
            result = self.put(RecordInput.model_validate_json(row["payload"]), db=db) if approve else None
            status = "approved" if approve else "rejected"
            db.execute("UPDATE actions SET status=?,result_id=? WHERE id=?",
                       (status, result["id"] if result else None, action_id))
            return {"status": status, "result_id": result["id"] if result else None}

    def record_activity(self, sample, at=None):
        at = at or datetime.now(timezone.utc)
        stamp = at.isoformat()
        with self.db() as db:
            last = db.execute("SELECT * FROM activity ORDER BY id DESC LIMIT 1").fetchone()
            gap = (at - datetime.fromisoformat(last["ended_at"])).total_seconds() if last else None
            if last and last["app"] == sample.app and last["title"] == sample.title and 0 <= gap <= activity_rules.MERGE_GAP_SECONDS:
                db.execute("UPDATE activity SET ended_at=? WHERE id=?", (stamp, last["id"]))
            else:
                db.execute("INSERT INTO activity (app,bundle_id,title,started_at,ended_at) VALUES (?,?,?,?,?)",
                           (sample.app, sample.bundle_id, sample.title, stamp, stamp))
            cutoff = (at - timedelta(days=activity_rules.RETENTION_DAYS)).isoformat()
            db.execute("DELETE FROM activity WHERE ended_at < ?", (cutoff,))

    def activity(self, limit=40, since=None):
        with self.db() as db:
            if since:
                rows = db.execute("SELECT * FROM activity WHERE ended_at >= ? ORDER BY id DESC LIMIT 2000", (since.isoformat(),))
            else:
                rows = db.execute("SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(r) for r in rows]

    def clear_activity(self):
        with self.db() as db:
            db.execute("DELETE FROM activity")
            db.execute("DELETE FROM settings WHERE key IN ('last_nudge_at','last_review_at')")

    def activity_summary(self, minutes=120, at=None):
        at = at or datetime.now(timezone.utc)
        return activity_rules.summary(self.activity(since=at - timedelta(minutes=minutes)), at, minutes)

    def setting(self, key, default=None):
        with self.db() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, json.dumps(value)))

    def settings(self):
        values = self.setting("preferences", {})
        # Legacy OpenAI settings never enable a different provider implicitly.
        if values.get("model") and not values["model"].startswith("gemini-"):
            values = {**values, "model":SettingsInput().model, "ai_enabled":False, "semantic_memory":False}
        return SettingsInput.model_validate(values)

    def search(self, query, limit=14):
        terms = re.findall(r"\w+", query, re.UNICODE)[:24]
        match = " OR ".join('"' + t + '"' for t in terms)
        if not match:
            return []
        with self.db() as db:
            return [dict(r) for r in db.execute("""SELECT r.*, provenance.source FROM record_search s JOIN records r ON r.id=s.id
                       LEFT JOIN record_sources provenance ON r.id=provenance.record_id WHERE record_search MATCH ? AND r.status='active' ORDER BY bm25(record_search) LIMIT ?""", (match, limit))]

    def context(self, query, limit=14):
        relevant = self.search(query, limit)
        with self.db() as db:
            baseline = [dict(r) for r in db.execute("""SELECT * FROM records WHERE status='active'
                       ORDER BY CASE kind WHEN 'preference' THEN 0 WHEN 'goal' THEN 1 WHEN 'task' THEN 2 ELSE 3 END,
                       due IS NULL, due, updated_at DESC LIMIT 10""")]
        unique = {r["id"]: r for r in relevant + baseline}
        return list(unique.values())[:limit]

    def planning_context(self, query, semantic=None, at=None):
        # Reserved slots prevent a large number of keyword hits from excluding goals/preferences.
        with self.db() as db:
            goals = [dict(r) for r in db.execute("""SELECT * FROM records WHERE kind='goal' AND status='active'
                     ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END,
                     due IS NULL,due,updated_at DESC""")]
            # An explicitly selected goal takes precedence over the default twelve.
            goals = ([g for g in goals if g["id"] in query] + [g for g in goals if g["id"] not in query])[:12]
            tasks = [dict(r) for r in db.execute("""SELECT * FROM records WHERE kind='task' AND status='active'
                     ORDER BY due IS NULL,due,CASE priority WHEN 'high' THEN 0 ELSE 1 END LIMIT 16""")]
            preferences = [dict(r) for r in db.execute("SELECT * FROM records WHERE kind='preference' AND status='active' ORDER BY updated_at DESC LIMIT 8")]
            counts = {r["kind"]: r["n"] for r in db.execute("SELECT kind,count(*) n FROM records WHERE status='active' GROUP BY kind")}
        used = {r["id"] for r in goals + tasks + preferences}
        memories = []
        with self.db() as db:
            recent = [dict(r) for r in db.execute("""SELECT * FROM records
                      WHERE kind IN ('memory','project') AND status='active' ORDER BY updated_at DESC LIMIT 6""")]
        for row in (semantic or []) + self.search(query, 20) + recent:
            if row["id"] not in used:
                memories.append(row); used.add(row["id"])
            if len(memories) == 10:
                break
        with self.db() as db:
            sources = {r["record_id"]:r["source"] for r in db.execute("SELECT record_id,source FROM record_sources")}
        for row in goals + tasks + preferences + memories:
            row["source"] = sources.get(row["id"])
        result = {"profile": self.profile(), "goals": goals, "open_tasks": tasks,
                  "preferences": preferences, "memories": memories, "active_counts": counts,
                  "note": "Bounded selection. Use search_memory for other facts; omitted records are not absent."}
        if self.settings().activity_awareness:
            result["recent_activity"] = self.activity_summary(at=at)
        return result

    def import_records(self, selections, candidates):
        created, duplicates = [], 0
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            for selection in selections:
                candidate = candidates.get(selection.candidate_id)
                if candidate is None:
                    raise ValueError("Import preview expired or candidate is invalid; load the export again")
                fingerprint = candidate["id"]
                if db.execute("SELECT 1 FROM record_sources WHERE fingerprint=?", (fingerprint,)).fetchone():
                    duplicates += 1
                    continue
                row = self.put(selection.record, db=db)
                db.execute("INSERT INTO record_sources VALUES(?,?,?)", (row["id"], fingerprint, candidate["source"]))
                created.append(row["id"])
        return {"created": len(created), "duplicates": duplicates, "record_ids": created}
