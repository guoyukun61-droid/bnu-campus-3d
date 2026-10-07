"""Explicit spatial statements, not inferred shop-door coordinates. Dry run first."""
import copy
import csv
import hashlib
from pathlib import Path
from .storage import ROOT, read, write, now
from .adapters import CatalogAdapter
from .contribution import digest, overlay
from .import_field_batch import DIRECTORY

BATCH = 'snack-spatial-20261002'
LUCKIN = 'baidu-0f1888407b5b17632afc4855'
LAIXIFU_CANDIDATE = 'baidu-e01d5828d274ead49fec2b78'
COTTI = 'reported-cotti-northwest-campus'
PHOTO = Path('C:/Users/gyk11/AppData/Local/Temp/codex-clipboard-046565a3-6b16-4a73-bef2-9a67bb0d447b.jpg')
GROUPS = [('north-services','北段生活服务',0,2),
          ('snack-main','小吃街主排',2,15),
          ('south-second','南侧二层',15,18),
          ('xuewu-side','学五周边一组',18,24),
          ('northwest-west','西北食堂西侧餐厅组',24,29),
          ('tmall-services','天猫校园服务组',29,38)]


def representative(buildings, ident):
    from shapely.geometry import Polygon
    b = next(b for b in buildings if b['osm_id'] == ident)
    p = Polygon(b['coords']).representative_point()
    return dict(x=round(p.x, 3), y=round(p.y, 3), building_id=ident,
                crs='local EPSG:32650', model='white_v4')


