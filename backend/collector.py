"""Bounded Place v2 collection with resumable, credential-free audit."""
import argparse
import hashlib
import math
import os
import time
from urllib.parse import urlencode
from urllib.request import urlopen
from .storage import ROOT, read, write, now
from .geo import CampusGeometry

FOOD=("美食","咖啡厅","茶饮")
CAMPUS=("购物","生活服务","超市","便利店","打印店","理发店","快递","药店","银行","书店")
LIMIT=150

class RequestFailure(Exception):
    def __init__(self,code):self.code=code

def request_baidu(params,key):
    try:
        url="https://api.map.baidu.com/place/v2/search?"+urlencode(dict(params,ak=key))
        with urlopen(url,timeout=25) as response:
            import json
            data=json.load(response)
    except Exception:
        raise RequestFailure("transport_error") from None
    if data.get("status")!=0:
        raise RequestFailure("api_"+str(data.get("status")))
    return data

def poi_category(info):
    tag=info.get("tag") or ""
    if "咖啡" in tag:return "coffee"
    if "饮品" in tag or "茶饮" in tag:return "drink"
    if info.get("type")=="cater" or "美食" in tag:return "restaurant"
    if "购物" in tag:return "retail"
    if "生活服务" in tag or "丽人" in tag:return "service"
    if "药店" in tag:return "retail"
    if "银行" in tag or "金融" in tag:return "finance"
    return "other"

def task_id(bounds,query):
    return hashlib.sha256(repr((bounds,query)).encode()).hexdigest()[:16]

def make_task(bounds,query,depth=0):
    return dict(id=task_id(bounds,query),bounds=list(bounds),query=query,depth=depth,
                page=0,status="pending",uids=[],failures=0)

def initial_tasks(geo,names):
    from shapely.geometry import box
    minx,miny,maxx,maxy=geo.region.bounds
    tasks=[]
    for x in range(math.floor(minx/500)*500,math.ceil(maxx/500)*500,500):
        for y in range(math.floor(miny/500)*500,math.ceil(maxy/500)*500,500):
            bounds=[x,y,x+500,y+500];tile=box(*bounds)
            if not tile.intersects(geo.region):continue
            categories=FOOD+CAMPUS if tile.intersects(geo.boundary) else FOOD
            tasks.extend(make_task(bounds,q) for q in categories)
    # Same bounded search, targeting known names that broad categories may miss.
    tasks.extend(make_task(list(geo.region.bounds),name) for name in names)
    return tasks

def split_task(task):
    x0,y0,x1,y1=task["bounds"];mx=(x0+x1)/2;my=(y0+y1)/2
    return [make_task(b,task["query"],task["depth"]+1) for b in
            ([x0,y0,mx,my],[mx,y0,x1,my],[x0,my,mx,y1],[mx,my,x1,y1])]

