"""Allowlist normalization for observed rollout-v1; content never leaves here."""
from hashlib import sha256
import ntpath
from .domain import Usage, identifier, timestamp

VERSION = 'rollout-v1'


def optional(value):
    return identifier(value) if value is not None else None


def adapt(record):
    if not isinstance(record, dict):
        raise ValueError('envelope required')
    kind = record.get('type')
    if kind not in ('session_meta', 'turn_context', 'token_usage_record', 'event_msg'):
        return None
    p = record.get('payload')
    if not isinstance(p, dict):
        raise ValueError('payload required')
    sub = p.get('type')
    if kind == 'event_msg' and sub not in ('task_started', 'task_complete', 'turn_aborted', 'token_count'):
        return None
    ts = timestamp(record.get('timestamp'))
    if kind == 'session_meta':
        cwd = p.get('cwd')
        project = None
        if isinstance(cwd, str) and 0 < len(cwd) <= 4096 and not any(ord(c)<32 for c in cwd):
            canonical = ntpath.normcase(ntpath.normpath(cwd))
            project = {'id': sha256(canonical.encode()).hexdigest(),
                       'name': ntpath.basename(canonical)[:128] or 'workspace'}
        source = p.get('source')
        return {'kind': 'session', 'id': identifier(p.get('id')),
                'root_session_id': optional(p.get('session_id')) or identifier(p.get('id')),
                'parent_thread_id': optional(p.get('parent_thread_id')),
                'agent_kind': 'subagent' if isinstance(source, dict) and 'subagent' in source else 'main',
                'version': optional(p.get('cli_version')), 'project': project, 'timestamp': ts}
    if kind == 'turn_context':
        return {'kind': 'context', 'turn_id': identifier(p.get('turn_id')),
                'model': optional(p.get('model')), 'effort': optional(p.get('effort')), 'timestamp': ts}
    if kind == 'token_usage_record':
        return {'kind': 'usage', 'id': identifier(p.get('response_id')),
                'thread_id': identifier(p.get('thread_id')),
                'root_session_id': identifier(p.get('session_id')),
                'turn_id': identifier(p.get('turn_id')),
                'root_turn_id': optional(p.get('root_turn_id')), 'timestamp': ts,
                'usage': Usage.parse(p.get('usage')).metrics()}
    if sub == 'token_count':
        return {'kind': 'summary_ignored', 'has_usage': isinstance(p.get('info'), dict)}
    attr = p.get('turn_attribution') or {}
    if not isinstance(attr, dict):
        raise ValueError('invalid attribution')
    return {'kind': 'task', 'turn_id': identifier(p.get('turn_id')),
            'root_turn_id': optional(p.get('root_turn_id') or attr.get('root_turn_id')),
            'parent_turn_id': optional(attr.get('parent_turn_id')),
            'trigger': optional(attr.get('turn_trigger')), 'timestamp': ts,
            'status': 'running' if sub == 'task_started' else
                      'aborted' if sub == 'turn_aborted' else 'failed' if p.get('error') else 'completed'}
