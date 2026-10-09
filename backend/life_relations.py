"""Versioned, read-only campus relations. Source IDs and storage stay untouched."""
import base64
import copy
import hashlib
import json
import math
import re
import threading
from collections import Counter, OrderedDict

from .storage import ROOT, read
from .adapters import CatalogAdapter
from .agent.presentation import public_address, public_source, category_info
from .map_display import display_fields
from .menu_relations import build_menu_relations, record_data_mode
from .campus_content import enrich_buildings, area_descriptions
from .catalog_identity import normalize_identity, roster_review
from .confirmed_relations import apply_confirmed_relations, public_confirmations
from .poi_network import build_poi_network

CONTRACT_VERSION = 'life-map.v2'
PROJECTION_VERSION = '1.20.0-data.3'
INACTIVE = {'historical', 'archived', 'closed'}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def ref(kind, ident):
    return {'kind': kind, 'id': str(ident)}


def key(value):
    return value['kind'] + ':' + value['id']


def location_of(p):
    point = p.get('map_point') or p.get('location')
    if not isinstance(point, dict):
        return None
    crs = point.get('crs', p.get('location_crs'))
    if crs != 'local EPSG:32650':
        return None
    if any(isinstance(point.get(k), bool) or not isinstance(point.get(k), (int, float))
           or not math.isfinite(point[k]) for k in ('x', 'y')):
        return None
    return {'x': point['x'], 'y': point['y'], 'crs': crs}


def map_target(p, building_ids):
    """Never turn a relative reference or illustrative anchor into a shop entrance."""
    bid = str(p.get('building_id')) if p.get('building_id') is not None else None
    display = display_fields(p)
    point = location_of(p)
    if bid in building_ids:
        return dict(kind='building_anchor', poi_id=p['id'], building_id=bid,
                    precision='building', can_measure_to_entrance=False,
                    label='所在楼栋；店门位置未核实')
    if point:
        return dict(kind='recorded_point', poi_id=p['id'], location=point,
                    precision='recorded_unverified', can_measure_to_entrance=False,
                    label='已有记录位置；入口未复测')
    if display.get('map_reference'):
        return dict(kind='reference_area', poi_id=p['id'],
                    reference=display['map_reference'], precision='relative',
                    can_measure_to_entrance=False, label='参照区域；所在建筑待确认')
    sequence = display.get('spatial_sequence')
    return dict(kind='area_list' if sequence else 'unknown', poi_id=p['id'],
                area_id=sequence.get('group') if sequence else None,
                precision='area' if sequence else 'unknown', can_measure_to_entrance=False,
                label='区域名录；位置待补' if sequence else '具体位置待补')


def safe_price(item):
    value = item.get('price')
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None


def source_mode(*records):
    return record_data_mode(*records)


def active_sources(*records):
    return all(r.get('status') not in INACTIVE for r in records)


