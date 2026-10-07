"""Single-writer, reviewed contributions; no writes or credentials at import time."""
import copy
import hashlib
import math
import re
import secrets
import threading
import io
from datetime import timedelta
from .storage import read, write, now, timestamp
from .schemas import validate_catalog


def digest(value):
    import json
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def overlay(catalog, state):
    result = copy.deepcopy(catalog)
    for kind, records in state.get("published", {}).items():
        index = {r["id"]: r for r in result[kind]}
        for ident, patch in records.items():
            if ident in index:
                # A partial publication must not erase evidence for untouched fields.
                evidence = copy.deepcopy(index[ident].get("field_evidence", {}))
                evidence.update(copy.deepcopy(patch.get("field_evidence", {})))
                index[ident].update(copy.deepcopy(patch))
                if evidence:
                    index[ident]["field_evidence"] = evidence
            else:
                result[kind].append(copy.deepcopy(patch))
    return validate_catalog(result)


class Conflict(ValueError):
    pass


class ContributionStore:
    """One process owns this store. A bound server port prevents duplicate writers."""
    def __init__(self, directory, catalog):
        self.directory, self.catalog = directory, catalog
        self.path = directory / "state.json"
        self.lock = threading.RLock()

    def state(self):
        return read(self.path, dict(submissions={}, published={}, attachments={}, claims={}, audit=[], version=0))

    def entities(self):
        return self.catalog.snapshot()

    def credential(self, token):
        # Credentials are provisioned separately after explicit owner approval.
        users = read(self.directory / "members.json", [])
        key = hashlib.sha256(token.encode()).hexdigest()
        for user in users:
            if user.get("active") and secrets.compare_digest(user.get("token_hash", ""), key):
                return {k: user[k] for k in ("id", "name", "role")}
        raise PermissionError("邀请凭证无效或已撤销")

    def active(self, user):
        return any(u.get("active") and u.get("id") == user["id"] and u.get("role") == user["role"]
                   for u in read(self.directory / "members.json", []))

    def records(self, user):
        with self.lock:
            return [copy.deepcopy(s) for s in self.state()["submissions"].values()
                    if user["role"] == "admin" or s["author_id"] == user["id"]]

    def claim(self, user, entity_id):
        if entity_id not in {p["id"] for p in self.entities()["pois"]}:
            raise ValueError("地点不存在")
        with self.lock:
            state = self.state()
            state["claims"][entity_id] = dict(name=user["name"], at=now(), expires_at=(timestamp(now())+timedelta(hours=24)).isoformat())
            write(self.path, state)
            return state["claims"][entity_id]

    def validate(self, data, user, state):
        kind = data.get("kind")
        if kind not in {"pois", "shops", "items"}: raise ValueError("对象类型无效")
        patch = data.get("patch")
        if not isinstance(patch, dict) or not patch: raise ValueError("至少填写一个修改字段")
        allowed = {
            "pois": {"name", "category", "address", "floor", "opening_hours", "business_status", "access_scope", "coordinates", "observation", "map_point", "building_floors", "floor_evidence", "location_description"},
            "shops": {"name", "poi_id", "floor", "opening_hours"},
            "items": {"name", "shop_id", "price", "tags", "specification", "sales_channel", "serving_minutes", "available"}}
        if set(patch) - allowed[kind]: raise ValueError("包含不允许修改的字段")
        if "map_point" in patch and "coordinates" in patch:raise ValueError("地图选点与经纬度不能同时提交，请保留一种")
        if "building_floors" in patch and patch.get("floor_evidence") not in {"observed","estimated"}:raise ValueError("填写总层数须说明现场确认或估计")
        for field, value in patch.items():
            if field == "map_point":
                if not isinstance(value,dict) or set(value)!={"x","y","building_id","crs","model"} or value.get("crs")!="local EPSG:32650" or value.get("model")!="white_v4":raise ValueError("地图坐标或模型版本无效")
                for axis,limit in (("x",452),("y",601)):
                    v=value.get(axis)
                    if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or abs(v)>limit:raise ValueError("选点超出当前模型范围")
                bid=value["building_id"]
                if bid is not None:
                    from .geo import CampusGeometry
                    from shapely.geometry import Point
                    if isinstance(bid,bool) or not isinstance(bid,int):raise ValueError("建筑ID无效")
                    shape=next((s for b,s in CampusGeometry().buildings if b==bid),None)
                    if shape is None or not shape.buffer(5).covers(Point(value["x"],value["y"])):raise ValueError("建筑与选点不匹配，请改选地面位置")
            elif field == "building_floors":
                if isinstance(value,bool) or not isinstance(value,int) or not 1<=value<=100:raise ValueError("建筑总层数须为1到100的整数")
            elif field == "floor_evidence":
                if value not in {"observed","estimated"}:raise ValueError("层数依据无效")
            elif field == "coordinates":
                if not isinstance(value,dict) or set(value)!={"lng","lat","crs"} or value.get("crs") not in {"WGS84","BD09"}: raise ValueError("坐标须含经纬度及WGS84/BD09坐标系")
                for k,limit in (("lng",180),("lat",90)):
                    v=value.get(k)
                    if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not -limit<=v<=limit:raise ValueError("经纬度无效")
            elif field in {"price", "serving_minutes"}:
                if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 10000):
                    raise ValueError("价格/耗时须为非负数或未知")
            elif field == "available":
                if not isinstance(value, bool): raise ValueError("商品状态须为布尔值")
            elif field == "tags":
                if not isinstance(value, list) or len(value)>20 or any(not isinstance(v,str) or len(v)>30 for v in value): raise ValueError("标签格式错误")
            elif field == "opening_hours":
                if value is not None and (not isinstance(value, list) or len(value)>8 or any(not isinstance(v,list) or len(v)!=2 or any(not isinstance(t,str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d",t) for t in v) for v in value)):
                    raise ValueError("营业时间格式应为 [[\"09:00\",\"21:00\"]] 或 null")
            elif not isinstance(value,str) or not value.strip() or len(value)>500:
                raise ValueError(field+" 须为非空短文本")
        if patch.get("category") and patch["category"] not in {"restaurant","coffee","drink","snack","canteen","retail","service","finance","building","other"}: raise ValueError("店铺类别无效")
        if patch.get("access_scope") and patch["access_scope"] not in {"public","student","staff","unknown"}: raise ValueError("准入条件无效")
        observed = timestamp(data.get("observed_at"))
        if observed.year<2000: raise ValueError("观察日期无效")
        if observed > timestamp(now()) + timedelta(minutes=5): raise ValueError("观察时间不能在未来")
        evidence = data.get("evidence")
        if not isinstance(evidence,str) or not 3<=len(evidence.strip())<=2000: raise ValueError("请填写来源链接或具体观察说明")
        attachments=data.get("attachments",[])
        if not isinstance(attachments,list) or len(attachments)>5: raise ValueError("最多5张证据图片")
        for ident in attachments:
            a=state["attachments"].get(ident)
            if not a or a["owner"]!=user["id"]: raise PermissionError("不能引用他人附件")
        catalog=self.entities()
        ident=data.get("entity_id")
        base=next((r for r in catalog[kind] if r["id"]==ident),None)
        if ident and base is None: raise ValueError("关联对象不存在")
        if base and base.get("source")=="simulated": raise ValueError("请新建真实窗口/商品，不覆盖模拟样例")
        if not base and not patch.get("name"): raise ValueError("新增记录必须填写名称")
        parent="poi_id" if kind=="shops" else "shop_id" if kind=="items" else None
        if parent:
            parent_id=patch.get(parent,(base or {}).get(parent))
            candidates=catalog["pois" if kind=="shops" else "shops"]
            match=next((r for r in candidates if r["id"]==parent_id),None)
            if not match or match.get("source")=="simulated": raise ValueError("请选择真实父级地点/店铺")
        if base and data.get("base_revision")!=digest(base): raise Conflict("正式记录已改变，请重新选择记录并核对差异")
        return kind, patch, base

    def submit(self,user,data):
        if not isinstance(data,dict): raise ValueError("请求须为对象")
        key=data.get("request_id")
        if not isinstance(key,str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}",key): raise ValueError("缺少有效幂等请求ID")
        with self.lock:
            state=self.state()
            request_hash=digest(data)
            request_key=user["id"]+":"+key
            receipt=state.get("receipts",{}).get(request_key)
            if receipt:
                if receipt["hash"]!=request_hash:raise Conflict("同一请求ID不能用于不同内容")
                return receipt["result"]
            for record in state["submissions"].values():
                if record["author_id"]==user["id"] and record["request_id"]==key:
                    if record["request_hash"]!=request_hash: raise Conflict("同一请求ID不能用于不同内容")
                    return record
            kind,patch,base=self.validate(data,user,state)
            ident=data.get("submission_id")
            previous=state["submissions"].get(ident) if ident else None
            if ident:
                if not previous or previous["author_id"]!=user["id"]: raise PermissionError("不能修改他人提交")
                if previous["status"] not in {"draft","needs_info"}: raise Conflict("此提交不可编辑")
                if data.get("revision")!=previous["revision"]: raise Conflict("提交版本冲突")
            ident=ident or "submission-"+secrets.token_hex(12)
            record=dict(id=ident,kind=kind,entity_id=data.get("entity_id"),base_revision=digest(base) if base else None,
                        base=base,patch=patch,evidence=data["evidence"],observed_at=data["observed_at"],
                        attachments=data.get("attachments",[]),author_id=user["id"],author=user["name"],
                        request_id=key,request_hash=request_hash,status="draft" if data.get("draft") else "submitted",
                        revision=(previous or {}).get("revision",0)+1,updated_at=now())
            state["submissions"][ident]=record
            state.setdefault("receipts",{})[request_key]=dict(hash=request_hash,result=copy.deepcopy(record))
            state["audit"].append(dict(action=record["status"],submission_id=ident,at=now(),actor=user["id"],record=copy.deepcopy(record)))
            write(self.path,state)
            return record

    def review(self,user,data):
        if user["role"]!="admin": raise PermissionError("仅管理员可审核")
        action=data.get("action")
        if action not in {"approved","rejected","needs_info"}: raise ValueError("审核动作无效")
        note=data.get("note","")
        if not isinstance(note,str) or len(note)>2000: raise ValueError("审核意见无效")
        if action!="approved" and not note.strip(): raise ValueError("请说明退回或拒绝原因")
        with self.lock:
            state=self.state(); record=state["submissions"].get(data.get("id"))
            if not record: raise ValueError("提交不存在")
            if record["status"]==action and record.get("reviewed_revision")==data.get("revision"): return record
            if record["status"]!="submitted" or record["revision"]!=data.get("revision"): raise Conflict("审核版本或状态已变化")
            if action=="approved":
                catalog=self.entities(); kind=record["kind"]
                current=next((r for r in catalog[kind] if r["id"]==record["entity_id"]),None)
                if (digest(current) if current else None)!=record["base_revision"]: raise Conflict("正式记录发生变化，须退回重新核对")
                if current is None and any(r.get("name")==record["patch"].get("name") for r in catalog[kind]) and data.get("allow_distinct") is not True:
                    raise Conflict("存在同名记录；确认地址/楼层为独立分店后勾选同名不同店")
                ident=record["entity_id"] or "field-"+record["id"]
                patch=copy.deepcopy(state["published"].get(kind,{}).get(ident,{}))
                if current is None:
                    patch.update(id=ident,source="field_observation",status="verified")
                    if kind=="pois": patch.update(zone="unknown",location=None,building_id=None,access_scope="unknown",scope_status="pending",category="other",opening_hours=None)
                    if kind=="items": patch.update(tags=[],price=None,available=False,serving_minutes=None)
                patch.update(record["patch"])
                if kind=="pois" and "map_point" in record["patch"]:
                    from .geo import CampusGeometry
                    point=record["patch"]["map_point"]
                    position={k:point[k] for k in ("x","y")}
                    zone,_,distance=CampusGeometry().classify(position)
                    category=patch.get("category",(current or {}).get("category"))
                    in_scope=zone=="campus" or (zone=="nearby" and category in {"restaurant","coffee","drink","snack","canteen"})
                    patch.update(location=position,location_crs=point["crs"],location_source="reviewed_model_pick",building_id=point["building_id"],zone=zone,scope_status="confirmed" if in_scope else "outside",distance_to_campus_m=distance)
                if kind=="pois" and "coordinates" in record["patch"]:
                    from .geo import CampusGeometry
                    geo=CampusGeometry();coords=record["patch"]["coordinates"]
                    if coords["crs"]=="BD09":
                        position,_=geo.bd_to_local(coords)
                    else:
                        x,y=geo.to_metric.transform(coords["lng"],coords["lat"])
                        position=dict(x=round(x-geo.ox,2),y=round(y-geo.oy,2))
                    zone,_,distance=geo.classify(position)
                    category=patch.get("category",(current or {}).get("category"))
                    in_scope=zone=="campus" or (zone=="nearby" and category in {"restaurant","coffee","drink","snack","canteen"})
                    patch.update(location=position,location_crs="local EPSG:32650",location_source="field_coordinate_approximate",zone=zone,building_id=None,scope_status="confirmed" if in_scope else "outside",distance_to_campus_m=distance)
                provenance=patch.setdefault("field_evidence",{})
                for field in record["patch"]:
                    provenance[field]=dict(source="field_observation",observed_at=record["observed_at"],evidence=record["evidence"],submission_id=record["id"],reviewed_at=now())
                if "opening_hours" in record["patch"]: patch["hours_source"]="field_observation"
                if "price" in record["patch"]: patch["price_source"]="field_observation"
                patch["updated_at"]=now()
                state["published"].setdefault(kind,{})[ident]=patch
                overlay(catalog,state) # validate all relationships before committing
                record["published_id"]=ident; state["version"]+=1
            record.update(status=action,reviewer=user["name"],review_note=note,reviewed_at=now(),reviewed_revision=record["revision"],revision=record["revision"]+1)
            state["audit"].append(dict(action=action,submission_id=record["id"],at=now(),actor=user["id"],version=state["version"],note=note))
            # Status + audit + publication are a single atomic commit.
            write(self.path,state)
            return record

    def upload(self,user,raw,mime):
        if not 0<len(raw)<=3*1024*1024: raise ValueError("图片大小须在3MB以内")
        good=(mime=="image/png" and raw.startswith(b"\x89PNG\r\n\x1a\n")) or (mime=="image/jpeg" and raw.startswith(b"\xff\xd8\xff") and raw.endswith(b"\xff\xd9"))
        if not good: raise ValueError("仅接收 PNG/JPEG 图片，不接受 SVG/HTML")
        from PIL import Image, UnidentifiedImageError
        try:
            with Image.open(io.BytesIO(raw)) as img:
                if img.width*img.height>20_000_000:raise ValueError("图片像素超过2000万")
                img.verify()
            with Image.open(io.BytesIO(raw)) as img:
                clean=io.BytesIO();img.convert("RGB").save(clean,format="JPEG",quality=90)
                raw=clean.getvalue();mime="image/jpeg" # strip EXIF, GPS and appended content
        except (UnidentifiedImageError,OSError,Image.DecompressionBombError) as exc:
            raise ValueError("图片无法解码，请上传有效JPEG/PNG") from exc
        with self.lock:
            state=self.state()
            own=[a for a in state["attachments"].values() if a["owner"]==user["id"]]
            if sum(a["size"] for a in own)+len(raw)>100*1024*1024: raise ValueError("个人附件总额已达100MB，请联系管理员")
            ident=secrets.token_hex(16)
            self.directory.joinpath("attachments").mkdir(parents=True,exist_ok=True)
            with self.directory.joinpath("attachments",ident).open("xb") as f:
                import os
                f.write(raw);f.flush();os.fsync(f.fileno())
            state["attachments"][ident]=dict(owner=user["id"],mime=mime,size=len(raw),at=now())
            write(self.path,state)
            return dict(id=ident)

    def attachment(self,user,ident):
        with self.lock:
            meta=self.state()["attachments"].get(ident)
            if not meta or (meta["owner"]!=user["id"] and user["role"]!="admin"): raise PermissionError("附件不可访问")
            return self.directory.joinpath("attachments",ident).read_bytes(),meta["mime"]
