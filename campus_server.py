"""Loopback-only campus information API + static viewer, Python standard library."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import json, sqlite3, uuid, datetime, argparse, math
from contextlib import contextmanager
from backend.service import LifeService
from backend.library import ReservationConflict
ROOT=Path(__file__).resolve().parent
DB=ROOT/'data/campus_info.sqlite3'
LIFE_DIR=ROOT/'data/life'
FIELDS={'id','revision','name','category','x','y','building_id','source','status','notes','hours','price','tags','updated_at','floor','unit'}
CATEGORIES={'canteen','snack','shop','building','road','correction','other','gate'}
@contextmanager
def connect():
    c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
    try:
        with c:yield c
    finally:c.close()
def init():
    DB.parent.mkdir(exist_ok=True)
    with connect() as c:
        c.execute('CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS history(id TEXT, revision INTEGER, payload TEXT, saved_at TEXT)')
def validate(d):
    if not isinstance(d,dict) or set(d)-FIELDS:raise ValueError('未知字段或非 JSON 对象')
    for k,n in [('name',100),('source',500),('notes',4000),('hours',300),('price',200),('floor',80),('unit',100)]:
        v=d.get(k,'')
        if not isinstance(v,str) or len(v)>n:raise ValueError(k+' 格式或长度错误')
    if not d.get('name','').strip() or not d.get('source','').strip():raise ValueError('名称与来源必填')
    if d.get('category') not in CATEGORIES:raise ValueError('类别无效')
    if d.get('status') not in {'unverified','verified','historical','archived'}:raise ValueError('核实状态无效')
    for k,bound in [('x',452),('y',601)]:
        v=d.get(k)
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or abs(v)>bound:raise ValueError(k+' 必须是校园范围内的本地米坐标')
    bid=d.get('building_id')
    if bid is not None:
        if isinstance(bid,bool) or not isinstance(bid,int):raise ValueError('building_id 须为整数或 null')
        asset_path=ROOT/'assets/campus_assets_white_v4.json'
        if not asset_path.exists():asset_path=ROOT/'assets/campus_assets_white_v3.json'
        assets=json.loads(asset_path.read_text(encoding='utf-8'))
        if bid not in {b['osm_id'] for b in assets['buildings']}:raise ValueError('建筑 ID 不存在')
    tags=d.get('tags',[])
    if not isinstance(tags,list) or len(tags)>20 or any(not isinstance(t,str) or len(t)>50 for t in tags):raise ValueError('标签格式错误')
    return {k:d[k] for k in FIELDS-{'id','revision','updated_at'} if k in d}
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw):super().__init__(*a,directory=str(ROOT),**kw)
    def send_json(self,status,data):
        raw=json.dumps(data,ensure_ascii=False,allow_nan=False).encode();self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers()
        if self.command!='HEAD':self.wfile.write(raw)
    def valid_host(self):return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
    def do_GET(self):
        if not self.valid_host():return self.send_json(403,{'error':'Host rejected'})
        path=urlsplit(self.path).path
        if path.startswith('/api/life/'):
            return self.life_request(path, False)
        if path=='/api/health':return self.send_json(200,{'ok':True,'schema_version':1,'storage':'SQLite','scope':'loopback only'})
        if path=='/api/places':
            query=parse_qs(urlsplit(self.path).query)
            with connect() as c:rows=[json.loads(r['payload']) for r in c.execute('SELECT payload FROM records ORDER BY rowid DESC')]
            for key in ['status','category']:
                if query.get(key):rows=[r for r in rows if r.get(key)==query[key][0]]
            if query.get('building_id'):rows=[r for r in rows if str(r.get('building_id'))==query['building_id'][0]]
            if query.get('q'):rows=[r for r in rows if query['q'][0].casefold() in (r['name']+' '+r.get('notes','')).casefold()]
            return self.send_json(200,{'schema_version':1,'crs':'local EPSG:32650 offsets; x east, y north; metres','records':rows})
        if path.startswith('/api/'):return self.send_json(404,{'error':'Unknown endpoint'})
        # Do not expose the database, logs, source scripts or arbitrary directory listings.
        resolved=Path(self.translate_path(self.path)).resolve()
        if not resolved.is_relative_to(ROOT) or any(part.startswith('.') for part in resolved.relative_to(ROOT).parts) or any(resolved.is_relative_to(ROOT/folder) for folder in ('data','backend','tests')) or resolved.suffix.lower() in {'.py','.sqlite3','.db','.log','.ps1','.cmd'}:
            return self.send_json(403,{'error':'Private file'})
        return super().do_HEAD() if self.command=='HEAD' else super().do_GET()
    def list_directory(self,path):return self.send_json(403,{'error':'Directory listing disabled'})
    def do_HEAD(self):
        # Same access policy as GET; no body is needed by normal static probes.
        return self.do_GET()
    def write_record(self,updating):
        expected={f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}
        if not self.valid_host() or self.headers.get('Origin') not in expected:return self.send_json(403,{'error':'Same-origin local request required'})
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.send_json(415,{'error':'JSON required'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=32768:raise ValueError('请求大小须为 1–32768 字节')
            d=json.loads(self.rfile.read(length));payload=validate(d)
            path=urlsplit(self.path).path
            if (not updating and path!='/api/places') or (updating and not path.startswith('/api/places/')):return self.send_json(404,{'error':'Unknown endpoint'})
            id=path.rsplit('/',1)[-1] if updating else str(uuid.uuid4())
            with connect() as c:
                c.execute('BEGIN IMMEDIATE')
                old=c.execute('SELECT * FROM records WHERE id=?',(id,)).fetchone()
                if updating and old is None:return self.send_json(404,{'error':'记录不存在'})
                if updating and d.get('revision')!=old['revision']:return self.send_json(409,{'error':'版本冲突，请重新载入后编辑'})
                revision=old['revision']+1 if old else 1
                now=datetime.datetime.now(datetime.timezone.utc).isoformat()
                payload.update(id=id,revision=revision,updated_at=now)
                if old:c.execute('INSERT INTO history VALUES(?,?,?,?)',(id,old['revision'],old['payload'],now))
                c.execute('INSERT OR REPLACE INTO records VALUES(?,?,?)',(id,revision,json.dumps(payload,ensure_ascii=False)))
            return self.send_json(200 if updating else 201,payload)
        except (ValueError,TypeError,UnicodeError) as e:return self.send_json(400,{'error':str(e)})
    def life_request(self,path,writing):
        if not self.valid_host():return self.send_json(403,{'error':'Host rejected'})
        service=LifeService(LIFE_DIR,DB)
        try:
            if writing:
                expected={f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}
                if self.headers.get('Origin') not in expected:return self.send_json(403,{'error':'Same-origin local request required'})
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.send_json(415,{'error':'JSON required'})
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=32768:raise ValueError('请求大小须为 1–32768 字节')
                data=json.loads(self.rfile.read(length))
                result=service.post(path[len('/api/life'):],data)
            else:
                result=service.get(path[len('/api/life'):],parse_qs(urlsplit(self.path).query))
            return self.send_json(200,result)
        except ReservationConflict as error:return self.send_json(409,{'error':str(error)})
        except KeyError:return self.send_json(404,{'error':'Unknown endpoint'})
        except (ValueError,TypeError,UnicodeError) as error:return self.send_json(400,{'error':str(error)})
        except OSError:return self.send_json(503,{'error':'本地数据暂不可用，请检查服务目录和文件权限'})
    def do_POST(self):
        path=urlsplit(self.path).path
        if path.startswith('/api/life/'):return self.life_request(path,True)
        self.write_record(False)
    def do_PUT(self):self.write_record(True)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8786);args=parser.parse_args()
    from backend.bootstrap import initialize
    init();initialize(LIFE_DIR);print(f'Campus viewer + API: http://127.0.0.1:{args.port}/white/',flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
if __name__=='__main__':main()
