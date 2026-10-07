"""Explicit, idempotent materialization; never updates the legacy database."""
from .storage import ROOT, now, read, write
from .seeds.catalog import VENUES, DISHES, GUIDE

def build_catalog():
    assets = read(ROOT / "assets/campus_assets_white_v4.json")
    buildings = {b["osm_id"]: b for b in assets["buildings"]}
    pois, shops, items, gaps = [], [], [], []
    for n, (pid, name, address, category, hours, bid, floor, source, access) in enumerate(VENUES):
        b = buildings.get(bid)
        xy = {axis: round(sum(p[i] for p in b["coords"])/len(b["coords"]),2)
              for i,axis in enumerate(("x","y"))} if b else None
        zone = "nearby" if pid in {"bayi","xiang","ziguang"} else "affiliated" if pid=="canteen-7" else "campus"
        if pid == "jitian": zone = "unknown"
        poi = dict(id=pid, name=name, address=address, category=category, zone=zone,
                   location=xy, location_crs="local EPSG:32650" if xy else None,
                   location_source="model_building_centroid_approximate" if xy else "unknown",
                   building_id=bid, floor=floor, opening_hours=hours,
                   hours_source=source if hours else "unknown", source=source,
                   retrieved_at=now(), status="unverified", access_scope=access,
                   aliases=["教工四食堂"] if pid=="lanhui" else [], source_uid=None)
        pois.append(poi)
        if category in {"restaurant","coffee"}:
            shops.append(dict(id="shop-"+pid,poi_id=pid,name=name,floor=floor,
                              source=source,status="unverified",opening_hours=hours))
        missing = [key for key, value in (("坐标",xy),("分时营业时间",hours)) if value is None]
        gaps.append(dict(poi_id=pid, name=name, missing=missing+["逐窗口名录","真实菜单价格","现场营业核验"]))
        # Only dining venues receive synthetic demo service counters; these are not real shops.
        if category in {"canteen","restaurant"}:
            sid = "demo-counter-" + pid
            shops.append(dict(id=sid,poi_id=pid,name="演示窗口（虚构）",floor=floor,
                              source="simulated",status="demo",opening_hours=None))
            for j,(dish, price, tags) in enumerate(DISHES):
                items.append(dict(id=f"demo-{pid}-{j:02}",shop_id=sid,name=dish+"（样例）",
                    price=price,tags=tags,source="simulated",price_source="simulated",
                    available=True,serving_minutes=2+j%3,image_url=None,image_kind="placeholder",
                    dietary_verified=False))
    locations=[]
    for name, bid in (("教八",267948025),("教九",267948024),("图书馆",267944894)):
        b=buildings[bid]
        locations.append(dict(id=name,name=name,building_id=bid,source="model_centroid_approximate",
            x=sum(p[0] for p in b["coords"])/len(b["coords"]),
            y=sum(p[1] for p in b["coords"])/len(b["coords"])))
    return dict(schema_version=1,created_at=now(),pois=pois,shops=shops,items=items,
                locations=locations,gaps=gaps,walking_times=[],
                provenance_note="店名来自资料；演示窗口、菜品、价格均为模拟，不计入真实店铺完整率。")

def initialize(directory=None):
    directory = directory or ROOT/"data/life"
    target = directory/"catalog.json"
    if not target.exists():
        write(target,build_catalog())
    else:
        # Add missing source-backed shop identities; never overwrite existing rows.
        current=read(target)
        known={s["id"] for s in current["shops"]}
        additions=[s for s in build_catalog()["shops"] if s["id"] not in known]
        if additions:
            current["shops"].extend(additions);write(target,current)
    if not (directory/"reservations.json").exists():
        write(directory/"reservations.json",[])
    return read(target)

if __name__=="__main__":
    c=initialize()
    print(f"Catalog: {len(c['pois'])} source-backed venues, {len(c['items'])} simulated menu samples.")
