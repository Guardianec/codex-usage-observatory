"""Test-only fixture server. Production never generates sample usage."""
from datetime import datetime,timezone,timedelta
from pathlib import Path
from uuid import uuid4
from observatory.api import Server
from observatory.db import connect
from observatory.ingest import scan
from tests.helpers import records,usage,write

root=Path('.local/e2e');root.mkdir(parents=True,exist_ok=True)
dbpath=root/'runs'/uuid4().hex/'observatory.sqlite'
# Each run uses stable IDs and deterministic fixture updates in its private test DB.
db=connect(dbpath)
for n in range(32):
    data=records('qa-thread-'+str(n),response='qa-response-'+str(n))
    moment=datetime.now(timezone.utc)-timedelta(days=n%7,minutes=40+n)
    data[0]['payload']['cwd']='C:/sanitized/engine' if n%2 else 'C:/sanitized/observatory'
    data[2]['payload']['model']='fixture-model-a' if n%2 else 'fixture-model-b'
    data[2]['payload']['effort']='high' if n%2 else 'medium'
    data[3]['payload']['usage']=usage(10000*(n+1),5000*(n+1),200*(n+1),50*(n+1))
    for r in data:r['timestamp']=moment.isoformat().replace('+00:00','Z')
    data[-1]['timestamp']=(moment+timedelta(minutes=10)).isoformat().replace('+00:00','Z')
    if n==0:data=data[:-1]
    write(root/f'sessions/{n}.jsonl',data)
scan(db,root);db.close()
server=Server(dbpath,root,port=8877,interval=1);server.start_collector()
try:server.serve_forever()
finally:server.server_close()
