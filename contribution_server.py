"""Isolated loopback-only contribution server. No static access to project root."""
import argparse
import json
import secrets
import threading
import time
import base64
import hashlib
from collections import defaultdict, deque
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from backend.storage import ROOT, read, write
from backend.adapters import CatalogAdapter
from backend.contribution import ContributionStore, Conflict, digest
from backend.map_review import review_catalog
from backend.building_audit import building_audit


TEAM_NAMES=("g","kdy","lyx","ljz","ll")


def make_server(port=8790, directory=None, origin=None, team_mode=False, admin_port=None, local_team=False):
    if local_team and origin: raise ValueError("纯本地模式不能设置外部 origin")
    team_mode=team_mode or local_team
    life=directory or ROOT/"data/life"
    store=ContributionStore(life/"contributions", CatalogAdapter(life, ROOT/"data/campus_info.sqlite3" if directory is None else None))
    expected=origin or f"http://127.0.0.1:{port}"
    parsed=urlsplit(expected)
    if parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.scheme not in {"http","https"}:
        raise ValueError("origin 必须为完整、无路径的源地址")
    if origin and parsed.scheme!="https": raise ValueError("外部 origin 必须使用 HTTPS")
    if team_mode and not origin and not local_team: raise ValueError("免凭证外网服务必须设置精确 HTTPS origin")
    if team_mode and (not isinstance(admin_port,int) or (admin_port==port and port!=0)): raise ValueError("管理员须使用独立端口")
    session_path=store.directory/"sessions.json"
    sessions=read(session_path,{}) if team_mode else {}
    attempts=defaultdict(deque); guard=threading.RLock()

    def persist_sessions():
        if team_mode:write(session_path,sessions)

    class Handler(BaseHTTPRequestHandler):
        server_version="Contribution/1.2"
        def log_message(self,*args): pass # never log request paths, identities or credentials

        def reply(self,status,value,mime="application/json; charset=utf-8",cookie=None):
            raw=json.dumps(value,ensure_ascii=False,allow_nan=False).encode() if not isinstance(value,bytes) else value
            self.send_response(status)
            self.send_header("Content-Type",mime);self.send_header("Content-Length",str(len(raw)))
            self.send_header("Cache-Control","no-store");self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Referrer-Policy","no-referrer")
            map_hash=base64.b64encode(hashlib.sha256(b'{"imports":{"three":"/map/three.module.min.js"}}').digest()).decode()
            self.send_header("Content-Security-Policy",f"default-src 'self'; script-src 'self' 'sha256-{map_hash}'; style-src 'self'; connect-src 'self' blob:; img-src 'self' blob: data:; frame-ancestors 'self'; base-uri 'none'; form-action 'self'")
            if cookie:self.send_header("Set-Cookie",cookie)
            self.end_headers();self.wfile.write(raw)

        def body(self,limit=65536,binary=False):
            if self.headers.get("Transfer-Encoding"): raise ValueError("不支持分块上传")
            size=int(self.headers.get("Content-Length","0"))
            if not 0<size<=limit: raise ValueError("请求大小无效")
            self.connection.settimeout(10)
            raw=self.rfile.read(size)
            if len(raw)!=size: raise ValueError("请求不完整")
            if binary:return raw
            if self.headers.get("Content-Type","").split(";")[0]!="application/json": raise ValueError("须发送JSON")
            result=json.loads(raw,parse_constant=lambda _: (_ for _ in ()).throw(ValueError("无效数字")))
            if not isinstance(result,dict):raise ValueError("请求须为对象")
            return result

        def session(self):
            cookies=SimpleCookie();cookies.load(self.headers.get("Cookie",""))
            token=cookies.get("contribution_session")
            with guard:
                session=sessions.get(token.value if token else "")
                if not session or session["expires"]<time.time() or session.get("scope")!=("admin" if self.server.admin_mode else "public") or (not team_mode and not store.active(session["user"])):
                    raise PermissionError("请登录，或凭证已撤销")
                if self.command=="POST" and not secrets.compare_digest(self.headers.get("X-CSRF-Token",""),session["csrf"]):
                    raise PermissionError("CSRF 校验失败")
                return session

        def handle_request(self):
            if self.headers.get("Host")!=urlsplit(self.server.expected_origin).netloc: raise PermissionError("Host 不允许")
            path=urlsplit(self.path).path
            if self.command=="POST":
                if self.headers.get("Origin")!=self.server.expected_origin: raise PermissionError("请求来源不允许")
                # Global limit cannot be bypassed by forged proxy headers.
                with guard:
                    bucket=attempts["login" if path.endswith("/login") else "write"]
                    while bucket and bucket[0]<time.monotonic()-60:bucket.popleft()
                    if len(bucket)>=(20 if path.endswith("/login") else 180):
                        return self.reply(429,{"error":"请求过于频繁，请稍后重试"})
                    bucket.append(time.monotonic())
            static={"/":"index.html","/app.js":"app.js","/style.css":"style.css"}
            if self.command=="GET" and path in static:
                suffix=static[path].split(".")[-1]
                return self.reply(200,(ROOT/"contribute"/static[path]).read_bytes(),{"html":"text/html; charset=utf-8","js":"text/javascript; charset=utf-8","css":"text/css; charset=utf-8"}[suffix])
            if path=="/api/contribute/login" and self.command=="POST":
                data=self.body()
                if team_mode:
                    name=data.get("name")
                    if name not in TEAM_NAMES:raise ValueError("请选择团队名单中的署名")
                    if self.server.admin_mode and name!="g":raise PermissionError("本地管理入口只供 g 使用")
                    user=dict(id="g" if self.server.admin_mode else "visitor-"+secrets.token_hex(16),name=name,role="admin" if self.server.admin_mode else "member")
                else:
                    token=data.get("token")
                    if not isinstance(token,str) or len(token)>256: raise ValueError("凭证格式错误")
                    user=store.credential(token)
                key=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
                with guard:
                    for expired in [k for k,v in sessions.items() if v["expires"]<time.time()]:sessions.pop(expired)
                    lifetime=30*24*3600 if team_mode else 8*3600
                    sessions[key]=dict(user=user,csrf=csrf,expires=time.time()+lifetime,scope="admin" if self.server.admin_mode else "public")
                    persist_sessions()
                cookie=f"contribution_session={key}; HttpOnly; SameSite=Strict; Path=/; Max-Age={lifetime}"
                if self.server.expected_origin.startswith("https:"):cookie+="; Secure"
                return self.reply(200,dict(user=user,csrf=csrf),cookie=cookie)
            session=self.session();user=session["user"]
            if path in ("/audit/","/audit.js","/api/contribute/building-audit"):
                if not self.server.admin_mode or user["role"]!="admin":raise PermissionError("建筑证据仅供本机管理员查看")
                if self.command!="GET":return self.reply(405,{"error":"此入口只读"})
                if path=="/api/contribute/building-audit":return self.reply(200,building_audit(store.entities()))
                filename,mime=("audit.html","text/html; charset=utf-8") if path=="/audit/" else ("audit.js","text/javascript; charset=utf-8")
                return self.reply(200,(ROOT/"contribute"/filename).read_bytes(),mime)
            if self.command=="GET":
                # Explicit read-only assets; never expose root, old APIs or private data.
                map_assets={"/map/":("contribute/map.html","text/html; charset=utf-8"),
                            "/map/locations.js":("app/map-locations.js","text/javascript"),
                            "/map/locations.css":("app/map-locations.css","text/css"),
                            "/map/map.js":("contribute/map.js","text/javascript"),
                            "/map/map.css":("contribute/map.css","text/css"),
                            "/map/review.css":("contribute/review.css","text/css"),
                            "/map/campus.glb":("output/bnu_campus_web_white_v6.glb","model/gltf-binary")}
                for name in ("three.module.min.js","three.core.min.js","GLTFLoader.js","OrbitControls.js","BufferGeometryUtils.js"):
                    map_assets["/map/"+name]=("vendor/three/"+name,"text/javascript")
                if path in map_assets:
                    filename,mime=map_assets[path]
                    return self.reply(200,(ROOT/filename).read_bytes(),mime)
                if path=="/map/buildings.json":
                    assets=read(ROOT/"assets/campus_assets_white_v6.json")
                    return self.reply(200,dict(model_version="white_v6",coordinate_frame="white_v4",buildings=[{k:b.get(k) for k in ("osm_id","name","audit_label","floors","height","floor_status","height_status","correction_note")} for b in assets["buildings"]]))
                if path=="/api/contribute/me":return self.reply(200,dict(user=user,csrf=session["csrf"]))
                if path=="/api/contribute/map-review":
                    return self.reply(200,review_catalog(store.entities(),life))
                if path=="/api/contribute/catalog":
                    catalog=store.entities()
                    # Only structured public catalog fields, not legacy private notes.
                    allowed={"id","name","category","address","floor","poi_id","shop_id","source","opening_hours","price","tags","available","specification","sales_channel","serving_minutes","access_scope","business_status","zone","location","field_evidence","map_point","building_floors","floor_evidence","location_description"}
                    allowed.update({"opening_hours_text","hours_notes","dining_type","menu_section","availability_note","independent_window_verified","entity_type"})
                    output={k:[dict({f:v for f,v in r.items() if f in allowed},revision=digest(r)) for r in catalog[k] if r.get("source")!="simulated"] for k in ("pois","shops","items")}
                    return self.reply(200,output)
                if path=="/api/contribute/submissions":return self.reply(200,store.records(user))
                if path=="/api/contribute/tasks":
                    catalog=store.entities()
                    updates=read(life/"update_candidates.json",[])
                    limited=[dict(id=u.get("id"),name=u.get("candidate",{}).get("name"),address=u.get("candidate",{}).get("address")) for u in updates]
                    return self.reply(200,dict(claims=store.state()["claims"],missing_coordinates=[p["id"] for p in catalog["pois"] if not p.get("location")],missing_hours=[p["id"] for p in catalog["pois"] if not p.get("opening_hours")],duplicates=read(life/"possible_duplicates.json",[]),updates=limited))
                if path.startswith("/api/contribute/attachments/"):
                    raw,mime=store.attachment(user,path.rsplit("/",1)[1]);return self.reply(200,raw,mime)
                if path=="/api/contribute/export":
                    if user["role"]!="admin" or (team_mode and not self.server.admin_mode):raise PermissionError("仅本地管理员可导出")
                    return self.reply(200,store.state())
            if self.command=="POST":
                if path=="/api/contribute/logout":
                    with guard:
                        for k in [k for k,v in sessions.items() if v is session]:sessions.pop(k)
                        persist_sessions()
                    return self.reply(200,{},cookie="contribution_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0")
                if path=="/api/contribute/attachments":return self.reply(200,store.upload(user,self.body(3*1024*1024,True),self.headers.get("Content-Type")))
                data=self.body()
                if path=="/api/contribute/submissions":return self.reply(200,store.submit(user,data))
                if path=="/api/contribute/review":
                    if team_mode and not self.server.admin_mode:raise PermissionError("审核只允许本机入口")
                    return self.reply(200,store.review(user,data))
                if path=="/api/contribute/claim":return self.reply(200,store.claim(user,data.get("entity_id")))
            self.reply(404,{"error":"接口不存在"})

        def dispatch(self):
            try:self.handle_request()
            except PermissionError as exc:self.reply(403,{"error":str(exc)})
            except Conflict as exc:self.reply(409,{"error":str(exc)})
            except (ValueError,TypeError,KeyError) as exc:self.reply(400,{"error":str(exc)})
            except (BrokenPipeError,ConnectionError,TimeoutError):pass
            except Exception:self.reply(500,{"error":"服务异常；未确认保存，请保留填写内容并联系管理员"})
        do_GET=dispatch
        do_POST=dispatch

    class ExclusiveServer(ThreadingHTTPServer):
        def server_close(self):
            super().server_close()
            if getattr(self,"writer_lock",None):
                self.writer_lock.close();self.writer_lock=None
    server=ExclusiveServer(("127.0.0.1",port),Handler)
    # OS lock survives neither crash nor shutdown, but prevents writers on other ports.
    store.directory.mkdir(parents=True,exist_ok=True)
    lock=store.directory.joinpath("writer.lock").open("a+b")
    try:
        import os
        lock.seek(0)
        if os.name=="nt":
            import msvcrt
            msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        server.writer_lock=lock
    except OSError:
        lock.close();server.server_close();raise RuntimeError("同一数据目录已有协作写入服务") from None
    server.expected_origin=origin or f"http://127.0.0.1:{server.server_port}"
    server.store=store
    server.admin_mode=False
    if not team_mode:return server
    admin_server=ThreadingHTTPServer(("127.0.0.1",admin_port),Handler)
    admin_server.expected_origin=f"http://127.0.0.1:{admin_server.server_port}"
    admin_server.store=store
    admin_server.admin_mode=True
    original_close=server.server_close
    def close_both():
        admin_server.server_close()
        original_close()
    server.server_close=close_both
    server.admin_server=admin_server
    return server


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--port",type=int,default=8790)
    parser.add_argument("--origin",help="批准开启隧道后设置精确 HTTPS 源地址")
    parser.add_argument("--team-open",action="store_true",help="免凭证团队署名模式；审核仅本地独立端口")
    parser.add_argument("--local-team",action="store_true",help="纯本地团队模式，不需要公网地址")
    parser.add_argument("--admin-port",type=int,default=8792)
    args=parser.parse_args()
    server=make_server(args.port,origin=args.origin,team_mode=args.team_open,admin_port=args.admin_port,local_team=args.local_team)
    if args.team_open or args.local_team:
        threading.Thread(target=server.admin_server.serve_forever,daemon=True).start()
        print(f"团队填报监听 127.0.0.1:{server.server_port}；本地审核 127.0.0.1:{args.admin_port}")
    else: print(f"独立填报服务：127.0.0.1:{server.server_port}；未自动生成账号、未开启外网")
    server.serve_forever()
