"""Stable query interface; no raw paths, prompts, or source payloads."""
from .domain import Usage, timestamp


def rows(db, sql, args=()):
    return [dict(r) for r in db.execute(sql,args)]


def aggregate(db, *, session_id=None, task_id=None, root_session_id=None,
              model=None, project_id=None, start=None, end=None):
    clauses, params = [], []
    for col,value in [('r.session_id',session_id),('r.task_id',task_id),
                      ('r.root_session_id',root_session_id),('r.model',model),('s.project_id',project_id)]:
        if value is not None:
            clauses.append(col+'=?');params.append(value)
    for op,value in [('>=',start),('<',end)]:
        if value is not None:
            clauses.append('r.timestamp'+op+'?');params.append(timestamp(value))
    if start and end and timestamp(start)>=timestamp(end):
        raise ValueError('start must precede end')
    where = ' WHERE '+' AND '.join(clauses) if clauses else ''
    result = db.execute('SELECT count(*) AS n,coalesce(sum(input_tokens),0) AS i,'
                        'coalesce(sum(cached_input_tokens),0) AS c,coalesce(sum(output_tokens),0) AS o,'
                        'coalesce(sum(reasoning_output_tokens),0) AS r FROM responses r '
                        'JOIN sessions s ON s.id=r.session_id'+where, params).fetchone()
    return {**Usage(result['i'],result['c'],result['o'],result['r']).metrics(),
            'request_count':result['n'], 'coverage':'recorded_responses_only'}


def sessions(db):
    return rows(db, 'SELECT s.*,count(r.id) AS recorded_responses FROM sessions s LEFT JOIN responses r '
                'ON r.session_id=s.id GROUP BY s.id ORDER BY s.started_at DESC')


def tasks(db, limit=100, current=False):
    return rows(db,"SELECT * FROM tasks "+("WHERE status='running' " if current else '')+
                'ORDER BY started_at DESC,session_id,id LIMIT ?', (min(max(limit,1),1000),))


def health(db):
    diagnostics = rows(db,'SELECT category,sum(count) AS count FROM diagnostics GROUP BY category')
    concerns = {'unsupported','malformed','oversized','conflicting_response','unreadable',
                'source_rewritten','unsupported_missing_session'}
    return {'schema_version':db.execute('PRAGMA user_version').fetchone()[0],
            'adapter':'rollout-v1', 'responses':db.execute('SELECT count(*) FROM responses').fetchone()[0],
            'sources':db.execute('SELECT count(*) FROM checkpoints').fetchone()[0],
            'quality':'review_diagnostics' if any(d['category'] in concerns for d in diagnostics) else 'observed_schema',
            'diagnostics':diagnostics}
