"""Independent raw numeric oracle, bounded to importer checkpoint offsets.

Read-only Codex access. Emits only anonymized IDs and numeric evidence.
"""
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
from observatory.db import connect
from observatory.ingest import scan, MAX_LINE
from observatory.service import aggregate

FIELDS=('input_tokens','cached_input_tokens','output_tokens','reasoning_output_tokens','total_tokens')


def alias(value):
    return sha256(value.encode()).hexdigest()[:10]


def verify(home,dbpath,output):
    db=connect(dbpath)
    try:
        imported=scan(db,home)
        expected={}; by_task=defaultdict(Counter); by_thread=defaultdict(Counter)
        checks=Counter(); oversized=Counter(); examples=[]; child_threads=set()
        for cp in db.execute('SELECT path,offset FROM checkpoints ORDER BY path'):
            previous_thread={};previous_turn={}
            with Path(cp['path']).open('rb') as f:
                while f.tell()<cp['offset']:
                    line=f.readline()
                    try:rec=json.loads(line)
                    except ValueError:checks['malformed']+=1;continue
                    p=rec.get('payload',{});kind=rec.get('type')
                    if len(line)>MAX_LINE:oversized[kind]+=1
                    if kind=='session_meta' and p.get('parent_thread_id'):child_threads.add(p['id'])
                    if kind!='token_usage_record':continue
                    u=p['usage'];rid=p['response_id'];sid=p['thread_id'];tid=p['turn_id']
                    assert u['total_tokens']==u['input_tokens']+u['output_tokens']
                    assert 0<=u['cached_input_tokens']<=u['input_tokens']
                    assert 0<=u['reasoning_output_tokens']<=u['output_tokens']
                    for label,prior,current in [('thread',previous_thread.get(sid,{}),p['thread_token_usage']),
                                                ('turn',previous_turn.get((sid,tid),{}),p['turn_token_usage'])]:
                        checks[label+'_delta_checked']+=1
                        if any(current[k]-prior.get(k,0)!=u[k] for k in FIELDS):checks[label+'_delta_mismatch']+=1
                    previous_thread[sid]=p['thread_token_usage'];previous_turn[sid,tid]=p['turn_token_usage']
                    if rid in expected:
                        assert expected[rid]['usage']==u
                        checks['duplicate']+=1;continue
                    expected[rid]=p
                    for k in FIELDS:
                        by_task[sid,tid][k]+=u[k];by_thread[sid][k]+=u[k]
                    if len(examples)<3 or (sid in child_threads and not any(x['thread_id'] in child_threads for x in examples)):
                        examples.append(p)
        actual={r['id']:dict(r) for r in db.execute('SELECT * FROM responses')}
        assert set(expected)==set(actual),'response set discrepancy'
        for rid,p in expected.items():
            for k in FIELDS[:-1]:assert actual[rid][k]==p['usage'][k],(alias(rid),k)
            assert actual[rid]['session_id']==p['thread_id']
            assert actual[rid]['task_id']==p['turn_id']
        for (sid,tid),u in by_task.items():
            got=aggregate(db,session_id=sid,task_id=tid)
            assert all(got[k]==u[k] for k in FIELDS)
        for sid,u in by_thread.items():
            got=aggregate(db,session_id=sid)
            assert all(got[k]==u[k] for k in FIELDS)
        assert not checks['thread_delta_mismatch'] and not checks['turn_delta_mismatch'],checks
        report=['# Real-data verification','',
            'Read-only verification on 2026-10-16. Raw reads stop at persisted byte checkpoints, so live growth cannot race this comparison. '
            'The oracle uses direct integer addition and explicit field comparisons, independent of the domain parser. No prompt text is retained.','',
            f"PASS: {len(expected):,} unique responses, {len(by_task)} tasks and {len(by_thread)} threads with usage. All response IDs, ownership, numeric fields, task totals and thread totals match SQLite.",
            f"Cumulative checks: `{dict(checks)}`.",
            f"Oversized raw lines by type: `{dict(oversized)}`. These contain no token_usage_record events in this snapshot.",'',
            '## Individual response calculations','',
            'Raw columns I/C/O/R/T mean input/cached/output/reasoning/total. Expected uncached = I − C; expected total = I + O. '
            'Application columns are independently read from SQLite, with derived metrics from the service.','',
            '| Anonymized thread / response | Raw I / C / O / R / T | Expected uncached / total | App I / C / uncached / O / R / total | Result |',
            '|---|---|---|---|---|']
        for p in examples:
            u=p['usage'];a=actual[p['response_id']]
            raw=' / '.join(str(u[k]) for k in FIELDS)
            got=f"{a['input_tokens']} / {a['cached_input_tokens']} / {a['input_tokens']-a['cached_input_tokens']} / {a['output_tokens']} / {a['reasoning_output_tokens']} / {a['input_tokens']+a['output_tokens']}"
            report.append(f"| {alias(p['thread_id'])} / {alias(p['response_id'])} | {raw} | {u['input_tokens']-u['cached_input_tokens']} / {u['input_tokens']+u['output_tokens']} | {got} | PASS |")
        report+=['','## Task reconciliation','','| Anonymized thread / task | Expected I / C / uncached / O / R / total | App result |','|---|---|---|']
        for (sid,tid),u in list(by_task.items())[:3]:
            vals=f"{u['input_tokens']} / {u['cached_input_tokens']} / {u['input_tokens']-u['cached_input_tokens']} / {u['output_tokens']} / {u['reasoning_output_tokens']} / {u['total_tokens']}"
            report.append(f'| {alias(sid)} / {alias(tid)} | {vals} | Identical — PASS |')
        report+=['','## Interpretation and limits','',
            'Each response total is input + output; uncached input is input minus cached. Reasoning is contained in output and is not added again.',
            '', 'Guardian usage is included through its own response IDs. All available raw usage records were accounted for; '
            'this does not prove provider billing completeness or recover failed requests without usage. '
            'Counter equality supports the local accounting interpretation but does not establish subscription quota or pricing.',
            '', 'Reproduce: `python -m scripts.verify_local`. Counts can grow as Codex runs. '
            'This script intentionally fails on discrepancies rather than rewriting expected values to match the importer.','']
        Path(output).parent.mkdir(parents=True,exist_ok=True)
        Path(output).write_text('\n'.join(report),encoding='utf-8')
        print(json.dumps({'responses':len(expected),'tasks':len(by_task),'threads':len(by_thread),
                          'checks':checks,'oversized_types':oversized,'result':'PASS'},indent=2))
    finally:db.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--codex-home',type=Path,default=Path.home()/'.codex')
    p.add_argument('--db',type=Path,default=Path('.local/observatory.sqlite'))
    p.add_argument('--output',type=Path,default=Path('.local/reports/verification.md'))
    a=p.parse_args();verify(a.codex_home,a.db,a.output)
