import unittest
from pathlib import Path
from observatory.db import connect
from observatory.ingest import scan
from observatory import analytics,settings
from tests.helpers import records,write,temporary_directory,usage


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=temporary_directory();self.root=Path(self.tmp.name);self.db=connect(self.root/'db.sqlite')
        data=records();second=records('child',root='thread-a',parent='thread-a',response='child-r')
        second[2]['payload']['model']='another-model';second[3]['payload']['usage']=usage(200,100,40,10)
        write(self.root/'sessions/a.jsonl',data);write(self.root/'sessions/b.jsonl',second);scan(self.db,self.root)
    def tearDown(self):self.db.close();self.tmp.cleanup()

    def test_snapshot_matches_authoritative_aggregate(self):
        from observatory.service import aggregate
        snap=analytics.snapshot(self.db,{})
        self.assertEqual(snap['summary']['total_tokens'],aggregate(self.db)['total_tokens'])
        self.assertEqual(snap['summary']['median_tokens'],180)
        self.assertEqual(sum(r['total_tokens'] for r in snap['models']),360)
        self.assertEqual(sum(r['total_tokens'] for r in snap['daily']),360)
        self.assertEqual(snap['projects'][0]['top_model'],'another-model')
        self.assertIsNone(snap['cost']['amount'])

    def test_filters_sort_pagination(self):
        result=analytics.page_tasks(self.db,{},sort='total_tokens',limit=1)
        self.assertEqual(result['total'],2);self.assertEqual(result['items'][0]['total_tokens'],240)
        self.assertEqual(analytics.snapshot(self.db,{'model':'gpt-6-astra'})['summary']['total_tokens'],120)
        self.assertEqual(analytics.page_tasks(self.db,{'search':'child'})['total'],1)
        self.assertEqual(analytics.snapshot(self.db,{'end':'2026-10-14T12:00:00Z'})['summary']['total_tokens'],0)
        with self.assertRaises(ValueError):analytics.page_tasks(self.db,{},sort='DROP TABLE')
        # A later context must not relabel the effort of an earlier filtered contribution.
        context=records()[2];context['payload']['effort']='low'
        write(self.root/'sessions/a.jsonl',[context,records(response='later-request')[3]],'a');scan(self.db,self.root)
        filtered=analytics.task_rows(self.db,{'effort':'medium','session_id':'thread-a'})
        self.assertEqual(filtered[0]['efforts'],'medium')
        self.assertEqual(filtered[0]['total_tokens'],120)

    def test_timeline_requests_and_roots(self):
        self.assertEqual(analytics.timeline(self.db,{'root_session_id':'thread-a'})['items'][-1]['cumulative_tokens'],360)
        r=analytics.requests(self.db,{'session_id':'child'},limit=1)
        self.assertEqual(r['items'][0]['uncached_input_tokens'],100)
        self.assertEqual(len(analytics.session_rows(self.db,{})),2)

    def test_unknown_model(self):
        self.db.execute('UPDATE responses SET model=NULL');self.db.commit()
        result=analytics.snapshot(self.db,{'model':'__unknown__'})
        self.assertEqual(result['summary']['total_tokens'],360)
        self.assertEqual(result['models'][0]['key'],'Unknown model')

    def test_pricing_coverage_and_settings_validation(self):
        p={'model':'gpt-6-astra','effective_date':'2026-01-01','uncached_input_per_million':2,'cached_input_per_million':1,'output_per_million':10}
        cost=analytics.costs(self.db,{},[p]);self.assertEqual(cost['amount'],'0.00034');self.assertFalse(cost['complete'])
        self.assertEqual(cost['covered_requests'],1)
        path=self.root/'settings.json';settings.save(path,{'prices':[p]});self.assertEqual(settings.load(path)['prices'],[p])
        for bad in ({'threshold_tokens':-1},{'prices':[p,p]},{'prices':[{**p,'output_per_million':'NaN'}]}):
            with self.assertRaises(ValueError):settings.save(path,bad)
        self.assertEqual(settings.load(path)['prices'],[p])
