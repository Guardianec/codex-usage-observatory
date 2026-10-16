import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from observatory.db import connect
from observatory.ingest import scan, import_file
from observatory.service import aggregate, tasks, sessions
from tests.helpers import records, write, event, usage, temporary_directory


class IngestTests(unittest.TestCase):
    def setUp(self):
        self.tmp=temporary_directory();self.root=Path(self.tmp.name)
        self.path=self.root/'sessions/one.jsonl';self.dbpath=self.root/'db.sqlite'
        self.db=connect(self.dbpath)

    def tearDown(self):
        self.db.close();self.tmp.cleanup()

    def test_history_repeat_restart(self):
        write(self.path,records());self.assertEqual(scan(self.db,self.root)['lines'],6)
        self.assertEqual(aggregate(self.db)['total_tokens'],120)
        self.assertEqual(scan(self.db,self.root)['bytes'],0)
        self.db.close();self.db=connect(self.dbpath)
        self.assertEqual(scan(self.db,self.root)['lines'],0)
        self.assertEqual(aggregate(self.db)['request_count'],1)

    def test_append_and_new_file(self):
        write(self.path,records());scan(self.db,self.root)
        write(self.path,[records(response='resp-b')[3]],'a')
        self.assertEqual(scan(self.db,self.root)['lines'],1)
        write(self.root/'archived_sessions/two.jsonl',records('thread-b',response='resp-c'))
        scan(self.db,self.root);self.assertEqual(aggregate(self.db)['request_count'],3)

    def test_partial_completion_and_corrupt_middle(self):
        write(self.path,records()[:3])
        raw=json.dumps(records()[3]).encode()
        with self.path.open('ab') as f:f.write(b'{bad}\n'+raw[:40])
        scan(self.db,self.root);self.assertEqual(aggregate(self.db)['request_count'],0)
        with self.path.open('ab') as f:f.write(raw[40:]+b'\n')
        scan(self.db,self.root);self.assertEqual(aggregate(self.db)['request_count'],1)
        self.assertEqual(self.db.execute("SELECT count FROM diagnostics WHERE category='malformed'").fetchone()[0],1)

    def test_duplicate_and_retry(self):
        write(self.path,records()+[records()[3],records(response='retry-new-id')[3]])
        scan(self.db,self.root);self.assertEqual(aggregate(self.db)['request_count'],2)

    def test_conflicting_response(self):
        changed=records()[3];changed['payload']['usage']=usage(200,60,20,5)
        write(self.path,records()+[changed]);scan(self.db,self.root)
        self.assertEqual(aggregate(self.db)['input_tokens'],100)
        self.assertEqual(self.db.execute("SELECT count FROM diagnostics WHERE category='conflicting_response'").fetchone()[0],1)

    def test_parent_child_and_inherited_replay(self):
        write(self.path,records())
        child=records('child',root='thread-a',parent='thread-a',response='child-response')
        write(self.root/'sessions/child.jsonl',child+[records()[3]])
        scan(self.db,self.root)
        self.assertEqual(aggregate(self.db,root_session_id='thread-a')['total_tokens'],240)
        self.assertEqual(aggregate(self.db,session_id='child')['total_tokens'],120)
        self.assertEqual(aggregate(self.db,session_id='thread-a')['total_tokens'],120)
        self.assertEqual(self.db.execute("SELECT parent_thread_id FROM sessions WHERE id='child'").fetchone()[0],'thread-a')

    def test_task_grouping_and_status(self):
        data=records();r=records(response='second-turn')[3];r['payload']['turn_id']='turn-b'
        write(self.path,data+[r]);scan(self.db,self.root)
        self.assertEqual(aggregate(self.db,session_id='thread-a',task_id='turn-a')['total_tokens'],120)
        self.assertEqual({t['status'] for t in tasks(self.db)},{'unknown','completed'})

    def test_running_and_failed(self):
        data=records()[:4];write(self.path,data);scan(self.db,self.root)
        self.assertEqual(len(tasks(self.db,current=True)),1)
        write(self.path,[event('event_msg',{'type':'task_complete','turn_id':'turn-a','error':{'message':'PRIVATE'}})],'a')
        scan(self.db,self.root);self.assertEqual(tasks(self.db)[0]['status'],'failed')

    def test_model_change(self):
        ctx=records()[2];ctx['payload']['model']='gpt-6.1-sol'
        write(self.path,records()[:4]+[ctx,records(response='b')[3]])
        scan(self.db,self.root)
        self.assertEqual(aggregate(self.db,model='gpt-6.1-sol')['request_count'],1)

    def test_summary_only_not_fake_zero_coverage(self):
        data=records();write(self.path,[data[0],data[4]])
        scan(self.db,self.root)
        self.assertEqual(sessions(self.db)[0]['summary_events'],1)
        self.assertEqual(sessions(self.db)[0]['recorded_responses'],0)

    def test_rewrite_and_replay_do_not_erase_history(self):
        write(self.path,records());scan(self.db,self.root)
        write(self.path,records(response='new'));scan(self.db,self.root)
        self.assertEqual(aggregate(self.db)['request_count'],2)

    def test_transaction_rolls_back_checkpoint(self):
        write(self.path,records())
        from observatory.ingest import consume
        calls=0
        def fail_late(db,event,state):
            nonlocal calls
            calls+=1
            if calls==5:raise RuntimeError('crash')
            return consume(db,event,state)
        with patch('observatory.ingest.consume',side_effect=fail_late):
            with self.assertRaises(RuntimeError):scan(self.db,self.root)
        self.assertEqual(self.db.execute('SELECT count(*) FROM checkpoints').fetchone()[0],0)
        self.assertEqual(aggregate(self.db)['request_count'],0)
        scan(self.db,self.root);self.assertEqual(aggregate(self.db)['request_count'],1)

    def test_dates_and_indexes(self):
        write(self.path,records());scan(self.db,self.root)
        self.assertEqual(aggregate(self.db,start='2026-10-14T12:00:00Z',end='2026-10-14T12:00:01Z')['request_count'],1)
        self.assertEqual(aggregate(self.db,end='2026-10-14T12:00:00Z')['request_count'],0)
        plan=str([tuple(r) for r in self.db.execute("EXPLAIN QUERY PLAN SELECT * FROM responses WHERE timestamp>=?",('a',))])
        self.assertIn('responses_time',plan)

    def test_oversized_bounded_reader(self):
        write(self.path,records()[:3])
        with self.path.open('ab') as f:f.write(b'x'*500+b'\n')
        write(self.path,[records()[3]],'a')
        with patch('observatory.ingest.MAX_LINE',400):scan(self.db,self.root)
        self.assertEqual(self.db.execute("SELECT count FROM diagnostics WHERE category='oversized'").fetchone()[0],2)

    def test_invalid_json_and_unicode(self):
        write(self.path,records()[:3])
        with self.path.open('ab') as f:f.write(b'[]\n\xff\n')
        write(self.path,[records()[3]],'a');scan(self.db,self.root)
        self.assertEqual(aggregate(self.db)['request_count'],1)

    def test_db_constraints(self):
        import sqlite3
        write(self.path,records());scan(self.db,self.root)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('UPDATE responses SET cached_input_tokens=input_tokens+1')

    def test_copy_in_another_file(self):
        write(self.path,records());write(self.root/'archived_sessions/copy.jsonl',records())
        scan(self.db,self.root);self.assertEqual(aggregate(self.db)['request_count'],1)

    def test_missing_context_stays_unknown_then_replay_enriches(self):
        data=records();write(self.path,[data[0],data[3]]);scan(self.db,self.root)
        self.assertIsNone(self.db.execute('SELECT model FROM responses').fetchone()[0])
        write(self.path,[data[2],data[3]],'a');scan(self.db,self.root)
        self.assertEqual(self.db.execute('SELECT model FROM responses').fetchone()[0],'gpt-6-astra')

    def test_abort(self):
        write(self.path,records()[:4]+[event('event_msg',{'type':'turn_aborted','turn_id':'turn-a'})])
        scan(self.db,self.root);self.assertEqual(tasks(self.db)[0]['status'],'aborted')

    def test_synthetic_numeric_fixture(self):
        fixture=Path(__file__).parent/'fixtures/observed.jsonl'
        self.path.parent.mkdir(parents=True,exist_ok=True);self.path.write_bytes(fixture.read_bytes())
        scan(self.db,self.root)
        self.assertEqual(aggregate(self.db)['total_tokens'],6600)
        self.assertEqual(aggregate(self.db)['uncached_input_tokens'],1800)
        self.assertEqual(aggregate(self.db)['reasoning_output_tokens'],170)
