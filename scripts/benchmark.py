import json
from pathlib import Path
import time
import tracemalloc
from observatory.db import connect
from observatory.ingest import scan
from observatory.service import aggregate
from observatory.analytics import snapshot
from tests.helpers import records,write,temporary_directory,event


def main():
    with temporary_directory() as folder:
        root=Path(folder)
        for n in range(250):
            sid=f'synthetic-{n}';data=records(sid,response=f'{n}-0')[:4]
            data += [records(sid,response=f'{n}-{i}')[3] for i in range(1,40)]
            data += [event('response_item',{'text':'x'*100000})]
            write(root/f'sessions/{n}.jsonl',data)
        write(root/'sessions/large.jsonl',[event('response_item',{'text':'x'*20000000})])
        db=connect(root/'db.sqlite');tracemalloc.start();start=time.perf_counter()
        first=scan(db,root);elapsed=time.perf_counter()-start
        _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        start=time.perf_counter();second=scan(db,root);warm=time.perf_counter()-start
        write(root/'sessions/0.jsonl',[records('synthetic-0',response='append')[3]],'a')
        start=time.perf_counter();append=scan(db,root);incremental=time.perf_counter()-start
        start=time.perf_counter();total=aggregate(db);query=time.perf_counter()-start
        start=time.perf_counter();product=snapshot(db,{});product_seconds=time.perf_counter()-start
        product_bytes=len(json.dumps(product).encode())
        assert second['bytes']==0 and second['lines']==0
        assert append['lines']==1 and total['request_count']==10001
        db.close()
        result={'sessions':250,'responses':10001,'source_bytes':first['bytes'],
                'cold_seconds':round(elapsed,3),'warm_seconds':round(warm,3),'warm_parsed_bytes':second['bytes'],
                'append_seconds':round(incremental,3),'append_parsed_lines':append['lines'],
                'aggregate_seconds':round(query,4),'product_analytics_seconds':round(product_seconds,4),
                'product_payload_bytes':product_bytes,'python_peak_mib':round(peak/1024/1024,2)}
        Path('docs/performance.md').write_text('# Performance sanity check\n\nPython 3.13.1, Windows, 2026-10-16. Synthetic, content-free fixtures.\n\n```json\n'+json.dumps(result,indent=2)+'\n```\n\nCold scan includes tracemalloc overhead. Memory is traced Python allocations, not total process RSS or SQLite cache. '
            'Includes a 20 MB oversized line and 250 100 KB content lines. Warm scan stats files without parsing unchanged sources. '
            'Append scan reads one new record plus a 4 KB checkpoint anchor. Discovery is O(files) every two seconds; no archive contents are rescanned. '
            'Timestamp/model/task/root indexes support filtered queries; whole-history sums necessarily scan stored response rows. '
            'Reproduce with `python -m scripts.benchmark`.\n',encoding='utf-8')
        print(json.dumps(result,indent=2))


if __name__=='__main__':main()
