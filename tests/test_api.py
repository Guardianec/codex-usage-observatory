import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from observatory.api import Server
from observatory.db import connect
from tests.helpers import records, write, temporary_directory


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=temporary_directory();self.root=Path(self.tmp.name)
        self.db=self.root/'db.sqlite';connect(self.db).close()
        self.server=Server(self.db,self.root,port=0,interval=1)
        self.server.start_collector()
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()

    def get(self,path,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_address[1],timeout=5)
        conn.request('GET',path,headers=headers or {})
        r=conn.getresponse();value=json.loads(r.read());conn.close();return r.status,value

    def wait_count(self,n):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if self.get('/api/usage')[1]['request_count']==n:return
            time.sleep(.05)
        self.fail('collector did not observe append')

    def test_live_aggregates_and_metadata(self):
        path=self.root/'sessions/a.jsonl';write(path,records());self.wait_count(1)
        self.assertEqual(self.get('/api/usage?session_id=thread-a&task_id=turn-a')[1]['total_tokens'],120)
        for endpoint in ('health','sessions','tasks','current','models','projects'):
            self.assertEqual(self.get('/api/'+endpoint)[0],200)
        write(path,[records(response='next')[3]],'a');self.wait_count(2)

    def test_security_and_invalid_queries(self):
        self.assertEqual(self.get('/api/usage',{'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.get('/api/usage',{'Host':'evil.example'})[0],403)
        self.assertEqual(self.get('/api/usage?start=bad')[0],400)
        self.assertEqual(self.get('/api/usage?model=a&model=b')[0],400)
        self.assertEqual(self.get('/api/usage?unexpected=x')[0],400)
        self.assertEqual(self.get('/missing')[0],404)

    def test_sse_initial_and_live_invalidation(self):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_address[1],timeout=5)
        conn.request('GET','/api/events');r=conn.getresponse()
        self.assertEqual(r.status,200);self.assertEqual(r.readline(),b'event: invalidate\n')
        r.readline();r.readline()
        write(self.root/'sessions/new.jsonl',records())
        for _ in range(12):
            line=r.readline()
            if line==b'event: invalidate\n':break
        else:self.fail('no live invalidation')
        conn.close()