def build_relation_snapshot(catalog, buildings, areas=None):
    """Pure projection. Private paths/evidence never appear in returned entities."""
    c = apply_confirmed_relations(normalize_identity(catalog))
    entities, relations, issues = {}, [], []
    ids = {}
    for table in ('pois', 'shops', 'items'):
        ids[table] = {row['id'] for row in c[table]}
        if len(ids[table]) != len(c[table]):
            raise ValueError('Duplicate source ID: ' + table)
    for s in c['shops']:
        if s.get('poi_id') not in ids['pois']:
            raise ValueError('Orphan Shop')
    for item in c['items']:
        if item.get('shop_id') not in ids['shops']:
            raise ValueError('Orphan Item')

    def add(kind, ident, name, **values):
        r = ref(kind, ident)
        if key(r) in entities:
            raise ValueError('Duplicate projected entity')
        row = dict(ref=r, name=name, aliases=[], is_simulated=False,
                   operational_status='unknown', data_mode='real', source_active=True)
        row.update(values)
        entities[key(r)] = row
        return row

    def edge(kind, child, parent, basis='existing_record', **values):
        relations.append(dict(type=kind, subject=child, object=parent, basis=basis, **values))

    b_ids = {str(b.get('id', b.get('osm_id'))) for b in buildings}
    for b in buildings:
        ident = str(b.get('id', b.get('osm_id')))
        row = add('building', ident, b.get('name') or '未命名建筑',
                  description=b.get('description', ''),
                  description_status=b.get('description_status', '资料待补'),
                  content_origin=b.get('content_origin', 'unknown'),
                  review_state=b.get('review_state', 'unknown'),
                  function_tags=copy.deepcopy(b.get('function_tags', [])),
                  content_scope=b.get('content_scope'),
                  content_limitations=copy.deepcopy(b.get('content_limitations', [])),
                  source_links=copy.deepcopy(b.get('source_links', [])))
        row['map_target'] = dict(kind='building_anchor', building_id=ident, precision='building',
                                 can_measure_to_entrance=False)
    for a in areas or []:
        ident = str(a['id'])
        add('area', ident, a['name'], description=a.get('description', ''),
            content_origin=a.get('content_origin', 'unknown'),
            description_status=a.get('description_status', 'unknown'),
            review_state=a.get('review_state', 'unknown'),
            area_type=a.get('area_type', 'narrative_area'), geometry=None,
            content_scope=a.get('content_scope'),
            content_limitations=copy.deepcopy(a.get('content_limitations', [])),
            source_links=copy.deepcopy(a.get('source_links', [])))

    def ensure_area(ident, name):
        r = ref('area', ident)
        if key(r) not in entities:
            add('area', ident, name, area_type='catalogue_group', geometry=None,
                content_scope='名录逻辑分组，不代表测绘边界。')
        return r

    poi_index = {p['id']: p for p in c['pois']}
    shop_index = {s['id']: s for s in c['shops']}
    aliases = {'canteen-1': ['新一', '新乐群一层'], 'canteen-2': ['新二', '新乐群二层', '智慧食堂'],
               'canteen-3': ['新三', '学三', '新乐群三层'], 'canteen-4': ['新四', '学四', '新乐群四层'],
               'canteen-5': ['学五', '学五食堂']}
    for p in c['pois']:
        category = category_info(p)
        row = add('poi', p['id'], p['name'], category=category['display_category'],
                  address=public_address(p.get('address')), floor=p.get('floor') or None,
                  source=public_source(p.get('source')), status=p.get('status', 'unknown'),
                  hours=p.get('opening_hours_text') or '；'.join('–'.join(v) for v in p.get('opening_hours') or []) or '尚未录入',
                  opening_hours=copy.deepcopy(p.get('opening_hours')),
                  map_target=map_target(p, b_ids), **display_fields(p))
        row.update(public_confirmations(p))
        source_aliases = p.get('aliases') if isinstance(p.get('aliases'), list) else []
        row['aliases'] = list(dict.fromkeys([a for a in source_aliases if isinstance(a, str)] + aliases.get(p['id'], [])))
        row['data_mode'] = source_mode(p)
        row['is_simulated'] = row['data_mode'] == 'simulated'
        row['source_active'] = active_sources(p)
        row['operational_status'] = p.get('status', 'unknown')
        bid = str(p.get('building_id')) if p.get('building_id') is not None else None
        if bid and bid not in b_ids:
            issues.append(dict(code='MISSING_BUILDING', entity=row['ref'], severity='high'))
        if bid in b_ids:
            floor = str(p.get('floor') or '').strip()
            parent = ref('building', bid)
            if re.fullmatch(r'-?\d+', floor):
                fid = bid + ':floor:' + floor
                if key(ref('floor', fid)) not in entities:
                    f = add('floor', fid, floor + '层', floor=floor, building_id=bid)
                    edge('contained_in', f['ref'], parent)
                parent = ref('floor', fid)
            edge('contained_in', row['ref'], parent)
        seq = p.get('spatial_sequence') or {}
        if seq.get('group'):
            area = ensure_area(seq['group'], seq.get('label') or seq['group'])
            edge('member_of', row['ref'], area)
            if isinstance(seq.get('order'), (int, float)):
                edge('ordered_along', row['ref'], area, order=seq['order'], direction=seq.get('direction', 'unknown'))
        if p.get('zone'):
            area = ensure_area('zone:' + p['zone'], {'campus': '主校区', 'nearby': '周边片区'}.get(p['zone'], '范围待核'))
            edge('member_of', row['ref'], area)
        reference = row.get('map_reference') or {}
        reference_bid = str(reference.get('building_id'))
        if reference_bid in b_ids:
            edge('relative_to', row['ref'], ref('building', reference_bid),
                 relation=reference.get('relation', 'near'), precision='relative')
        if row['map_target']['kind'] in ('unknown', 'area_list', 'reference_area'):
            issues.append(dict(code='LOCATION_NOT_PRECISE', entity=row['ref'], severity='medium',
                               detail=row['map_target']['label']))

    for p in c['pois']:
        for r in public_confirmations(p).get('confirmed_relations', []):
            target = ref(r['target_kind'], r['target_id'])
            if key(target) in entities:
                edge(r['relation'], ref('poi', p['id']), target, basis='user_confirmation',
                     precision=r['precision'], evidence=r['evidence'],
                     **({'building_part': p['building_part']} if r['relation'] == 'located_in_part' else {}))

    for s in c['shops']:
        collection = (s.get('entity_type') == 'floor_menu_collection' or s.get('independent_merchant') is False
                      or s['id'] in {'menu-collection-xinlequn-3', 'menu-collection-xinlequn-4'})
        kind = 'collection' if collection else 'outlet'
        row = add(kind, s['id'], s['name'], poi_id=s['poi_id'], floor=s.get('floor') or None,
                  identity_status='source_only' if collection else 'existing_shop',
                  source=public_source(s.get('source')),
                  map_target=copy.deepcopy(entities[key(ref('poi', s['poi_id']))]['map_target']))
        row['data_mode'] = source_mode(s, poi_index[s['poi_id']])
        row['is_simulated'] = row['data_mode'] == 'simulated'
        row['source_active'] = active_sources(s, poi_index[s['poi_id']])
        row['operational_status'] = s.get('status', 'unknown')
        if s.get('canonical_shop_id'):
            row['canonical_outlet_id'] = s['canonical_shop_id']
        if s.get('source_poi_id'):
            row['source_poi_id'] = s['source_poi_id']
        edge('contained_in', row['ref'], ref('poi', s['poi_id']))

    for s in c['shops']:
        if s.get('canonical_shop_id') and key(ref('outlet', s['canonical_shop_id'])) in entities:
            edge('same_as', ref('outlet', s['id']), ref('outlet', s['canonical_shop_id']), basis='user_confirmation')

    menus = build_menu_relations(c)
    for outlet in menus.get('outlets', []):
        values = {k: copy.deepcopy(v) for k, v in outlet.items() if k not in ('id', 'name')}
        row = add('outlet', outlet['id'], outlet['name'], **values)
        parent_poi = poi_index[outlet['poi_id']]
        source_shop = shop_index[outlet['source_collection_id']]
        row.update(source_active=active_sources(source_shop, parent_poi),
                   operational_status=source_shop.get('status', 'unknown'),
                   map_target=copy.deepcopy(entities[key(ref('poi', outlet['poi_id']))]['map_target']))
        edge('contained_in', row['ref'], ref('poi', outlet['poi_id']), basis='user_confirmation')
        edge('derived_from', row['ref'], ref('collection', outlet['source_collection_id']), basis='menu_evidence')
    issues.extend(menus.get('issues', []))
    membership = menus['item_membership']
    if set(membership) != ids['items']:
        raise ValueError('Menu membership does not preserve all Item IDs')
    for g in menus['menu_groups']:
        values = {k: copy.deepcopy(g[k]) for k in ('poi_id', 'floor', 'outlet_id', 'identity_status',
                  'category', 'meal_role', 'evidence_summary', 'data_mode', 'source') if k in g}
        row = add('menu_group', g['id'], g['name'], **values)
        row['is_simulated'] = row['data_mode'] == 'simulated'
        group_items = [i for i in c['items'] if i['id'] in g['item_ids']]
        row['source_active'] = any(active_sources(i, shop_index[i['shop_id']], poi_index[g['poi_id']]) for i in group_items)
        row['item_count'] = len(g['item_ids'])
        row['map_target'] = copy.deepcopy(entities[key(ref('poi', g['poi_id']))]['map_target'])
        parent = ref('outlet', g['outlet_id']) if g.get('outlet_id') else ref('poi', g['poi_id'])
        edge('contained_in', row['ref'], parent, basis='menu_evidence')
        if not g.get('outlet_id') and not row['is_simulated']:
            issues.append(dict(code='OUTLET_IDENTITY_PENDING', entity=row['ref'], severity='high',
                               item_count=row['item_count']))
    for item in c['items']:
        m = membership[item['id']]
        s = shop_index[item['shop_id']]
        p = poi_index[s['poi_id']]
        row = add('item', item['id'], item['name'], group_id=m['group_id'],
                  outlet_id=m.get('outlet_id'), poi_id=p['id'],
                  specification=item.get('specification') or None, price=safe_price(item),
                  price_unit=item.get('price_unit') or item.get('unit') or None,
                  source=public_source(item.get('source')), availability=item.get('available'),
                  identity_status=m.get('identity_status'), meal_role=m.get('meal_role', 'unknown'),
                  observed_at=item.get('observation_date') or item.get('observed_at'),
                  status=item.get('status', 'unknown'))
        row['data_mode'] = source_mode(item, s, p)
        row['is_simulated'] = row['data_mode'] == 'simulated'
        row['source_active'] = active_sources(item, s, p)
        row['price_is_verified'] = row['price'] is not None and row['data_mode'] == 'real' and item.get('source') in ('menu_photo', 'field_observation', 'official_menu')
        row['operational_status'] = item.get('status', 'unknown')
        row['current_sale_verified'] = False  # A transcribed price is not live stock evidence.
        edge('listed_in', row['ref'], ref('menu_group', m['group_id']))
        if m.get('outlet_id'):
            edge('offered_by', row['ref'], ref('outlet', m['outlet_id']),
                 basis='user_confirmation' if m.get('identity_status') == 'confirmed' else 'existing_shop_identity')

    roster = roster_review(c)
    issues.extend(roster['issues'])
    for group in roster.get('same_building_groups', []):
        ident = group.get('id', 'northwest-west-unmatched-building')
        row = add('building_group', ident, group.get('name', '西侧商户同楼组'),
                  geometry_binding=group.get('model_building_id'), model_building_id=group.get('model_building_id'),
                  identity_status='user_confirmed' if group.get('model_building_id') else 'building_unmatched')
        if str(group.get('model_building_id')) in b_ids:
            edge('contained_in', row['ref'], ref('building', group['model_building_id']), basis='user_confirmation')
        for pid in group.get('poi_ids', group.get('member_ids', [])):
            if pid in poi_index:
                edge('same_building_member', ref('poi', pid), row['ref'], basis='user_confirmation')

    for r in relations:
        if key(r['subject']) not in entities or key(r['object']) not in entities:
            raise ValueError('Dangling projected relation')
    parents = {}
    for r in relations:
        if r['type'] in ('contained_in', 'listed_in'):
            child, parent = key(r['subject']), key(r['object'])
            if child in parents and parents[child] != parent:
                raise ValueError('Multiple containment parents')
            parents[child] = parent
    for child in parents:
        seen, current = set(), child
        while current in parents:
            if current in seen:
                raise ValueError('Containment cycle')
            seen.add(current)
            current = parents[current]
    for row in entities.values():
        path, current = [], key(row['ref'])
        browseable = row['operational_status'] not in INACTIVE and row['source_active'] and not row.get('canonical_outlet_id')
        while current in parents:
            current = parents[current]
            parent = entities[current]
            browseable = browseable and parent['operational_status'] not in INACTIVE and parent['source_active']
            path.append(dict(ref=parent['ref'], name=parent['name']))
        row['breadcrumbs'] = list(reversed(path))
        row['browseable'] = browseable
    body = dict(contract_version=CONTRACT_VERSION, projection_version=PROJECTION_VERSION,
                entities=list(entities.values()), relations=relations, issues=issues,
                menu_groups=menus['menu_groups'], item_membership=membership, roster=roster,
                summary=dict(source_counts={k: len(c[k]) for k in ('pois', 'shops', 'items')},
                             entity_counts=dict(Counter(r['ref']['kind'] for r in entities.values())),
                             item_sources=dict(Counter(i.get('source', 'unknown') for i in c['items'])),
                             pending_location_count=sum(i.get('code') == 'LOCATION_NOT_PRECISE' for i in issues)))
    body['network'] = build_poi_network(body, c)
    body['snapshot_id'] = 'sha256:' + fingerprint({'catalog': c, 'projection': body})
    return body


