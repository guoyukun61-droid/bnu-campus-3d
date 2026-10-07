"""HTTP-independent application boundary."""
from collections import Counter
from .storage import ROOT, read, now
from .adapters import CatalogAdapter, SimulatedScheduleAdapter, SimulatedCrowdAdapter
from .library import SimulatedLibraryAdapter
from .recommendation import recommend

class LifeService:
    def __init__(self,directory=None,legacy_db=None):
        self.directory=directory or ROOT/"data/life"
        self.catalog=CatalogAdapter(self.directory,legacy_db)
        self.library=SimulatedLibraryAdapter(self.directory)
        self.crowd=SimulatedCrowdAdapter()
        self.schedule=SimulatedScheduleAdapter()

    def coverage(self):
        catalog=self.catalog.snapshot()
        collection=read(self.directory/"collection.json",{})
        tasks=collection.get("tasks",[])
        leaves=[t for t in tasks if t["status"]!="split"]
        counts=Counter(t["status"] for t in leaves)
        pois=catalog["pois"]
        real_items=sum(i.get("source")!="simulated" for i in catalog["items"])
        return dict(generated_at=now(),known_venues=len(pois),
            simulated_shops=len([s for s in catalog["shops"] if s["source"]=="simulated"]),
            simulated_items=len([i for i in catalog["items"] if i["source"]=="simulated"]),
            real_world_completeness=None,real_world_complete=False,
            real_items=real_items,
            photo_menu_items=sum(i.get("source")=="menu_photo" for i in catalog["items"]),
            providers={"meituan":"not_configured","menu":"mixed_real_and_simulated" if real_items else "simulated","crowd":"simulated","schedule":"simulated","library":"simulated"},
            collection_status=collection.get("run_status","not_started"),
            collection_notice=("百度当日配额超限（302），断点已保存，待配额恢复后续采"
                if any(t.get("error")=="api_302" for t in leaves)
                else collection.get("run_status","not_started")),
            query_geometry=collection.get("query_geometry","bounds"),
            requests_total=collection.get("requests_total",0),
            unfinished_tasks=[{k:t.get(k) for k in ("id","query","bounds","page","status","error","total")} for t in leaves if t["status"]!="complete"],
            tasks=dict(counts),total_leaf_tasks=len(leaves),completed_tasks=counts["complete"],
            known_catalog_records=len(read(self.directory/"catalog.json",{"pois":[]})["pois"]),
            missing_coordinates=[p["id"] for p in pois if p.get("location") is None],
            missing_hours=[p["id"] for p in pois if not p.get("opening_hours")],
            pending_duplicates=read(self.directory/"possible_duplicates.json",[]),
            update_candidates=read(self.directory/"update_candidates.json",[]),
            gaps=catalog.get("gaps",[]),dispositions=read(self.directory/"dispositions.json",[]),
            notice="名录收录不等于现实全店覆盖；未现场核对，百度增量采集状态单独计量。")

    def get(self,path,query):
        one=lambda name,default=None:query.get(name,[default])[0]
        if path=="/coverage":return self.coverage()
        if path=="/schedule":
            return dict(records=self.schedule.get(one("user_id","demo-student-1"),one("date",now()[:10])),source="simulated")
        if path=="/library/slots":return dict(records=self.library.slots(one("start"),one("end")),source="simulated")
        if path=="/library/reservations":return dict(records=self.library.reservations(one("user_id")),source="simulated")
        data=self.catalog.snapshot()
        if path=="/locations":return dict(records=data["locations"])
        if path=="/dynamic-state":
            ids={s["id"] for s in data["shops"]}
            sid=one("shop_id")
            if sid is not None and sid not in ids:raise ValueError("shop_id 不存在")
            return dict(records=[SimulatedCrowdAdapter().get(s,one("at",now())) for s in sorted(ids) if not sid or s==sid],source="simulated")
        collections={"/pois":"pois","/shops":"shops","/items":"items"}
        if path not in collections:raise KeyError("Unknown endpoint")
        rows=data[collections[path]]
        pois={p["id"]:p for p in data["pois"]};shops={s["id"]:s for s in data["shops"]}
        def match(row):
            shop=shops.get(row.get("shop_id"),row)
            poi=pois.get(shop.get("poi_id"),row)
            checks={"category":row.get("category",poi.get("category")),"zone":poi.get("zone"),
                    "poi_id":shop.get("poi_id",poi.get("id")),"shop_id":row.get("shop_id",shop.get("id")),
                    "building_id":poi.get("building_id"),"source":row.get("source"),"status":row.get("status")}
            return all(one(key) is None or str(value)==one(key) for key,value in checks.items()) and (one("q","").casefold() in row["name"].casefold())
        return dict(records=[r for r in rows if match(r)],schema_version=1)

    def post(self,path,data):
        if not isinstance(data,dict):raise ValueError("请求必须是JSON对象")
        if path=="/recommendations":return recommend(self.catalog.snapshot(),data,self.crowd)
        if path=="/library/reservations":return self.library.reserve(data)
        if path.startswith("/library/reservations/") and path.endswith("/cancel"):
            parts=path.strip("/").split("/")
            if len(parts)==4:return self.library.cancel(parts[2],data.get("user_id"))
        raise KeyError("Unknown endpoint")
