"""Guarded read-time application of the user's 2026-10-08 confirmations.

No source writes, approximate entrance coordinates, or physical record merges.
Containment, qualitative direction and identity are independent assertions.
"""
from copy import deepcopy
import re
from .catalog_identity import (WEST_BUILDING_IDS, NORTHWEST_REFERENCE,
    LAIXIFU_CANDIDATE, YOUGUOHUI, TMALL, MIXUE, KFC, IDENTITY_RULES)

BATCH = 'user-relations-20261008'
NORTHWEST_BUILDING = 499437130
XUEWU_BUILDING = 499437078
_NAMES = {
    WEST_BUILDING_IDS[0]: ('乡村基',), WEST_BUILDING_IDS[1]: ('塔斯汀',),
    WEST_BUILDING_IDS[2]: ('鹏记重庆鸡公煲',), WEST_BUILDING_IDS[3]: ('夜罐罐米线',),
    WEST_BUILDING_IDS[4]: ('库迪咖啡（西北食堂西侧）',),
    NORTHWEST_REFERENCE: ('西北风味餐厅(北师大店)', '西北风味餐厅（北师大店）'),
    'laixifu': ('来喜福', '来喜福炒酸奶鸡蛋仔'),
    LAIXIFU_CANDIDATE: ('来喜福炒酸奶鸡蛋仔',),
    KFC: ('肯德基(北京师范大学店)', '肯德基（北京师范大学店）'),
    **{ident: IDENTITY_RULES[ident]['names'] for ident in (YOUGUOHUI, TMALL, MIXUE)},
}
_SPATIAL_FIELDS = ('building_id', 'location', 'map_point', 'display_anchor',
                   'map_reference', 'address', 'spatial_sequence', 'building_part',
                   'location_description', 'location_review_status', 'location_source')


def _matches(row):
    return bool(row and row.get('name') in _NAMES.get(row.get('id'), ()))


def _newer_manual(row, fields):
    # The source snapshot used by this confirmation contains spatial edits up to
    # Oct 2. Any later reviewed edit must win, even on the confirmation's date.
    evidence = row.get('field_evidence') or {}
    for field in fields:
        entry = evidence.get(field) or {}
        if str(entry.get('reviewed_at') or entry.get('reported_at') or '')[:10] > '2026-10-02':
            return True
    return False


def _evidence(note):
    return dict(source='user_confirmation', reported_at='2026-10-08',
                observed_at=None, batch=BATCH, note=note)


def _relation(row, relation, kind, ident, note):
    value = dict(relation=relation, target_kind=kind, target_id=str(ident),
                 precision='qualitative', evidence=_evidence(note))
    rows = row.setdefault('confirmed_relations', [])
    if value not in rows:
        rows.append(value)


def _building(row, bid, part, label):
    row.update(building_id=bid, building_part=part, address=label,
               location_description=label, location_review_status='building_confirmed_entrance_unknown')
    _relation(row, 'located_in_part', 'building', bid, label)
    # Promote only an existing matching building reference to a representative
    # building anchor. The point remains display-only, never a routing position.
    old = next((p for p in (row.get('display_anchor'), row.get('map_reference'))
                if isinstance(p, dict) and str(p.get('building_id')) == str(bid)
                and p.get('crs') == 'local EPSG:32650'), None)
    if old:
        row['display_anchor'] = dict(old, precision='building', label=label+'；楼栋代表点，非店门')
    else:
        row['display_anchor'] = None
    row['map_reference'] = None
    row['location_confirmation'] = _evidence(label+'；未提供店门坐标。')


