"""Reviewed UID allowlist; approximate conversion, conservative building links.
pip dependencies: eviltransform==0.1.1 pyproj shapely
Never rename source OSM buildings or infer footprints/heights from POIs.
"""
import json
import datetime
from pathlib import Path
import eviltransform
from pyproj import Transformer
from shapely.geometry import Point, Polygon
import campus_server as api

ROOT = Path(__file__).resolve().parent
REVIEWED = {
    '373cf757b9861d774354d750': ('canteen', '2楼'),
    '64f5e271343868c7128824b5': ('building', ''),
    'e8a3ac7102db225cad04571f': ('building', ''),
    '9d05817c550c0a563b221c57': ('building', ''),
    'e762ab2776f6abf5f6c59c56': ('building', ''),
    '4e08aaa67e8a30b0843304ac': ('building', ''),
    '446e5e56f3daa2d5ea12e475': ('building', ''),
    '0a797dc744af32e1774ff184': ('canteen', ''),
    '86150cb7fe4f85c41f389433': ('building', ''),
    'a31ffae3c2524c5b6140a9de': ('building', ''),
    'ed209310ccb7ad6f0bf5eb8a': ('other', ''),
    'be3e817cbfd2ba2c2b3a9fd9': ('snack', ''),
}

def prepare():
    assets = json.loads((ROOT/'assets/campus_assets_white_v3.json').read_text(encoding='utf-8'))
    audit = json.loads((ROOT/'data/baidu_poi_audit_20260921.json').read_text(encoding='utf-8'))
    tx = Transformer.from_crs(4326, 32650, always_xy=True)
    ox, oy = assets['coordinate_system']['origin_utm']
    shapes = [(b, Polygon(b['coords']).buffer(0)) for b in assets['buildings']]
    seen, rows, report = set(), [], []
    for query in audit['queries']:
        for p in query['results']:
            uid = p['uid']
            if uid not in REVIEWED or uid in seen:
                continue
            seen.add(uid)
            lat, lon = eviltransform.bd2wgs(p['location']['lat'], p['location']['lng'])
            east, north = tx.transform(lon, lat)
            x, y = round(east-ox, 2), round(north-oy, 2)
            if abs(x)>452 or abs(y)>601:
                continue
            point = Point(x, y)
            contains = [b for b, shape in shapes if shape.covers(point)]
            # Overlaps and nearest-neighbour guesses remain unlinked.
            bid = contains[0]['osm_id'] if len(contains)==1 else None
            distance = min(shape.distance(point) for _, shape in shapes)
            category, floor = REVIEWED[uid]
            note = ('唯一轮廓包含点，暂关联建筑，仍需现场确认。' if bid else
                    '尚未可靠关联建筑；独立点位，不吸附最近楼。轮廓缺失/入口偏移均有可能。')
            row = dict(name=p['name'], category=category, x=x, y=y, building_id=bid,
                       source=f'百度 Place v2 / UID {uid} / 2026-09-21',
                       status='unverified', floor=floor, unit='', hours='', price='',
                       tags=['百度POI', '近似坐标', '建筑关联待核' if bid else '独立点位'],
                       notes=f"百度地址：{p.get('address', '')}。{note} BD-09经开源算法近似转换为WGS84，再投影UTM50N；非测量坐标。营业状态与楼高未核实。")
            rows.append({'id': 'baidu-'+uid, **api.validate(row)})
            report.append(dict(uid=uid, name=p['name'], original_bd09=p['location'],
                               x=x, y=y, building_id=bid, nearest_footprint_m=round(distance,2)))
    return rows, report

def main():
    rows, report = prepare()
    api.init()
    inserted = 0
    with api.connect() as c:
        for row in rows:
            row.update(revision=1, updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
            inserted += c.execute('INSERT OR IGNORE INTO records VALUES(?,?,?)',
                                 (row['id'], 1, json.dumps(row, ensure_ascii=False))).rowcount
    (ROOT/'data/baidu_poi_matching.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(reviewed=len(rows), inserted=inserted,
                         linked=sum(r['building_id'] is not None for r in rows),
                         independent=sum(r['building_id'] is None for r in rows))))

if __name__ == '__main__':
    main()
