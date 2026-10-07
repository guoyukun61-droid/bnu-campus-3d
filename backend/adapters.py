"""Adapters expose normalized data, not third-party wire formats."""
import hashlib
import sqlite3
import json
from contextlib import closing
from datetime import timedelta
from .storage import ROOT, read, timestamp, TZ
from .schemas import validate_catalog

class CatalogAdapter:
    def __init__(self, directory, legacy_db=None):
        self.directory = directory
        self.legacy_db = legacy_db

    def snapshot(self):
        result=read(self.directory/"catalog.json")
        if result is None:
            raise ValueError("数据未初始化，请执行 python -m backend.bootstrap")
        validate_catalog(result)
        result = json.loads(json.dumps(result))
        # Explicit identity map: no fuzzy auto-merge of different branches.
        identity={"baidu-373cf757b9861d774354d750":"lanhui"}
        existing={p["id"]:p for p in result["pois"]}
        if self.legacy_db and self.legacy_db.exists():
            with closing(sqlite3.connect(self.legacy_db.resolve().as_uri()+"?mode=ro",uri=True)) as connection:
                rows=[json.loads(r[0]) for r in connection.execute("SELECT payload FROM records")]
            for row in rows:
                pid=identity.get(row["id"],row["id"])
                if pid in existing:
                    p=existing[pid]
                    p["legacy_record_id"]=row["id"]
                    p["legacy_revision"]=row.get("revision")
                    p["status"]=row["status"]
                    p["location"]={"x":row["x"],"y":row["y"]}
                    p["location_source"]="legacy_record_approximate"
                    p["building_id"]=row.get("building_id")
                    p["legacy_name"]=row["name"]
                    p["name"]=row["name"]
                    p["legacy_hours"]=row.get("hours","")
                    p["legacy_notes"]=row.get("notes","")
                    continue
                p=dict(id=pid,name=row["name"],category=row["category"],address=row.get("notes",""),
                    source=row["source"],status=row["status"],building_id=row.get("building_id"),
                    floor=row.get("floor",""),location={"x":row["x"],"y":row["y"]},
                    location_crs="local EPSG:32650",location_source="legacy_record_approximate",
                    zone="unknown",opening_hours=None,hours_source="unknown",
                    legacy_record_id=row["id"],legacy_revision=row.get("revision"),access_scope="unknown")
                result["pois"].append(p)
                existing[pid]=p
        # Imported snapshots do not overwrite curated or manually edited records.
        for p in read(self.directory/"baidu_normalized.json",[]):
            if p["id"] in identity and identity[p["id"]] in existing:
                continue
            if p["id"] not in existing:
                result["pois"].append(p)
                existing[p["id"]]=p
        # Each independently identified merchant gets a Shop, not a fabricated menu.
        linked={s["poi_id"] for s in result["shops"]}
        for p in result["pois"]:
            if p["id"] not in linked and p.get("source")=="baidu_place_v2" and p.get("category") in {
                "restaurant","coffee","drink","retail","service","finance"
            }:
                result["shops"].append(dict(id="shop-"+p["id"],poi_id=p["id"],name=p["name"],
                    floor=p.get("floor",""),source=p["source"],source_uid=p.get("source_uid"),
                    retrieved_at=p.get("retrieved_at"),status=p["status"],menu_status="missing"))
                linked.add(p["id"])
        from .contribution import overlay
        return overlay(result, read(self.directory/"contributions/state.json", {}))

class SimulatedCrowdAdapter:
    source="simulated"
    def get(self,shop_id,at):
        t=timestamp(at)
        seed=int(hashlib.sha256(shop_id.encode()).hexdigest()[:8],16)
        peak=11<=t.hour<13 or 17<=t.hour<19
        minutes=(seed%7)+(4 if peak else 0)
        return dict(shop_id=shop_id,queue_minutes=minutes,crowd_level=round(minutes/12,2),
                    available=True,source=self.source,valid_from=t.isoformat(),
                    valid_until=(t+timedelta(minutes=15)).isoformat())

class SimulatedScheduleAdapter:
    def get(self,user_id,date):
        if user_id not in {"demo-student-1","demo-student-2"}:
            raise ValueError("仅支持虚构 demo-student-1 / demo-student-2")
        timestamp(date+"T00:00:00+08:00")
        return [dict(id=f"{user_id}-{date}-{i}",user_id=user_id,name=name,location=location,
                     start=f"{date}T{start}:00+08:00",end=f"{date}T{end}:00+08:00",source="simulated")
                for i,(name,location,start,end) in enumerate([
                    ("模拟课程A","教八","10:00","11:40"),
                    ("模拟课程B","教九","13:30" if user_id.endswith("1") else "12:30","15:10")])]

class MeituanAdapter:
    configured=False
    def items(self,*args,**kwargs):
        raise ValueError("美团正式接口未配置；请使用明确标注的模拟商品")

class SimulatedMenuAdapter:
    source="simulated"
    def items(self,catalog):
        return [i for i in catalog["items"] if i["source"]==self.source]
