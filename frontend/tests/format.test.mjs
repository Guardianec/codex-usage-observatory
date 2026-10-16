import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compact,exact,duration,percent,dateRange,warning} from '../src/format.mjs';
test('numbers retain useful precision and unavailable values',()=>{
  assert.equal(compact(1842391),'1.84M');assert.equal(exact(1842391),'1,842,391');assert.equal(percent(.918),'91.8%');assert.equal(compact(null),'—');
});
test('durations handle unknown and stable minute boundaries',()=>{
  assert.equal(duration(1122),'18m 42s');assert.equal(duration(null),'—');assert.equal(duration(3605),'1h 0m');
});
test('date range all-time, local calendar days and invalid custom',()=>{
  assert.deepEqual(dateRange('all'),{});assert.equal(dateRange('custom','2026-10-16','2026-10-15').invalid,true);
  const range=dateRange('7','','',new Date('2026-10-16T12:00:00'));assert.ok(Date.parse(range.end)>Date.parse(range.start));
  const custom=dateRange('custom','2026-10-14','2026-10-14');assert.ok(Date.parse(custom.end)>Date.parse(custom.start));
});
test('warnings use explicit thresholds with explainable reasons',()=>{
  const settings={threshold_tokens:100,threshold_requests:20,threshold_minutes:60,threshold_multiple:3};
  assert.equal(warning({total_tokens:250,request_count:1},settings,null,1).level,'High');
  assert.equal(warning({total_tokens:300,request_count:1},settings,null,1).level,'Critical');
  assert.equal(warning({total_tokens:10,request_count:1},settings,100,1).level,'Normal');
});