class SnapshotExpired(ValueError):
    pass


class RelationRepository:
    """Small immutable snapshot history; API callers receive copies, not shared objects."""
    def __init__(self, loader=None, retain=3):
        self.loader = loader or self.load
        self.retain = max(2, retain)
        self._snapshots = OrderedDict()
        self._lock = threading.RLock()

    @staticmethod
    def load():
        # Two stable logical reads detect concurrent source publication. No private account tree.
        def inputs():
            c = CatalogAdapter(ROOT / 'data/life', ROOT / 'data/campus_info.sqlite3').snapshot()
            b = enrich_buildings(read(ROOT / 'assets/campus_assets_white_v6.json')['buildings'])
            return c, b, area_descriptions()
        for _ in range(3):
            first, second = inputs(), inputs()
            if fingerprint(first) == fingerprint(second):
                return build_relation_snapshot(*second)
        raise ValueError('目录正更新，请稍后重试')

    def snapshot(self, snapshot_id=None):
        with self._lock:
            if snapshot_id:
                if snapshot_id not in self._snapshots:
                    raise SnapshotExpired('资料版本已过期，请重新加载')
                return copy.deepcopy(self._snapshots[snapshot_id])
            current = self.loader()
            sid = current['snapshot_id']
            self._snapshots[sid] = copy.deepcopy(current)
            self._snapshots.move_to_end(sid)
            while len(self._snapshots) > self.retain:
                self._snapshots.popitem(last=False)
            return copy.deepcopy(current)

    def query(self, operation, *, kind=None, ident=None, query='', cursor=None,
              snapshot_id=None, limit=24, include_simulated=False):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 60:
            raise ValueError('分页大小须为1至60')
        if not isinstance(query, str) or len(query) > 200:
            raise ValueError('查询词过长')
        index = 0
        scope = fingerprint([operation, kind, ident, query, include_simulated])
        if cursor:
            try:
                if not isinstance(cursor, str) or len(cursor) > 2048:
                    raise ValueError()
                token = json.loads(base64.urlsafe_b64decode(cursor + '=' * (-len(cursor) % 4)))
                if token['scope'] != scope or (snapshot_id and token['snapshot_id'] != snapshot_id):
                    raise ValueError()
                snapshot_id, index = token['snapshot_id'], token['index']
                if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                    raise ValueError()
            except (ValueError, TypeError, KeyError, UnicodeError):
                raise ValueError('分页游标无效') from None
        snapshot = self.snapshot(snapshot_id)
        base = {k: snapshot[k] for k in ('contract_version', 'projection_version', 'snapshot_id')}
        if operation == 'summary':
            return dict(base, summary=snapshot['summary'], issues=snapshot['issues'])
        entities = snapshot['entities']
        entity_map = {key(e['ref']): e for e in entities}
        def visible(e):
            return (include_simulated or e.get('data_mode', 'real') == 'real') and e['browseable']
        if operation == 'entity':
            row = entity_map.get(key(ref(kind, ident)))
            redirected_from = None
            canonical_field = {'poi': 'canonical_poi_id', 'outlet': 'canonical_outlet_id'}.get(kind)
            seen = set()
            while row and canonical_field and row.get(canonical_field):
                token = key(row['ref'])
                if token in seen:
                    raise KeyError('实体别名关系待核')
                seen.add(token)
                redirected_from = redirected_from or row['ref']
                row = entity_map.get(key(ref(kind, row[canonical_field])))
            if row is None or not visible(row):
                raise KeyError('实体不存在')
            return dict(base, entity=row, **({'redirected_from': redirected_from} if redirected_from else {}))
        if operation == 'search':
            q = query.strip().casefold()
            rows = [r for r in entities if visible(r) and (not kind or r['ref']['kind'] == kind)
                    and (not q or q in ' '.join([r['name']] + r.get('aliases', [])).casefold())]
        elif operation in ('children', 'items'):
            parent = ref('menu_group' if operation == 'items' else kind, ident)
            if key(parent) not in entity_map or not visible(entity_map[key(parent)]):
                raise KeyError('父实体不存在')
            allowed = {'listed_in'} if operation == 'items' else {'contained_in', 'member_of', 'same_building_member'}
            children = {key(r['subject']) for r in snapshot['relations'] if r['type'] in allowed and r['object'] == parent}
            rows = [r for r in entities if key(r['ref']) in children and visible(r)]
        else:
            raise ValueError('未知查询')
        rows.sort(key=lambda r: ((r.get('spatial_sequence') or {}).get('order') or 999, r['ref']['kind'], r['ref']['id']))
        page = rows[index:index + limit]
        next_cursor = None
        if index + limit < len(rows):
            token = dict(snapshot_id=snapshot['snapshot_id'], scope=scope, index=index + limit)
            next_cursor = base64.urlsafe_b64encode(json.dumps(token).encode()).decode().rstrip('=')
        return dict(base, items=page, total=len(rows), loaded_count=len(page), next_cursor=next_cursor)