class Collector:
    def __init__(self,directory,geo,fetch=request_baidu,sleep=time.sleep,clock=time.monotonic):
        self.directory,self.geo,self.fetch,self.sleep,self.clock=directory,geo,fetch,sleep,clock
        self.last_request=None
    def run(self,key,names=(),max_requests=300,geometry=None):
        path=self.directory/"collection.json"
        state=read(path)
        if state is None:
            state=dict(created_at=now(),scope="main-campus + 1000m food buffer",
                       tasks=initial_tasks(self.geo,names),requests_total=0)
        previous=state.get("query_geometry","bounds")
        if geometry and geometry!=previous and any(t.get("uids") or t.get("last_success_at") for t in state["tasks"]):
            raise ValueError("已有成功分页，不允许更换检索模式；请沿用原模式续采")
        state["query_geometry"]=geometry or previous
        if not key:
            leaves=[t for t in state["tasks"] if t["status"]!="split"]
            state["run_status"]="complete" if leaves and all(t["status"]=="complete" for t in leaves) else "blocked_missing_key"
            state["last_attempt_status"]="blocked_missing_key"
            write(path,state);return state
        used=0
        state.update(run_status="running",last_attempt_status="running",updated_at=now())
        write(path,state)
        for task in state["tasks"]:
            if used>=max_requests:break
            if task["status"] in {"complete","split","truncated","incomplete"}:continue
            while used<max_requests:
                x0,y0,x1,y1=task["bounds"]
                corners=[self.geo.local_to_bd(x,y) for x,y in ((x0,y0),(x1,y0),(x0,y1),(x1,y1))]
                params=dict(query=task["query"],bounds=f"{min(p[0] for p in corners)},{min(p[1] for p in corners)},{max(p[0] for p in corners)},{max(p[1] for p in corners)}",
                            output="json",scope=2,page_size=20,page_num=task["page"])
                if state["query_geometry"]=="circle":
                    lat,lng=self.geo.local_to_bd((x0+x1)/2,(y0+y1)/2)
                    params.pop("bounds")
                    params.update(location=f"{lat},{lng}",radius=math.ceil(math.hypot(x1-x0,y1-y0)/2)+20,
                                  radius_limit="true")
                if self.last_request is not None:
                    self.sleep(max(0,1-(self.clock()-self.last_request)))
                self.last_request=self.clock();used+=1;state["requests_total"]+=1
                try:
                    result=self.fetch(params,key)
                except RequestFailure as error:
                    task["status"]="failed";task["failures"]+=1;task["error"]=error.code
                    state.update(run_status="request_failed",last_attempt_status="request_failed",
                                 updated_at=now(),last_run_requests=used)
                    write(path,state)
                    if error.code in {"api_3","api_4","api_5","api_9","api_101","api_200","api_201","api_202","api_203","api_210","api_211","api_240","api_302"}:
                        return state
                    if task["failures"]%3==0:break
                    self.sleep(min(8,2**(task["failures"]%3)));continue
                stamp=now()
                write(self.directory/"raw"/f"{task['id']}-{task['page']:03}-{state['requests_total']:06}.json",
                      dict(retrieved_at=stamp,params=params,result=result))
                rows=result.get("results",[])
                total=result.get("total")
                task["uids"]=sorted(set(task["uids"])|{r["uid"] for r in rows if r.get("uid")})
                task.update(total=total,last_success_at=stamp,status="pending")
                task.pop("error",None)
                if isinstance(total,int) and total>=LIMIT:
                    if task["depth"]<3 and max(x1-x0,y1-y0)>125:
                        state["tasks"].extend(split_task(task));task["status"]="split"
                    else:task["status"]="truncated"
                elif not rows:
                    task["status"]="incomplete" if isinstance(total,int) and len(task["uids"])<total else "complete"
                elif isinstance(total,int) and (task["page"]+1)*20>=total:
                    task["status"]="complete" if len(task["uids"])>=total else "incomplete"
                elif task["page"]>=7:
                    task["status"]="truncated"
                else:task["page"]+=1
                # Strict radius can make provider total inaccurate. Never silently count
                # an underfilled task as complete; refine spatially when possible.
                if task["status"]=="incomplete" and task["depth"]<3 and max(x1-x0,y1-y0)>125:
                    state["tasks"].extend(split_task(task));task["status"]="split"
                write(path,state)
                if task["status"]!="pending":break
        leaves=[t for t in state["tasks"] if t["status"]!="split"]
        state["run_status"]="complete" if all(t["status"]=="complete" for t in leaves) else "partial"
        state["last_attempt_status"]=state["run_status"]
        state["updated_at"]=now();state["last_run_requests"]=used;write(path,state)
        return state

