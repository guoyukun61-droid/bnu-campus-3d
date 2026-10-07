"""Read-only catalog audit, export candidates separately from published records."""
from pathlib import Path
from shapely.geometry import Polygon, box
from .storage import ROOT, read, write
from .adapters import CatalogAdapter

SOURCES={
 'snack_area':'https://zhyqb.bnu.edu.cn/docs/2022-03/0373a9b72e0348f3b7ad59c9775cb7e5.pdf',
 'snack_names':'https://phil.bnu.edu.cn/xsyd/hdkx/137559.html',
 'south_57':'https://espre.bnu.edu.cn/docs/2021-09/20210916092426513123.pdf',
 'south_s':'https://nsem.bnu.edu.cn/xzzx/130622.htm',
 'gym':'https://iso.bnu.edu.cn/cn/facilities?cid=155&pid=24'}

def audit():
    assets=read(ROOT/'assets/campus_assets_white_v4.json')
    catalog=CatalogAdapter(ROOT/'data/life',ROOT/'data/campus_info.sqlite3').snapshot()
    rough=box(-460,-1000,100,-490);display=box(-452,-601,452,601)
    south=[]
    for b in assets['buildings']:
        p=Polygon(b['coords'])
        if not rough.covers(p.centroid):continue
        south.append(dict(building_id=b['osm_id'],name=b['name'],location=dict(x=round(p.centroid.x,2),y=round(p.centroid.y,2)),model_floors=b.get('floors'),model_height=b.get('height'),bounds=list(p.bounds),outside_display_m2=round(p.difference(display).area,2),status='ownership_and_identity_unverified',notice='矩形初筛不代表南院边界；既有体块不应重复补建'))
    names=['小米鸡排','干荷煎饼','彩棠里米粉','好这口老麻抄手']
    snack=[]
    for name in names:
        matches=[{k:p.get(k) for k in ('id','name','address','location','building_id')} for p in catalog['pois'] if name in p['name']]
        snack.append(dict(name=name,existing_matches=matches,source=SOURCES['snack_area'] if name in names[:2] else SOURCES['snack_names'],status='current_business_and_exact_position_unverified',coordinates=None,building_floors=None,notice='历史资料线索；不将相似名字的校外分店自动合并'))
    surfaces=[]
    for s in assets['surfaces']:
        if s['osm_id'] not in (267948582,267948583):continue
        p=Polygon(s['coords']);assert p.is_valid and p.area>0 and display.covers(p)
        overlaps=[dict(building_id=b['osm_id'],area_m2=round(p.intersection(Polygon(b['coords'])).area,3)) for b in assets['buildings'] if p.intersection(Polygon(b['coords'])).area>.01]
        surfaces.append(dict(osm_id=s['osm_id'],name=s['name'] or '未命名运动场地',area_m2=round(p.area,2),building_overlaps=overlaps,display_restored=True,current_sport_verified=False))
    return dict(audited_at='2026-09-24',coordinate_frame='white_v4 local EPSG:32650',sources=SOURCES,counts=dict(south_candidates=len(south),south_partial_outside=sum(s['outside_display_m2']>0 for s in south),snack_candidates=len(snack)),sports=surfaces,south_candidates=south,snack_candidates=snack,
                height_evidence=[dict(name='南院57号实验楼',above_ground_floors=4,below_ground_floors=0,source=SOURCES['south_57'],source_location='PDF第5页（印刷页2）',source_status='2021历史文件',building_id=None,total_height_m=None,status='pending_mesh_match_and_current_verification'),dict(name='邱季端体育馆',main_above_ground_floors=1,main_below_ground_floors=1,annex_above_ground_floors=2,source=SOURCES['gym'],total_height_m=None,status='split_main_annex_semantics_not_applied_to_geometry')],
                publication='audit_only_no_catalog_or_sqlite_changes')

if __name__=='__main__':
    result=audit();dest=ROOT/'data/life/map-audit/2026-09-24.json'
    if dest.exists():raise FileExistsError('Audit exists; do not overwrite')
    write(dest,result)
    print(result['counts']);print(result['sports'])
