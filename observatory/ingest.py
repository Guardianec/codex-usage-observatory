"""Streaming append reader. Transactions commit rows and checkpoints together."""
import hashlib
import json
import logging
from pathlib import Path
from .adapter import adapt, VERSION

LOG = logging.getLogger(__name__)
MAX_LINE = 8 * 1024 * 1024


def diagnostic(db, path, category):
    source = hashlib.sha256(str(path).encode()).hexdigest()[:16]
    db.execute('INSERT INTO diagnostics VALUES(?,?,1) ON CONFLICT(source_id,category) '
               'DO UPDATE SET count=count+1', (source, category))
    LOG.debug('source=%s category=%s', source, category)


def ensure_session(db, sid, root, ts):
    db.execute('INSERT OR IGNORE INTO sessions(id,root_session_id,started_at,last_seen) VALUES(?,?,?,?)',
               (sid, root, ts, ts))
    db.execute('UPDATE sessions SET last_seen=max(coalesce(last_seen,?),?) WHERE id=?', (ts, ts, sid))


def ensure_task(db, sid, tid):
    db.execute('INSERT OR IGNORE INTO tasks(session_id,id) VALUES(?,?)', (sid, tid))


def consume(db, event, state):
    kind = event['kind']
    if kind == 'session':
        sid = event['id']
        state['session_id'] = sid
        ensure_session(db, sid, event['root_session_id'], event['timestamp'])
        project = event['project']
        if project:
            db.execute('INSERT OR IGNORE INTO projects VALUES(?,?)', (project['id'], project['name']))
        db.execute('UPDATE sessions SET root_session_id=?,parent_thread_id=?,agent_kind=?,project_id=?,version=? WHERE id=?',
                   (event['root_session_id'], event['parent_thread_id'], event['agent_kind'],
                    project['id'] if project else None, event['version'], sid))
        return 'parsed'
    if kind == 'usage':
        sid, tid = event['thread_id'], event['turn_id']
        ensure_session(db, sid, event['root_session_id'], event['timestamp'])
        ensure_task(db, sid, tid)
        db.execute('UPDATE tasks SET root_turn_id=coalesce(root_turn_id,?) WHERE session_id=? AND id=?',
                   (event['root_turn_id'], sid, tid))
        ctx = db.execute('SELECT model,effort FROM tasks WHERE session_id=? AND id=?', (sid,tid)).fetchone()
        u = event['usage']
        row = (event['id'],sid,tid,event['root_session_id'],event['root_turn_id'],event['timestamp'],
               ctx['model'],ctx['effort'],u['input_tokens'],u['cached_input_tokens'],
               u['output_tokens'],u['reasoning_output_tokens'])
        old = db.execute('SELECT * FROM responses WHERE id=?', (event['id'],)).fetchone()
        if old:
            # Transport timestamps/context can differ on replay. Ownership and tokens cannot.
            relevant = (1,2,3,4,8,9,10,11)
            if not all(old[i] == row[i] for i in relevant):
                return 'conflicting_response'
            db.execute('UPDATE responses SET model=coalesce(model,?),effort=coalesce(effort,?) WHERE id=?',
                       (ctx['model'],ctx['effort'],event['id']))
            return 'deduplicated'
        db.execute('INSERT INTO responses VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', row)
        return 'parsed'
    sid = state.get('session_id')
    if not sid:
        return 'unsupported_missing_session'
    if kind == 'summary_ignored':
        if event['has_usage']:
            db.execute('UPDATE sessions SET summary_events=summary_events+1 WHERE id=?', (sid,))
        return 'summary_ignored'
    tid = event['turn_id']
    ensure_task(db, sid, tid)
    if kind == 'context':
        db.execute('UPDATE tasks SET model=?,effort=? WHERE session_id=? AND id=?',
                   (event['model'],event['effort'],sid,tid))
    elif kind == 'task':
        status = event['status']
        if status == 'running':
            db.execute("UPDATE tasks SET started_at=coalesce(started_at,?),root_turn_id=coalesce(?,root_turn_id),"
                       "parent_turn_id=coalesce(?,parent_turn_id),trigger=coalesce(?,trigger),"
                       "status=CASE WHEN ended_at IS NULL THEN 'running' ELSE status END WHERE session_id=? AND id=?",
                       (event['timestamp'],event['root_turn_id'],event['parent_turn_id'],event['trigger'],sid,tid))
        else:
            db.execute('UPDATE tasks SET ended_at=?,status=? WHERE session_id=? AND id=?',
                       (event['timestamp'],status,sid,tid))
    return 'parsed'


def anchor(stream, offset):
    stream.seek(max(0,offset-4096))
    return hashlib.sha256(stream.read(min(offset,4096))).hexdigest()


def import_file(db, path):
    path = Path(path)
    if path.is_symlink():
        return {'lines': 0, 'bytes': 0}
    path = path.resolve()
    stat = path.stat()
    cp = db.execute('SELECT * FROM checkpoints WHERE path=?',(str(path),)).fetchone()
    if cp and cp['size'] == stat.st_size and cp['mtime_ns'] == stat.st_mtime_ns:
        return {'lines':0,'bytes':0}
    offset = cp['offset'] if cp else 0
    state = json.loads(cp['state']) if cp else {}
    lines = 0
    with path.open('rb') as stream, db:
        if cp and (cp['adapter'] != VERSION or stat.st_size < offset or anchor(stream,offset) != cp['anchor']):
            # Re-read changed files; global response IDs retain existing historical evidence.
            offset, state = 0, {}
            diagnostic(db,path,'source_rewritten')
        start = offset
        stream.seek(offset)
        while True:
            raw = stream.readline(MAX_LINE+1)
            if not raw:
                break
            oversized = len(raw)>MAX_LINE
            if oversized:
                while raw and not raw.endswith(b'\n'):
                    raw = stream.readline(MAX_LINE+1)
            if not raw.endswith(b'\n'):
                break  # Retry the entire incomplete trailing line on the next pass.
            offset = stream.tell()
            lines += 1
            if oversized:
                diagnostic(db,path,'oversized')
                continue
            try:
                record = json.loads(raw)
            except (ValueError, UnicodeDecodeError, RecursionError):
                diagnostic(db,path,'malformed')
                continue
            try:
                event = adapt(record)
            except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
                diagnostic(db,path,'unsupported')
                continue
            category = consume(db,event,state) if event else 'ignored'
            diagnostic(db,path,category)
        mark = anchor(stream,offset)
        db.execute('INSERT INTO checkpoints VALUES(?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET '
                   'offset=excluded.offset,size=excluded.size,mtime_ns=excluded.mtime_ns,anchor=excluded.anchor,'
                   'state=excluded.state,adapter=excluded.adapter',
                   (str(path),offset,stat.st_size,stat.st_mtime_ns,mark,json.dumps(state),VERSION))
    return {'lines':lines,'bytes':offset-start}


def scan(db, codex_home):
    result = {'files':0,'lines':0,'bytes':0,'errors':0}
    for folder in ('sessions','archived_sessions'):
        root = Path(codex_home)/folder
        for path in sorted(root.rglob('*.jsonl')):
            if path.is_symlink():
                continue
            try:
                counts = import_file(db,path)
            except (OSError,):
                with db:
                    diagnostic(db,path,'unreadable')
                result['errors'] += 1
                continue
            result['files'] += 1
            for key in ('lines','bytes'):
                result[key] += counts[key]
    return result
