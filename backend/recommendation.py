"""Deterministic, evidence-carrying recommendation; no LLM or routing."""
import math
from collections import Counter
from datetime import timedelta
from .storage import ROOT, read, timestamp
from .adapters import SimulatedCrowdAdapter

def number(value,name,low,high):
    if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or not low<=value<=high:
        raise ValueError(name+" 数值无效")
    return value

def string_list(value,name):
    if not isinstance(value,list) or len(value)>30 or any(not isinstance(v,str) or len(v)>80 for v in value):
        raise ValueError(name+" 须为字符串数组")
    return value

def open_at(hours,at,service_minutes=0):
    """Check a full service interval, including windows that cross midnight."""
    if not hours: return None
    for offset in (-1,0):
        day=at.date()+timedelta(days=offset)
        for start,end in hours:
            a=timestamp(f"{day}T{start}:00+08:00")
            b=timestamp(f"{day}T{end}:00+08:00")
            if b<=a:b+=timedelta(days=1)
            if a<=at and at+timedelta(minutes=service_minutes)<b:return True
    return False

def recommend(catalog,request,crowd=None):
    if not isinstance(request,dict):raise ValueError("请求必须是对象")
    at=timestamp(request.get("current_time"))
    budget=number(request.get("budget"),"budget",0,10000)
    maximum=number(request.get("max_queue_minutes",10),"max_queue_minutes",0,180)
    available=number(request.get("available_minutes",90),"available_minutes",1,1440)
    k=number(request.get("top_k",3),"top_k",1,3)
    if int(k)!=k:raise ValueError("top_k 必须为整数")
    mode=request.get("mode","demo")
    mapped_only=request.get("mapped_only",False)
    if not isinstance(mapped_only,bool):raise ValueError("mapped_only 必须为布尔值")
    if mode not in {"demo","verified"}:raise ValueError("mode 无效")
    taste=string_list(request.get("taste",[]),"taste")
    avoid=string_list(request.get("avoid",[]),"avoid")
    likes=string_list(request.get("likes",[]),"likes")
    dietary=string_list(request.get("dietary_requirements",[]),"dietary_requirements")
    locations={r["id"]:r for r in catalog["locations"]}
    current=locations.get(request.get("current_location","教八"))
    if current is None:raise ValueError("当前位置不在地点列表中")
    next_class=request.get("next_class")
    destination=None
    if next_class is not None:
        if not isinstance(next_class,dict):raise ValueError("next_class 必须为对象")
        deadline=timestamp(next_class.get("time"))
        available=min(available,(deadline-at).total_seconds()/60)
        destination=locations.get(next_class.get("location"))
        if destination is None:raise ValueError("下一课堂位置未知")
        if available<=0:raise ValueError("下一课程必须晚于当前时间")
    config=read(ROOT/"backend/seeds/ranking.json")
    pois={p["id"]:p for p in catalog["pois"]}
    shops={s["id"]:s for s in catalog["shops"]}
    rejected=Counter()
    candidates=[]
    crowd=crowd or SimulatedCrowdAdapter()
    for item in catalog["items"]:
        shop=shops.get(item["shop_id"])
        poi=pois.get(shop["poi_id"]) if shop else None
        if not poi: rejected["关联数据缺失"]+=1;continue
        if poi.get("scope_status") in {"pending","outside"}:
            rejected["新增地点范围尚未核验"]+=1;continue
        if mapped_only and not poi.get("location"):
            rejected["仅查看已有坐标的地点"]+=1;continue
        if poi.get("status") in {"historical","archived","closed"} or shop.get("status") in {"historical","archived","closed"}:
            rejected["历史或停用"]+=1;continue
        if poi.get("business_status") in {"暂停营业","可能已关闭","已关闭"}:
            rejected["来源提示暂停或关闭"]+=1;continue
        if poi.get("access_scope")=="staff":
            rejected["教工餐准入未确认"]+=1;continue
        if poi.get("access_scope")=="unknown" and mode!="demo":
            rejected["准入条件未知"]+=1;continue
        if mode=="verified" and (item.get("source")=="simulated" or shop.get("source")=="simulated" or poi.get("status")!="verified"):
            rejected["缺少已核验真实商品"]+=1;continue
        tags=set(item.get("tags",[]))
        if tags.intersection(avoid):rejected["不符合忌口"]+=1;continue
        if dietary and (not item.get("dietary_verified") or not set(dietary).issubset(item.get("dietary_certifications",[]))):
            rejected["饮食安全条件未经核实"]+=1;continue
        price=item.get("price")
        if price is None:rejected["价格未知"]+=1;continue
        if price>budget:rejected["超过硬预算"]+=1;continue
        if item.get("available") is False:rejected["商品停售"]+=1;continue
        if item.get("available") is not True:rejected["商品在售状态未知"]+=1;continue
        # Demo fallback is deliberately separate from the factual POI location.
        position=poi.get("location")
        walking_source="distance_estimate"
        def walking(origin,target):
            for row in catalog.get("walking_times",[]):
                if row.get("from")==origin["id"] and row.get("to")==poi["id"]:
                    return row["minutes"],row["source"]
            return math.ceil(math.hypot(origin["x"]-target["x"],origin["y"]-target["y"])*config["detour_factor"]/config["walk_metres_per_minute"]), "distance_estimate"
        if position:
            walk,walking_source=walking(current,position)
            back=math.ceil(math.hypot(destination["x"]-position["x"],destination["y"]-position["y"])*config["detour_factor"]/config["walk_metres_per_minute"]) if destination else 0
        elif mode=="demo":
            walk,back=8,8 if destination else 0
            walking_source="simulated"
        else:rejected["坐标未知"]+=1;continue
        state=crowd.get(shop["id"],at.isoformat())
        if mode!="demo" and state.get("source")=="simulated":
            rejected["真实排队数据未接入"]+=1;continue
        if not state.get("available"):
            rejected["当前服务不可用"]+=1;continue
        if state["queue_minutes"]>maximum:rejected["排队超过上限"]+=1;continue
        serving=item.get("serving_minutes")
        if serving is None:rejected["出餐时间未知"]+=1;continue
        hours=shop.get("opening_hours") or poi.get("opening_hours")
        hours_source=shop.get("hours_source",poi.get("hours_source","unknown"))
        if hours is None and mode=="demo":
            hours=[["06:00","23:00"]];hours_source="simulated"
        service=state["queue_minutes"]+serving
        if open_at(hours,at+timedelta(minutes=walk),service) is not True:
            rejected["到店及取餐时段不可用"]+=1;continue
        total=walk+service+config["meal_minutes"]+back+config["buffer_minutes"]
        if total>available:rejected["上课前时间不足"]+=1;continue
        parts=dict(taste=len(tags.intersection(taste))/len(taste) if taste else .5,
                   budget=max(0,1-price/max(budget,1)),queue=1-state["queue_minutes"]/max(maximum,1),
                   distance=1/(1+walk/10),preference=len(tags.intersection(likes))/len(likes) if likes else .5)
        score=sum(parts[key]*weight for key,weight in config["weights"].items())
        price_label="样例价格" if item.get("price_source",item["source"])=="simulated" else "记录价格"
        queue_label="模拟排队" if state.get("source")=="simulated" else "观测排队"
        reasons=[f"{price_label} ¥{price} ≤ 预算 ¥{budget}",f"{queue_label} {state['queue_minutes']} 分钟",
                 f"估算总用时 {total} 分钟，含下一课堂步行及 {config['buffer_minutes']} 分钟缓冲"]
        if tags.intersection(taste):reasons.insert(0,"匹配口味："+ "、".join(sorted(tags.intersection(taste))))
        candidates.append(dict(poi_id=poi["id"],poi=poi["name"],shop_id=shop["id"],shop=shop["name"],
            item_id=item["id"],item=item["name"],price=price,score=round(score,6),score_parts=parts,
            walking_minutes=walk,return_walking_minutes=back,queue_minutes=state["queue_minutes"],
            total_estimated_minutes=total,reason=reasons,location=position,building_id=poi.get("building_id"),
            address=poi.get("address",""),zone=poi.get("zone"),image_url=item.get("image_url"),
            field_evidence=dict(poi=poi.get("field_evidence",{}),shop=shop.get("field_evidence",{}),item=item.get("field_evidence",{})),
            sources=dict(poi=poi["source"],item=item["source"],price=item.get("price_source",item["source"]),
                         walking=walking_source,queue=state["source"],opening_hours=hours_source),
            simulation=any(s=="simulated" for s in (item["source"],state["source"],walking_source,hours_source)),
            feasibility="demo_estimate_not_verified" if mode=="demo" else "estimated_from_verified_inputs",dynamic_state=state))
    candidates.sort(key=lambda r:(-r["score"],r["price"],r["item_id"]))
    selected=[];seen=set()
    for row in candidates:
        if row["shop_id"] in seen:continue
        seen.add(row["shop_id"]);row["rank"]=len(selected)+1;selected.append(row)
        if len(selected)==int(k):break
    return dict(recommendations=selected,rejected=dict(rejected),candidate_count=len(candidates),
        mode=mode,available_minutes=available,notice="演示窗口、商品、排队为模拟；时间可行性仅为估算。" if mode=="demo" else "仅返回已核验事实；当前真实动态接口尚未接入。")