def normalize(directory,geo):
    records={}
    for path in sorted((directory/"raw").glob("*.json")):
        snapshot=read(path)
        for row in snapshot["result"].get("results",[]):
            if row.get("uid"):
                old=records.get(row["uid"])
                if old is None or snapshot["retrieved_at"]>=old[1]:
                    records[row["uid"]]=(row,snapshot["retrieved_at"])
    historical=read(ROOT/"data/baidu_poi_audit_20260921.json",{})
    for query in historical.get("queries",[]):
        for row in query["results"]:
            if row.get("uid") and row["uid"] not in records:
                records[row["uid"]]=(row,historical.get("retrieved_at"))
    from .adapters import CatalogAdapter
    catalog=CatalogAdapter(directory,ROOT/"data/campus_info.sqlite3").snapshot()
    existing={p["id"]:p for p in read(directory/"baidu_normalized.json",[])}
    normalized=[];dispositions=[];possible_duplicates=[];updates=[]
    for uid,(row,stamp) in records.items():
        pid="baidu-"+uid
        if not row.get("location"):
            dispositions.append(dict(uid=uid,name=row.get("name"),status="needs_location"))
            # Retain named POI even if it cannot participate in spatial recommendation.
            loc=None;wgs=None;zone="unknown";bid=None;distance=None
        else:
            loc,wgs=geo.bd_to_local(row["location"]);zone,bid,distance=geo.classify(loc)
        info=row.get("detail_info") or {}
        tag=info.get("tag") or ""
        if zone=="outside":
            dispositions.append(dict(uid=uid,name=row.get("name"),status="outside_scope"));continue
        if zone=="nearby" and info.get("type")!="cater" and not any(w in (tag+row["name"]) for w in ("美食","餐","咖啡","茶","小吃","饭","鸡","饼","粉","面","肯德基","麦当劳")):
            dispositions.append(dict(uid=uid,name=row["name"],status="nearby_nonfood"));continue
        p=dict(id=pid,name=row["name"],source="baidu_place_v2",source_uid=uid,
            business_status=row.get("status"),
            retrieved_at=stamp,status="unverified",address=row.get("address",""),zone=zone,
            location=loc,location_crs="local EPSG:32650" if loc else None,
            location_source="bd09_approximate_conversion",original_bd09=row.get("location"),
            wgs84_approximate=wgs,building_id=bid,building_link_status="candidate" if bid else "unlinked",
            category=poi_category(info),baidu_tag=tag,floor="",access_scope="unknown",
            opening_hours=None,raw_hours=info.get("shop_hours"),hours_source="unknown",
            average_price=info.get("price"),distance_from_campus_m=distance)
        for known in catalog["pois"]:
            if known["id"]==pid or (uid=="373cf757b9861d774354d750" and known["id"]=="lanhui"):
                continue
            if known["name"] in row["name"] or row["name"] in known["name"] or any(a in row["name"] for a in known.get("aliases",[])):
                possible_duplicates.append(dict(baidu_id=pid,catalog_id=known["id"],status="review_required",
                    reason="名称或别名相近；地址、楼层与位置须人工联合核对"))
        if pid in existing:
            stable=lambda v:{k:x for k,x in v.items() if k!="retrieved_at"}
            if stable(existing[pid])!=stable(p):updates.append(dict(id=pid,candidate=p,reason="保留已录入版本，待核对更新"))
            p=existing[pid]
        normalized.append(p)
        dispositions.append(dict(uid=uid,name=row["name"],status="recorded"))
    # Retain previous entries not present in this run.
    found={p["id"] for p in normalized}
    normalized.extend(p for key,p in existing.items() if key not in found)
    write(directory/"baidu_normalized.json",normalized)
    write(directory/"dispositions.json",dispositions)
    write(directory/"possible_duplicates.json",possible_duplicates)
    write(directory/"update_candidates.json",updates)
    return normalized

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--max-requests",type=int,default=300)
    parser.add_argument("--prepare-only",action="store_true")
    parser.add_argument("--geometry",choices=("bounds","circle"),help="仅首次采集可显式选择；后续沿用审计模式")
    args=parser.parse_args()
    if not 1<=args.max_requests<=300:parser.error("--max-requests must be 1..300")
    from .bootstrap import initialize
    directory=ROOT/"data/life";catalog=initialize(directory);geo=CampusGeometry()
    key="" if args.prepare_only else os.environ.get("BAIDU_MAP_AK","").strip()
    state=Collector(directory,geo).run(key,[p["name"] for p in catalog["pois"]],args.max_requests,args.geometry)
    rows=normalize(directory,geo)
    print(f"status={state['run_status']}; tasks={len(state['tasks'])}; normalized={len(rows)}; credentials not logged")
if __name__=="__main__":main()
