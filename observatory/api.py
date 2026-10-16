"""Read-only loopback HTTP API and SSE invalidations; frontend can use a same-origin proxy."""
import json
import threading
import csv
import io
import mimetypes
import sqlite3
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs, unquote
from . import service
from . import analytics, settings
from .db import connect
from .ingest import scan


class Server(ThreadingHTTPServer):
    daemon_threads = False

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(10)
        return connection, address

    def __init__(self, db_path, codex_home, port=8765, interval=2.0):
        self.db_path, self.codex_home = str(db_path), codex_home
        self.interval = max(1.0, interval)
        self.stop = threading.Event()
        self.collector_status = {'state':'starting'}
        self.settings_path=Path(db_path).parent/'settings.json'
        self.settings_lock=threading.Lock()
        self.frontend=Path(__file__).resolve().parents[1]/'frontend/dist'
        super().__init__(('127.0.0.1',port), Handler)

    def collect(self):
        db = connect(self.db_path)
        try:
            while not self.stop.is_set():
                try:
                    self.collector_status = {'state':'ready', **scan(db,self.codex_home)}
                except Exception:
                    self.collector_status = {'state':'error'}
                self.stop.wait(self.interval)
        finally:
            db.close()

    def start_collector(self):
        self.worker = threading.Thread(target=self.collect,daemon=True)
        self.worker.start()

    def server_close(self):
        self.stop.set()
        if hasattr(self,'worker'):
            self.worker.join(timeout=10)
        super().server_close()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Request paths can contain private IDs; no default HTTP access log.

    def reply(self, code, value):
        body = json.dumps(value,ensure_ascii=True).encode()
        self.send_response(code)
        self.send_header('Content-Type','application/json')
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        port = self.server.server_address[1]
        allowed = {f'127.0.0.1:{port}',f'localhost:{port}'}
        origin = self.headers.get('Origin')
        if self.headers.get('Host') not in allowed or (origin and origin not in {'http://'+h for h in allowed}):
            self.reply(403,{'error':'same-origin loopback requests only'})
            return
        if not urlsplit(self.path).path.startswith('/api/'):
            self.static();return
        db = None
        try:
            db = connect(self.server.db_path)
            url = urlsplit(self.path)
            query = parse_qs(url.query,strict_parsing=True)
            if any(len(v)!=1 for v in query.values()):
                raise ValueError('duplicate query')
            q = {k:v[0] for k,v in query.items()}
            preferences=settings.load(self.server.settings_path)
            if url.path == '/api/events':
                self.events(db)
                return
            if url.path == '/api/health':
                result = {**service.health(db),'collector':self.server.collector_status,
                          'source_available':(Path(self.server.codex_home)/'sessions').is_dir()}
            elif url.path == '/api/settings':
                result={**preferences,'runtime':{'codex_home':str(Path(self.server.codex_home).resolve()),
                    'database':str(Path(self.server.db_path).resolve()),'interval_seconds':self.server.interval,
                    'adapter':'rollout-v1','binding':'127.0.0.1'}}
            elif url.path == '/api/analytics':
                result=analytics.snapshot(db,q,preferences['prices'])
            elif url.path == '/api/history':
                controls={k:q.pop(k) for k in ('sort','direction','page','limit') if k in q}
                for k in ('page','limit'):
                    if k in controls:controls[k]=int(controls[k])
                result=analytics.page_tasks(db,q,**controls)
                for row in result['items']:
                    row['cost']=analytics.costs(db,{**q,'session_id':row['session_id'],'task_id':row['id']},preferences['prices'])
            elif url.path == '/api/requests':
                page=int(q.pop('page',1));limit=int(q.pop('limit',50))
                result=analytics.requests(db,q,page,limit)
            elif url.path == '/api/timeline':
                result=analytics.timeline(db,q)
            elif url.path == '/api/session-history':
                page=int(q.pop('page',1));limit=int(q.pop('limit',25))
                if page<1 or not 1<=limit<=100:raise ValueError('invalid page')
                data=analytics.session_rows(db,q)
                result={'items':data[(page-1)*limit:page*limit],'total':len(data),'page':page,'limit':limit}
            elif url.path == '/api/task-detail':
                if not q.get('session_id') or not q.get('task_id'):raise ValueError('task identity required')
                data=analytics.task_rows(db,q)
                if not data:self.reply(404,{'error':'task not found'});return
                item=data[0];all_tasks=analytics.task_rows(db,{})
                measured=[r for r in all_tasks if r['request_count'] and r['status']!='running']
                result={'task':item,'cost':analytics.costs(db,q,preferences['prices']),
                    'baselines':{'global':analytics.task_statistics(measured),
                        'project':analytics.task_statistics([r for r in measured if r['project_id']==item['project_id']]),
                        'model':analytics.task_statistics([r for r in measured if r['models']==item['models']])}}
            elif url.path == '/api/export':
                kind=q.pop('kind','tasks')
                if kind=='statistics':self.download('statistics.json',json.dumps(analytics.snapshot(db,q,preferences['prices']),indent=2).encode(),'application/json');return
                if kind not in {'tasks','daily'}:raise ValueError('invalid export')
                data=analytics.task_rows(db,q) if kind=='tasks' else [{**r,'date':r['key']} for r in analytics.response_groups(db,q,'substr(r.timestamp,1,10)')]
                if len(data)>50000:raise ValueError('narrow export range')
                columns=['session_id','id','project','model','effort','status','started_at','duration_seconds','request_count','input_tokens','cached_input_tokens','uncached_input_tokens','output_tokens','reasoning_output_tokens','total_tokens'] if kind=='tasks' else ['date','request_count','input_tokens','cached_input_tokens','uncached_input_tokens','output_tokens','reasoning_output_tokens','total_tokens']
                output=io.StringIO(newline='');writer=csv.writer(output);writer.writerow(columns)
                for row in data:
                    writer.writerow([("'"+str(row.get(c))) if isinstance(row.get(c),str) and row[c].startswith(('=','+','-','@','\t','\r')) else row.get(c) for c in columns])
                self.download(kind+'.csv',output.getvalue().encode('utf-8-sig'),'text/csv; charset=utf-8');return
            elif url.path == '/api/usage':
                if set(q)-{'session_id','task_id','root_session_id','project_id','model','start','end'}:
                    raise ValueError('unknown filter')
                result = service.aggregate(db,**q)
            elif url.path == '/api/sessions':
                result = service.sessions(db)
            elif url.path in ('/api/tasks','/api/current'):
                result = service.tasks(db,int(q.get('limit',100)),current=url.path=='/api/current')
            elif url.path == '/api/models':
                result = service.rows(db,'SELECT DISTINCT model FROM responses WHERE model IS NOT NULL ORDER BY model')
            elif url.path == '/api/projects':
                result = service.rows(db,'SELECT * FROM projects ORDER BY name')
            else:
                self.reply(404,{'error':'not found'});return
            self.reply(200,result)
        except (ValueError,TypeError):
            self.reply(400,{'error':'invalid query'})
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError,TimeoutError):
            pass
        except (sqlite3.Error,OSError):
            self.reply(503,{'error':'local storage unavailable; check the service and retry'})
        finally:
            if db is not None:db.close()

    def download(self,name,body,mime):
        self.send_response(200);self.send_header('Content-Type',mime)
        self.send_header('Content-Disposition',f'attachment; filename="{name}"')
        self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)))
        self.end_headers();self.wfile.write(body)

    def static(self):
        root=self.server.frontend.resolve();name=unquote(urlsplit(self.path).path).lstrip('/')
        path=(root/name).resolve()
        if not path.is_relative_to(root):self.reply(403,{'error':'invalid path'});return
        if not path.is_file():
            if '.' in name or name.split('/')[0] not in {'','live','tasks','sessions','projects','models','agents','insights','settings'}:
                self.reply(404,{'error':'not found'});return
            path=root/'index.html'
        if not path.is_file():self.reply(404,{'error':'frontend not built; run npm install and npm run build'});return
        body=path.read_bytes();self.send_response(200)
        self.send_header('Content-Type',mimetypes.guess_type(str(path))[0] or 'application/octet-stream')
        self.send_header('Content-Length',str(len(body)));self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
        self.end_headers();self.wfile.write(body)

    def do_POST(self):
        port=self.server.server_address[1];host=self.headers.get('Host');origin=self.headers.get('Origin')
        if host not in {f'127.0.0.1:{port}',f'localhost:{port}'} or origin not in {f'http://127.0.0.1:{port}',f'http://localhost:{port}'}:
            self.reply(403,{'error':'same-origin request required'});return
        if self.path!='/api/settings':self.reply(404,{'error':'not found'});return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=65536 or self.headers.get('Content-Type')!='application/json':raise ValueError('invalid body')
            raw=json.loads(self.rfile.read(size))
            with self.server.settings_lock:value=settings.save(self.server.settings_path,raw)
            self.reply(200,value)
        except (ValueError,TypeError,KeyError):self.reply(400,{'error':'Check thresholds and pricing. Use positive thresholds, nonnegative USD rates, unique model/date pairs, and YYYY-MM-DD dates.'})
        except OSError:self.reply(503,{'error':'settings could not be saved; check local permissions'})

    def events(self, db):
        self.send_response(200)
        self.send_header('Content-Type','text/event-stream')
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        self.connection.settimeout(10)
        previous = None
        while not self.server.stop.is_set():
            version = db.execute('PRAGMA data_version').fetchone()[0]
            if version != previous:
                self.wfile.write(b'event: invalidate\ndata: {"refetch":true}\n\n')
                previous = version
            else:
                self.wfile.write(b': heartbeat\n\n')
            self.wfile.flush()
            self.server.stop.wait(self.server.interval)