def corrected_state(original, catalog, buildings, hours, at, photo_sha):
    if any(a.get('batch') == BATCH for a in original.get('audit', [])):
        raise ValueError('This spatial correction is already applied')
    state = copy.deepcopy(original)
    index = {p['id']: p for p in catalog['pois']}
    changed = []

    def put(kind, ident, patch, evidence):
        previous = next((r for r in catalog[kind] if r['id'] == ident), {})
        target = state.setdefault('published', {}).setdefault(kind, {}).setdefault(ident, {})
        for key, value in patch.items():
            target[key] = copy.deepcopy(value)
            target.setdefault('field_evidence', {})[key] = dict(
                source='user_spatial_report_20261002', evidence=evidence,
                previous_value=copy.deepcopy(previous.get(key)), reported_at=at,
                observed_at=None, reviewed_at=at, batch=BATCH,
                source_photo_sha256=photo_sha if '照片' in evidence else None)
        target['updated_at'] = at
        if kind == 'pois' and ident not in changed: changed.append(ident)

    def poi(ident, patch, evidence):
        if ident not in index: raise ValueError('Missing explicit POI: ' + ident)
        put('pois', ident, patch, evidence)
        # Keep independently identified Shop display fields in sync, not menus/prices.
        for shop in catalog['shops']:
            if shop['poi_id'] == ident and shop.get('source') != 'simulated':
                fields = {k: v for k, v in patch.items() if k in ('name', 'floor')}
                if fields: put('shops', shop['id'], fields, evidence)

    if '瑞幸' not in index[LUCKIN]['name'] or '瑞幸' not in index['luckin']['name']:
        raise ValueError('Luckin identity changed')
    for ident, bid, floor, name, address in [
        (LUCKIN, 499434918, '3', '瑞幸咖啡（新乐群三层店）', '新乐群食堂三层'),
        ('luckin', 172257586, '2', '瑞幸咖啡（科技楼二层店）', '科技楼二层大厅')]:
        poi(ident, dict(name=name, floor=floor, address=address, building_id=bid,
            display_anchor=dict(**representative(buildings, bid), precision='building',
                                label='已确认所在建筑；标记为楼栋代表点，非入口'),
            spatial_sequence=dict(group='luckin-branches', label='瑞幸 · 两处分店', order=1 if ident==LUCKIN else 2, direction='none')),
            '用户明确说明新乐群三层、科技楼二层分别有瑞幸；保留独立ID与原始坐标。')

    evidence = '用户确认来喜福与学五食堂在同一栋楼；未提供入口和楼层。百度同名记录仍作为疑似重复候选，未执行身份合并。'
    for ident in ('laixifu', LAIXIFU_CANDIDATE):
        poi(ident, dict(address='学五食堂同栋楼', building_id=499437078,
            location=None, map_point=None, location_source='user_building_only_20261002',
            display_anchor=dict(**representative(buildings,499437078), precision='building',
                                label='与学五食堂同楼；入口位置待补')),
            evidence)
    poi('laixifu', dict(aliases=list(dict.fromkeys(index['laixifu'].get('aliases',[])+['来西福炒鸡蛋','来喜福炒酸奶鸡蛋仔']))), evidence)

    if len(hours) != 38: raise ValueError('Hours inventory changed; review grouping')
    for group, label, start, end in GROUPS:
        for order, row in enumerate(hours[start:end], 1):
            ident = row['poi_id'] or 'reported-' + hashlib.sha256(row['name'].encode()).hexdigest()[:16]
            poi(ident, dict(spatial_sequence=dict(group=group, label=label, order=order, direction='north_to_south')),
                '用户说明之前营业时间表对应北到南分布；保留原分隔组内顺序，不推算入口坐标或组间道路拓扑。')

    ref = dict(**representative(buildings,499437130), label='西北食堂', relation='西侧', precision='reference_only')
    for name in ('乡村基','塔斯汀','鹏记重庆鸡公煲','夜罐罐米线'):
        ident = 'reported-' + hashlib.sha256(name.encode()).hexdigest()[:16]
        patch = dict(address='西北食堂西侧餐厅组', map_reference=ref)
        if name in ('鹏记重庆鸡公煲','夜罐罐米线'): patch['floor']='2'
        poi(ident, patch, '用户定位在西北食堂西侧；照片可见店招，鸡公煲、夜罐罐米线指示请上二楼；具体建筑ID与入口待补。')
    if COTTI in index: raise ValueError('Cotti ID exists; reconcile before insertion')
    put('pois', COTTI, dict(id=COTTI, name='库迪咖啡（西北食堂西侧）', source='user_photo_20261002',
        category='coffee', status='unverified', zone='campus', address='西北食堂西侧餐厅组',
        floor='1', location=None, building_id=None, opening_hours=None, map_reference=ref,
        spatial_sequence=dict(group='northwest-west',label='西北食堂西侧餐厅组',order=None,direction='unknown')),
        '用户照片可见Cotti Coffee库迪咖啡底层入口；店内完整使用范围、营业时间、在该组南北顺序与具体建筑待核。不是邮电大学校外店。')
    put('shops','shop-'+COTTI,dict(id='shop-'+COTTI,poi_id=COTTI,name='库迪咖啡（西北食堂西侧）',
        source='user_photo_20261002',floor='1',status='unverified',menu_status='missing'), '用户照片可见独立库迪店招；不虚构菜单或价格。')
    state['version'] += 1
    state['audit'].append(dict(action='spatial_correction',batch=BATCH,actor='g',at=at,ids=changed,
                              source_photo_sha256=photo_sha,geometry_changed=False))
    overlay(catalog,state)
    return state, changed


def prepare():
    original=read(ROOT/'data/life/contributions/state.json')
    catalog=CatalogAdapter(ROOT/'data/life',ROOT/'data/campus_info.sqlite3').snapshot()
    with (DIRECTORY/'hours.tsv').open(encoding='utf-8',newline='') as f: hours=list(csv.DictReader(f,delimiter='\t'))
    raw=PHOTO.read_bytes(); sha=hashlib.sha256(raw).hexdigest(); at=now()
    result,ids=corrected_state(original,catalog,read(ROOT/'assets/campus_assets_white_v6.json')['buildings'],hours,at,sha)
    stage=DIRECTORY/(BATCH+'-'+at.replace(':','-'))
    report=dict(batch=BATCH,stage=str(stage),original_digest=digest(original),result_digest=digest(result),
                approved=[],conflicts=[],drafts=[],hours=[],menu_counts={'imported':0},corrected_ids=ids,
                photo_sha256=sha,geometry_changed=False)
    write(stage/'result-state.json',result);write(stage/'report.json',report)
    write(stage/'before-pois.json',[p for p in catalog['pois'] if p['id'] in ids])
    (stage/'source.jpg').write_bytes(raw)
    print(__import__('json').dumps(dict(stage=str(stage),corrected_count=len(ids)),ensure_ascii=False))

if __name__=='__main__':prepare()
