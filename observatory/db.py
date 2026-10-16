import sqlite3
from pathlib import Path

SCHEMA = """
BEGIN IMMEDIATE;
CREATE TABLE projects(id TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE sessions(
 id TEXT PRIMARY KEY, root_session_id TEXT NOT NULL, parent_thread_id TEXT,
 agent_kind TEXT NOT NULL DEFAULT 'unknown', project_id TEXT REFERENCES projects(id),
 version TEXT, started_at TEXT, last_seen TEXT,
 summary_events INTEGER NOT NULL DEFAULT 0);
CREATE INDEX sessions_root ON sessions(root_session_id);
CREATE TABLE tasks(
 session_id TEXT NOT NULL REFERENCES sessions(id), id TEXT NOT NULL,
 root_turn_id TEXT, parent_turn_id TEXT, trigger TEXT, started_at TEXT, ended_at TEXT,
 status TEXT NOT NULL DEFAULT 'unknown', model TEXT, effort TEXT,
 PRIMARY KEY(session_id,id));
CREATE INDEX tasks_recent ON tasks(started_at DESC);
CREATE INDEX tasks_root ON tasks(root_turn_id);
CREATE TABLE responses(
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL, task_id TEXT NOT NULL,
 root_session_id TEXT NOT NULL, root_turn_id TEXT, timestamp TEXT NOT NULL,
 model TEXT, effort TEXT,
 input_tokens INTEGER NOT NULL CHECK(input_tokens>=0),
 cached_input_tokens INTEGER NOT NULL CHECK(cached_input_tokens BETWEEN 0 AND input_tokens),
 output_tokens INTEGER NOT NULL CHECK(output_tokens>=0),
 reasoning_output_tokens INTEGER NOT NULL CHECK(reasoning_output_tokens BETWEEN 0 AND output_tokens),
 FOREIGN KEY(session_id,task_id) REFERENCES tasks(session_id,id));
CREATE INDEX responses_task ON responses(session_id,task_id);
CREATE INDEX responses_time ON responses(timestamp);
CREATE INDEX responses_model_time ON responses(model,timestamp);
CREATE INDEX responses_root ON responses(root_session_id,timestamp);
CREATE TABLE checkpoints(
 path TEXT PRIMARY KEY, offset INTEGER NOT NULL, size INTEGER NOT NULL,
 mtime_ns INTEGER NOT NULL, anchor TEXT NOT NULL, state TEXT NOT NULL,
 adapter TEXT NOT NULL);
CREATE TABLE diagnostics(
 source_id TEXT NOT NULL, category TEXT NOT NULL, count INTEGER NOT NULL,
 PRIMARY KEY(source_id,category));
PRAGMA user_version=1;
COMMIT;
"""


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA journal_mode=WAL')
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version == 0:
        try:
            db.executescript(SCHEMA)
        except Exception:
            db.close()
            raise
    elif version != 1:
        db.close()
        raise ValueError('unsupported database version')
    return db
