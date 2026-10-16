import json
import tempfile
from pathlib import Path

TS = '2026-10-14T12:00:00Z'


def temporary_directory():
    root=Path(__file__).resolve().parents[1]/'.local/tests'
    root.mkdir(parents=True,exist_ok=True)
    return tempfile.TemporaryDirectory(dir=root)


def event(kind, payload, ts=TS):
    return {'timestamp':ts,'type':kind,'payload':payload}


def usage(i=100,c=60,o=20,r=5):
    return {'input_tokens':i,'cached_input_tokens':c,'cache_write_input_tokens':0,
            'output_tokens':o,'reasoning_output_tokens':r,'total_tokens':i+o}


def records(sid='thread-a', root=None, parent=None, response='resp-a'):
    root = root or sid
    return [
        event('session_meta',{'id':sid,'session_id':root,'parent_thread_id':parent,
              'source':{'subagent':{'other':'guardian'}} if parent else 'vscode',
              'cli_version':'0.162.0-alpha.17.2','cwd':'C:/private/project'}),
        event('event_msg',{'type':'task_started','turn_id':'turn-a','root_turn_id':'root-turn',
              'turn_attribution':{'parent_turn_id':'parent-turn' if parent else None,'turn_trigger':'composer'}}),
        event('turn_context',{'turn_id':'turn-a','model':'gpt-6-astra','effort':'medium'}),
        event('token_usage_record',{'response_id':response,'thread_id':sid,'session_id':root,
              'turn_id':'turn-a','root_turn_id':'root-turn','usage':usage(),
              'turn_token_usage':usage(),'thread_token_usage':usage()}),
        event('event_msg',{'type':'token_count','info':{'total_token_usage':usage(),'last_token_usage':usage()}}),
        event('event_msg',{'type':'task_complete','turn_id':'turn-a'})]


def write(path, data, mode='w'):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open(mode,encoding='utf-8',newline='\n') as f:
        for r in data:
            f.write(json.dumps(r)+'\n')
