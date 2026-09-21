"""Approximate main-campus context, not a legal ownership boundary."""
import json
from pathlib import Path
from shapely.geometry import Polygon
ROOT=Path(__file__).resolve().parent
data=json.loads((ROOT/'assets/campus_assets_white_v3.json').read_text(encoding='utf-8'))
# Traced against GF2 UTM display and user-labelled 2011/2012 campus map.
boundary=[[-424,325],[-405,-460],[-390,-469],[359,-469],[383,-444],[379,-220],[355,90],[337,340]]
poly=Polygon(boundary);assert poly.is_valid
classes={};counts={'inside':0,'outside':0,'uncertain':0}
for b in data['buildings']:
    shape=Polygon(b['coords']);shape=shape if shape.is_valid else shape.buffer(0)
    ratio=shape.intersection(poly).area/shape.area
    kind='inside' if poly.buffer(-8).covers(shape) else 'outside' if not poly.buffer(8).intersects(shape) else 'uncertain'
    classes[str(b['osm_id'])]={'classification':kind,'overlap_fraction':round(ratio,4)};counts[kind]+=1
gates=[]
for id,name,x,y in [('south','南门',45,-468),('east','东门',361,-46),('west','西门',-414,43),('north','北门',200,337),('small-west','小西门',-410,-333),('small-east','小东门',374,-377)]:
    gates.append({'id':'campus-gate-'+id,'name':name,'category':'gate','x':x,'y':y,'building_id':None,'source':'用户提供校园标注图（2011影像/2012制图）+ GF2 2025参考定位；2026-09-21整理','status':'unverified','notes':'主校区入口近似点位，不是测量坐标；名称、现位置、是否开放与通行规则待核实。','hours':'','price':'','tags':['校门','位置待核实']})
out={'version':'20260921','boundary':boundary,'boundary_source':'manual approximate trace: user historical campus map + existing GF2 UTM image','disclaimer':'按主校区范围分色，不表示产权。边界外也可能有学校附属区域；未确认建筑归属。','counts':counts,'buildings':classes,'gates':gates}
(ROOT/'assets/campus_context.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(counts));print('gates:',len(gates))

if __name__=='__main__':
    import campus_server as api
    import datetime
    api.init()
    with api.connect() as c:
        for gate in gates:
            row={**gate,'revision':1,'updated_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
            c.execute('INSERT OR IGNORE INTO records VALUES(?,?,?)',(row['id'],1,json.dumps(row,ensure_ascii=False)))
    print('Gate POIs inserted if missing; existing edits preserved.')
