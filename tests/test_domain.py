import unittest
from observatory.domain import Usage, cumulative_delta, estimate_cost, timestamp
from observatory.adapter import adapt
from tests.helpers import usage, event, records


class DomainTests(unittest.TestCase):
    def test_subsets_and_total(self):
        self.assertEqual(Usage.parse(usage()).metrics(),dict(input_tokens=100,cached_input_tokens=60,
            uncached_input_tokens=40,output_tokens=20,reasoning_output_tokens=5,total_tokens=120))

    def test_zero(self):
        self.assertEqual(Usage.parse(usage(0,0,0,0)).total_tokens,0)

    def test_invalid_values(self):
        for key,value in [('input_tokens',True),('cached_input_tokens',101),('output_tokens',-1),
                          ('reasoning_output_tokens',21),('total_tokens',121),
                          ('input_tokens',1.5),('cache_write_input_tokens',1),('input_tokens',10**13)]:
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                Usage.parse({**usage(),key:value})

    def test_missing_counter_is_unknown(self):
        u=usage();del u['reasoning_output_tokens']
        with self.assertRaises(ValueError): Usage.parse(u)

    def test_cumulative_delta(self):
        self.assertEqual(cumulative_delta(usage(200,120,40,10),usage()).metrics(),Usage.parse(usage()).metrics())
        with self.assertRaises(ValueError): cumulative_delta(usage(),usage(200,120,40,10))

    def test_time(self):
        self.assertEqual(timestamp('2026-10-14T15:00:00+03:00'),'2026-10-14T12:00:00.000Z')
        for value in ('2026-10-14','bad',None):
            with self.assertRaises(ValueError):timestamp(value)

    def test_price(self):
        p={'model':'gpt-6-astra','effective_date':'2026-01-01','uncached_input_per_million':'2',
           'cached_input_per_million':'0.2','output_per_million':'10'}
        self.assertEqual(estimate_cost(Usage.parse(usage()),p['model'],'2026-10-14T00:00:00Z',[p])['amount'],'0.000292')
        self.assertIsNone(estimate_cost(Usage.parse(usage()),'unknown','2026-10-14T00:00:00Z',[p]))
        self.assertIsNone(estimate_cost(Usage.parse(usage()),p['model'],'2025-01-01T00:00:00Z',[p]))
        with self.assertRaises(ValueError):
            estimate_cost(Usage.parse(usage()),p['model'],'2026-10-14T00:00:00Z',[{**p,'output_per_million':'NaN'}])

    def test_unknown_and_private_content(self):
        self.assertIsNone(adapt(event('response_item',{'text':'PRIVATE'})))
        self.assertIsNone(adapt(event('future',{})))
        normalized=adapt(records()[0])
        self.assertNotIn('private',str(normalized))
        self.assertEqual(normalized['project']['name'],'project')

    def test_model_effort(self):
        r=adapt(records()[2]);self.assertEqual((r['model'],r['effort']),('gpt-6-astra','medium'))

    def test_malformed_envelopes(self):
        for r in ([],event('token_usage_record',[]),event('turn_context',{'turn_id':'a\n'})):
            with self.assertRaises(ValueError):adapt(r)
