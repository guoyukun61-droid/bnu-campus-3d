import json,datetime
from pathlib import Path
from shapely.geometry import Polygon
from shapely.ops import unary_union
import campus_server as api
ROOT=Path(__file__).resolve().parent
patch=json.loads((ROOT/'assets/missing_blocks_v4.json').read_text(encoding='utf-8'))
old=json.loads((ROOT/'assets/campus_assets_white_v3.json').read_text(encoding='utf-8'))
report=[]
for b in patch['buildings']:
    shapes=[Polygon(p['coords']) for p in b['parts']]
    assert all(p.is_valid and p.area>0 for p in shapes)
    shape=unary_union(shapes)
    overlaps=[{'id':v['osm_id'],'area':round(shape.intersection(Polygon(v['coords'])).area,3)} for v in old['buildings'] if shape.intersection(Polygon(v['coords'])).area>.1]
    assert not overlaps,overlaps
    assert sum(p.area for p in shapes)-shape.area<.1,'Overlapping new parts'
    report.append({'id':b['osm_id'],'area':round(shape.area,1),'existing_building_overlaps':overlaps})
context=json.loads((ROOT/'assets/campus_context.json').read_text(encoding='utf-8'))
for b in patch['buildings']:
    context['buildings'][str(b['osm_id'])]={'classification':'inside','overlap_fraction':1,'source':'用户确认校内区域；截图+影像补建，非产权测绘'}
context['counts']['inside']+=len(patch['buildings']);context['version']='white-v4'
(ROOT/'assets/campus_context_v4.json').write_text(json.dumps(context,ensure_ascii=False,indent=2),encoding='utf-8')
links={'373cf757b9861d774354d750':900000000001,'e762ab2776f6abf5f6c59c56':900000000002,'4e08aaa67e8a30b0843304ac':900000000002,'446e5e56f3daa2d5ea12e475':900000000002}
updated=0
with api.connect() as c:
    for uid,bid in links.items():
        stored=c.execute('SELECT * FROM records WHERE id=?',('baidu-'+uid,)).fetchone()
        if not stored:continue
        row=json.loads(stored['payload'])
        if row.get('building_id') is not None or row['revision']!=1:continue
        now=datetime.datetime.now(datetime.timezone.utc).isoformat()
        c.execute('INSERT INTO history VALUES(?,?,?,?)',(row['id'],row['revision'],stored['payload'],now))
        row.update(building_id=bid,revision=row['revision']+1,updated_at=now)
        row['notes']+=' 2026-09-21：依据用户百度截图与GF2区域对应，关联本地补建建筑/组团；不是逐楼门牌实测。'
        row['tags']=[t for t in row.get('tags',[]) if t!='独立点位']+['截图参照补建','组团关联待核']
        c.execute('UPDATE records SET revision=?,payload=? WHERE id=?',(row['revision'],json.dumps(row,ensure_ascii=False),row['id']));updated+=1
(ROOT/'output/white_v4_spatial_checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'checks':report,'poi_links_updated':updated}))
