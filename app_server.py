"""Student app; local by default, explicit read-only preview without model access."""
import argparse
import hashlib
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from backend.storage import ROOT, read
from backend.agent.controller import AgentController
from backend.agent.model import ModelError
from backend.agent.candidates import recommend_candidates
from backend.agent.public_model import public_glb
from backend.agent.buildings import building_directory


class PreviewModel:
    configured=False
    connection_status='unconfigured'
    settings={'model':'disabled-preview'}

    def complete(self,*args):
        raise ModelError('临时测试未启用AI对话；可浏览地图、菜单或使用条件筛选。','MODEL_UNCONFIGURED',False)


def make_app_server(port=8793, controller=None, preview_origin=None):
    if preview_origin is not None and not re.fullmatch(r'https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com',preview_origin):
        raise ValueError('预览必须使用精确的HTTPS trycloudflare域名')
    if preview_origin and controller is not None:raise ValueError('公网预览不接受模型控制器')
    agent=controller or (AgentController(model=PreviewModel()) if preview_origin else AgentController())
    completed={};active={};guard=threading.Lock();slots=threading.BoundedSemaphore(2)
    preview_started=time.monotonic();preview_posts=[]
    assets={'/':('app/index.html','text/html; charset=utf-8'),'/app.css':('app/app.css','text/css'),'/app.js':('app/app.js','text/javascript'),
        '/explore/':('app/explore/index.html','text/html; charset=utf-8'),
        '/explore/index.html':('app/explore/index.html','text/html; charset=utf-8'),
        '/responsive.css':('app/responsive.css','text/css'),
        '/presentation.js':('app/presentation.js','text/javascript'),'/components.css':('app/components.css','text/css'),
        '/history.js':('app/history.js','text/javascript'),'/map/':('app/map.html','text/html; charset=utf-8'),'/map/map.js':('app/map.js','text/javascript'),
        '/map/map.css':('app/map.css','text/css'),'/map/locations.js':('app/map-locations.js','text/javascript'),
        '/map/locations.css':('app/map-locations.css','text/css'),'/map/campus.glb':('output/bnu_campus_web_white_v7.glb','model/gltf-binary')}
    for name in ('main.js','state.js','api.js','scene.js','materials.js','explore.css'):
        assets['/explore/'+name]=('app/explore/'+name,'text/css' if name.endswith('.css') else 'text/javascript')
    assets['/explore/art/paper-plaster-v1.png']=('app/explore/art/paper-plaster-v1.png','image/png')
    assets['/explore/art/ginkgo-ornament-v1.png']=('app/explore/art/ginkgo-ornament-v1.png','image/png')
    assets['/explore/art/ivory-paper-v1.png']=('app/explore/art/ivory-paper-v1.png','image/png')
    assets['/explore/art/manifest.json']=('app/explore/art/manifest.json','application/json')
    for name in ('three.module.min.js','three.core.min.js','GLTFLoader.js','OrbitControls.js','BufferGeometryUtils.js'):
        assets['/map/'+name]=('vendor/three/'+name,'text/javascript')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def response_headers(self,status,mime):
            self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
            # Inline importmap only; application scripts and all data remain same-origin.
            import base64
            map_hash=base64.b64encode(hashlib.sha256(b'{"imports":{"three":"/map/three.module.min.js"}}').digest()).decode()
            self.send_header('Content-Security-Policy',f"default-src 'self'; script-src 'self' 'sha256-{map_hash}'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self' blob:; frame-ancestors 'self'; base-uri 'none'; form-action 'self'")
        def reply(self,status,value,mime='application/json; charset=utf-8'):
            raw=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False,allow_nan=False).encode()
            self.response_headers(status,mime);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def body(self):
            if self.headers.get('Origin')!=self.server.origin or self.headers.get('X-BNU-Client')!='1':raise PermissionError('请求来源无效')
            size=int(self.headers.get('Content-Length','0'))
            if self.headers.get('Transfer-Encoding') or not 0<size<=65536:raise ValueError('请求大小无效')
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('须使用JSON')
            self.connection.settimeout(100)
            data=json.loads(self.rfile.read(size),parse_constant=lambda _: (_ for _ in ()).throw(ValueError('无效数字')))
            if not isinstance(data,dict):raise ValueError('请求须为对象')
            return data
        def dispatch(self):
            streaming=False
            try:
                if self.headers.get('Host')!=self.server.allowed_host:raise PermissionError('请求入口无效')
                if preview_origin and time.monotonic()-preview_started>=7200:
                    return self.reply(410,{'error':'本轮临时测试已结束，请联系管理员重新开启。'})
                path=urlsplit(self.path).path;q=parse_qs(urlsplit(self.path).query)
                if self.command=='GET':
                    if path in assets:
                        file,mime=assets[path];return self.reply(200,public_glb(ROOT/file) if path=='/map/campus.glb' else (ROOT/file).read_bytes(),mime)
                    if path=='/api/agent/status':return self.reply(200,dict(configured=getattr(agent.model,'configured',True),connection_status=getattr(agent.model,'connection_status','unverified'),model=getattr(agent.model,'settings',{}).get('model','test-model'),version=(ROOT/'VERSION').read_text().strip(),local_only=not bool(preview_origin),preview=bool(preview_origin)))
                    if path=='/api/app/directory':return self.reply(200,agent.tools.directory())
                    if path=='/api/app/buildings':return self.reply(200,building_directory())
                    if path=='/api/app/place':return self.reply(200,agent.tools.execute('get_place',{'poi_id':q.get('id',[''])[0],'offset':int(q.get('offset',['0'])[0])},{}))
                    if path=='/api/app/schedule':return self.reply(200,agent.tools.execute('get_schedule',{'date':q.get('date',[''])[0]},{}))
                    return self.reply(404,{'error':'资源不存在'})
                if preview_origin:
                    with guard:
                        current=time.monotonic()
                        preview_posts[:]=[t for t in preview_posts if current-t<60]
                        limited=len(preview_posts)>=30
                        if not limited:preview_posts.append(current)
                    if limited:return self.reply(429,{'error':'测试入口请求较多，请一分钟后重试。','retryable':True})
                data=self.body()
                if preview_origin and path=='/api/agent/chat':
                    return self.reply(503,{'error':'临时测试未启用AI对话；可浏览地图、菜单或使用条件筛选。','code':'MODEL_UNCONFIGURED','retryable':False})
                if preview_origin and path!='/api/app/candidates':raise PermissionError('临时测试不开放此操作')
                if path=='/api/agent/cancel':
                    with guard:
                        cancel=active.get(data.get('request_id'))
                        if cancel:cancel.set()
                    return self.reply(200,dict(cancel_requested=bool(cancel),message='已申请停止后续处理；已发往模型的请求可能仍在结束中。' if cancel else '本轮请求已结束或尚未到达；已停止本机等待。'))
                if path=='/api/app/candidates':return self.reply(200,recommend_candidates(agent.tools.snapshot(),data.get('conditions',{}),data.get('mode','real')))
                if path!='/api/agent/chat':return self.reply(404,{'error':'接口不存在'})
                ident=data.get('request_id')
                if not isinstance(ident,str) or not 8<=len(ident)<=100:raise ValueError('request_id 无效')
                digest=hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                with guard:
                    if ident in completed:
                        old,events=completed[ident]
                        if old!=digest:return self.reply(409,{'error':'重复请求ID与内容不一致'})
                        raw=''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in events).encode()
                        return self.reply(200,raw,'application/x-ndjson; charset=utf-8')
                    if ident in active:return self.reply(409,dict(error='这条请求仍在处理，请稍后点击重试获取结果。',code='REQUEST_ACTIVE',retryable=True,request_id=ident))
                    if not slots.acquire(False):return self.reply(429,dict(error='已有两个请求在处理，请稍后再试',code='LOCAL_BUSY',retryable=True,request_id=ident))
                    cancel=threading.Event();active[ident]=cancel
                events=[]
                try:
                    self.response_headers(200,'application/x-ndjson; charset=utf-8');self.end_headers();streaming=True
                    def emit(event):
                        events.append(event)
                        try:
                            self.wfile.write((json.dumps(event,ensure_ascii=False,allow_nan=False)+'\n').encode());self.wfile.flush()
                        except (BrokenPipeError,ConnectionError,TimeoutError):
                            pass # complete/cache read-only work so transport retries do not repay model cost
                    try:agent.run(data,emit,cancelled=cancel.is_set)
                    except ModelError as e:emit(e.event(ident))
                    except ValueError:emit(ModelError('条件格式有误，请调整输入后重试。','INVALID_INPUT',False).event(ident))
                    except Exception:emit(ModelError('本轮处理异常；已获取的结果保留，请重试。','INTERNAL_ERROR').event(ident))
                    with guard:
                        completed[ident]=(digest,events)
                        if len(completed)>100:completed.pop(next(iter(completed)))
                finally:
                    with guard:active.pop(ident,None)
                    slots.release()
            except PermissionError as e:
                if not streaming:self.reply(403,{'error':str(e)})
            except (ValueError,KeyError,TypeError):
                if not streaming:self.reply(400,{'error':'请求参数无效'})
            except (BrokenPipeError,ConnectionError,TimeoutError):pass
            except Exception:
                if not streaming:self.reply(500,{'error':'本地数据服务暂时不可用'})
        do_GET=dispatch
        do_POST=dispatch
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.origin=preview_origin or f'http://127.0.0.1:{server.server_port}'
    server.allowed_host=urlsplit(server.origin).netloc
    return server


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8793)
    parser.add_argument('--preview-origin',help='独立临时外网试用：精确HTTPS域名，禁用模型调用，两小时失效')
    args=parser.parse_args()
    server=make_app_server(args.port,preview_origin=args.preview_origin)
    print(f'京师智行试用版 {server.origin}/explore/',flush=True)
    server.serve_forever()