def apply_confirmed_relations(catalog):
    """Deep-copy projection, idempotent and exact-ID/name guarded."""
    result = deepcopy(catalog)
    index = {p['id']: p for p in result.get('pois', [])}
    northwest = index.get(NORTHWEST_REFERENCE)
    if _matches(northwest) and str(northwest.get('building_id')) == str(NORTHWEST_BUILDING):
        for ident in WEST_BUILDING_IDS:
            row = index.get(ident)
            if (_matches(row) and not _newer_manual(row, _SPATIAL_FIELDS)
                    and row.get('building_id') in (None, NORTHWEST_BUILDING, str(NORTHWEST_BUILDING))):
                _building(row, NORTHWEST_BUILDING, 'southwest', '西北食堂同建筑南面西侧')

    canonical, duplicate = index.get('laixifu'), index.get(LAIXIFU_CANDIDATE)
    if _matches(canonical) and not _newer_manual(canonical, _SPATIAL_FIELDS):
        if canonical.get('building_id') in (None, XUEWU_BUILDING, str(XUEWU_BUILDING)):
            _building(canonical, XUEWU_BUILDING, 'north', '学五食堂同建筑北面')
    if (_matches(canonical) and _matches(duplicate)
            and not canonical.get('canonical_poi_id')
            and duplicate.get('canonical_poi_id') in (None, '', 'laixifu')
            and not _newer_manual(canonical, ('name', 'aliases', 'canonical_poi_id'))
            and not _newer_manual(duplicate, ('name', 'status', 'canonical_poi_id'))):
        duplicate.update(canonical_poi_id='laixifu', status='archived', identity_status='confirmed_alias',
                         identity_confirmation=_evidence('用户确认只有一家来喜福；旧ID留档并转向规范身份。'))
        _relation(duplicate, 'same_as', 'poi', 'laixifu', '同一家店，旧ID仅作历史别名。')
        aliases = canonical.get('aliases')
        if aliases is None or isinstance(aliases, list):
            canonical['aliases'] = list(dict.fromkeys([*(aliases or []), duplicate['name'], '来喜福炒酸奶鸡蛋仔']))
        # Child records remain visible through the canonical identity. Keep
        # original child IDs and Item.shop_id; save the previous POI reference.
        canonical_shop = next((s for s in result.get('shops', []) if s.get('id') == 'shop-laixifu'
                               and s.get('poi_id') == 'laixifu' and s.get('name') in _NAMES['laixifu']
                               and s.get('source') not in {'simulated', 'inferred', 'generated'}
                               and not s.get('canonical_shop_id')), None)
        for shop in result.get('shops', []):
            if shop.get('poi_id') != LAIXIFU_CANDIDATE:
                continue
            shop.setdefault('source_poi_id', LAIXIFU_CANDIDATE)
            shop['poi_id'] = 'laixifu'
            if canonical_shop and shop.get('source') not in {'simulated', 'inferred', 'generated'}:
                shop.update(canonical_shop_id=canonical_shop['id'], identity_status='confirmed_alias')

    fruit, tmall = index.get(YOUGUOHUI), index.get(TMALL)
    if _matches(fruit) and _matches(tmall):
        for row, other, direction in ((fruit, tmall, 'west_of'), (tmall, fruit, 'east_of')):
            if _newer_manual(row, _SPATIAL_FIELDS):
                continue
            _relation(row, 'adjacent_to', 'poi', other['id'], '用户确认两店相邻；间距未知。')
            _relation(row, direction, 'poi', other['id'], '优果荟在西，天猫校园超市在东。')
        # The user resolved the relationship, not which absolute source point
        # is right. Retire BOTH incompatible positions rather than arbitrarily
        # choosing a point and manufacturing a neighbour beside it.
        expected = {YOUGUOHUI: (-354.73, -326.87), TMALL: (359.73, -227.52)}
        for row in (fruit, tmall):
            point = row.get('location') or {}
            old = expected[row['id']]
            unchanged = (point.get('x'), point.get('y')) == old and row.get('map_point') is None
            already = row.get('location_confirmation', {}).get('batch') == BATCH
            if not _newer_manual(row, _SPATIAL_FIELDS) and (unchanged or already):
                row.update(location=None, map_point=None, display_anchor=None, map_reference=None,
                           building_id=None, location_source='conflict_pending',
                           location_review_status='conflicting_source_points',
                           location_description='优果荟在西、天猫校园超市在东，两店相邻；共同绝对位置尚未录入',
                           location_confirmation=_evidence('相邻与东西关系已确认；原坐标相距约721米，两店绝对点位待共同点选。'))
                # The former group-wide N-to-S order cannot coexist with this
                # specifically confirmed E-to-W pair as a surveyed ordering.
                seq = row.get('spatial_sequence')
                if isinstance(seq, dict):
                    row['spatial_sequence'] = dict(seq, order=None, direction='unknown')

    mixue, kfc = index.get(MIXUE), index.get(KFC)
    if _matches(mixue) and _matches(kfc):
        for row, other in ((mixue, kfc), (kfc, mixue)):
            if not _newer_manual(row, _SPATIAL_FIELDS):
                _relation(row, 'adjacent_to', 'poi', other['id'], '用户确认蜜雪与肯德基相邻；不从源坐标小差值交换点位。')
    return result


def public_confirmations(row):
    """Whitelist relation metadata; never expose raw field audits or paths."""
    out = {}
    ident = row.get('canonical_poi_id')
    if isinstance(ident, str) and re.fullmatch(r'[A-Za-z0-9._:-]{1,100}', ident):
        out['canonical_poi_id'] = ident
    if row.get('building_part') in {'north', 'southwest'}:
        out['building_part'] = row['building_part']
    if row.get('location_review_status') in {'building_confirmed_entrance_unknown', 'conflicting_source_points'}:
        out['location_review_status'] = row['location_review_status']
    description = row.get('location_description')
    if isinstance(description, str):
        from .agent.presentation import public_address
        clauses = re.split(r'[；;\n。]', description)
        safe = '；'.join(c for c in clauses if not re.search(
            r'管理员|[/\\](?:Users|home|private|tmp|data)[/\\]|(?:token|api.?key|secret|password)\s*[:=]', c, re.I))
        if public_address(safe):
            out['location_description'] = public_address(safe)
    relations = []
    for r in row.get('confirmed_relations') or []:
        if r.get('relation') not in {'same_as', 'adjacent_to', 'west_of', 'east_of', 'located_in_part'}:
            continue
        if (r.get('evidence') or {}).get('batch') != BATCH or r.get('target_kind') not in {'poi', 'building'}:
            continue
        if not isinstance(r.get('target_id'), str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,100}', r['target_id']):
            continue
        value = {k: deepcopy(r[k]) for k in ('relation', 'target_kind', 'target_id', 'precision') if k in r}
        # Public provenance is a registry label, never a pass-through raw audit.
        value['evidence'] = _evidence('用户确认的身份或定性空间关系；不表示精确店门、实时营业或新测绘。')
        relations.append(value)
    if relations:
        out['confirmed_relations'] = relations
    return out
