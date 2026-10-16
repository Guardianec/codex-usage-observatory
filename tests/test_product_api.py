import http.client
import json
import unittest
from tests import test_api
from tests.helpers import records,write


class ProductApiTests(unittest.TestCase):
    # Additional HTTP contract tests reuse the isolated fixture lifecycle.
    setUp=test_api.ApiTests.setUp
    tearDown=test_api.ApiTests.tearDown
    get=test_api.ApiTests.get
    wait_count=test_api.ApiTests.wait_count
    def test_new_endpoints_and_export(self):
        write(self.root/'sessions/a.jsonl',records());self.wait_count(1)
        for endpoint in ('analytics','history','requests','timeline','session-history','task-detail?session_id=thread-a&task_id=turn-a'):
            self.assertEqual(self.get('/api/'+endpoint)[0],200,endpoint)
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_address[1],timeout=5)
        conn.request('GET','/api/export?kind=tasks');response=conn.getresponse()
        self.assertEqual(response.status,200);self.assertIn('uncached_input_tokens',response.read().decode('utf-8-sig'));conn.close()

    def test_settings_reject_cross_origin_and_invalid_rates(self):
        port=self.server.server_address[1]
        def post(value,origin):
            conn=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
            conn.request('POST','/api/settings',body=json.dumps(value),headers={'Content-Type':'application/json','Origin':origin})
            r=conn.getresponse();r.read();conn.close();return r.status
        self.assertEqual(post({'threshold_tokens':7},'https://foreign.example'),403)
        self.assertEqual(post({'threshold_tokens':-1},f'http://127.0.0.1:{port}'),400)
        self.assertEqual(post({'threshold_tokens':700},f'http://127.0.0.1:{port}'),200)
        self.assertEqual(self.get('/api/settings')[1]['threshold_tokens'],700)
