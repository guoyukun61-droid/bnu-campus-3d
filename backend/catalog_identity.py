"""Pure, conservative identity projection and a fixed user-supplied roster.

No filesystem access, ID merges, source mutations, or invented coordinates.
Roster order is a user's description, not a measured topology or a footprint.
"""
from collections import Counter
from copy import deepcopy
import math


MIXUE = 'baidu-9d9d7030bb7bcc77e0110373'
KFC = 'baidu-be3e817cbfd2ba2c2b3a9fd9'
ZENGSANXIAN = 'baidu-be4b47af81efd4befb2d6156'
TMALL = 'baidu-5dbb42fb4c2f8060a21de9cf'
YOUGUOHUI = 'baidu-4fa1ea3de624c94dc7effb11'
COTTI = 'reported-cotti-northwest-campus'
LAIXIFU_CANDIDATE = 'baidu-e01d5828d274ead49fec2b78'
NORTHWEST_REFERENCE = 'baidu-7388dffd488f73f2d3ff2365'

# Exact-ID AND exact-name checks prevent stale mappings from relabelling a new
# tenant, a different branch, or a manually corrected identity at the same ID.
IDENTITY_RULES = {
    ZENGSANXIAN: {
        'names': ('曾三仙米线(北师大店)', '曾三仙米线（北师大店）', '曾三线米线'),
        'aliases': ('曾三线米线',),
    },
    TMALL: {
        'names': ('天猫校园超市(北师大店)', '天猫校园超市（北师大店）', '24h超市'),
        'aliases': ('24h超市', '24小时超市'),
    },
    YOUGUOHUI: {
        'names': ('优果荟', '优果荟水果超市'),
        'aliases': ('优果荟水果超市',),
    },
    MIXUE: {
        'names': ('蜜雪冰城(北师大店)', '蜜雪冰城（北师大店）'),
        'aliases': (), 'category': 'drink',
    },
}

# Stable IDs, not hashes of subsequently edited names or array positions.
ROSTER_GROUPS = (
    ('north-services', '北段生活服务', (
        ('reported-7e96929e4f66795d', '平凡眼镜'),
        ('reported-e709ed621b8046eb', '复印社'),
    )),
    ('snack-main', '小吃街主排', (
        ('reported-6c4c9ce1d5f774c8', '小果匠水果捞'),
        (MIXUE, '蜜雪冰城'), (KFC, '肯德基'),
        ('reported-7674d316d650d22f', '无名缘粉面'),
        ('reported-7dfa26ae639eee47', '卤肉饭'),
        ('reported-690dccdc02ee7c48', '苗香掉渣饼'),
        ('reported-de6fc12ba54190e3', '沪上阿姨'),
        ('reported-42eb7b8a1e387d7a', '渝见你酸辣粉'),
        ('reported-9990383df790ac4e', '彩棠里（隆江猪脚饭贵阳糯米饭）'),
        ('reported-deb9ca8020a1dc88', '好这口重庆小面'),
        (ZENGSANXIAN, '曾三线米线'),
        ('reported-ed888bace4062779', '学之缘饼屋'),
        ('reported-68c2f5e857eedd11', '快客100'),
    )),
    ('south-second', '南侧二层', (
        ('starbucks', '星巴克'),
        ('reported-9708a3255421d5f7', '雲起时图文广告'),
        ('reported-863435c964639d80', '魔都剪艺'),
    )),
    ('xuewu-side', '学五周边一组', (
        ('reported-d93f576698f93216', '了辛·爆汁烤冷面'),
        ('laixifu', '来喜福炒酸奶鸡蛋仔'),
        ('reported-a491e0c373e82964', '广式肠粉'),
        ('xiaomi', '小米鸡排'), ('wugu', '五谷坊'),
        ('reported-ddd5ecac0cfad563', '陕西小吃'),
    )),
    ('northwest-west', '西北食堂西侧餐厅组', (
        ('reported-174e0a7adb61c3ad', '乡村基'),
        ('reported-f91106f326893dd0', '塔斯汀'),
        ('reported-af9de3e5b1e29fe6', '鹏记重庆鸡公煲'),
        ('reported-25db5caa2fbffbf4', '夜罐罐米线'),
        (NORTHWEST_REFERENCE, '西北风味餐厅'),
    )),
    ('tmall-services', '天猫校园服务组', (
        (YOUGUOHUI, '优果荟水果超市'), (TMALL, '24h超市'),
        ('reported-5e20dc62d00403c9', '鲜花绿植'),
        ('reported-8a79cc83d7f748ca', '电子维修'),
        ('reported-7dd59512dbdc9c14', '打印复印'),
        ('reported-95cc340c4d32732e', '干洗养护'),
        ('reported-460576edfad64173', '明亮眼镜'),
        ('reported-38d641383e632000', '薛记炒货'),
        ('reported-4488c5185a3a9e69', '美甲美发美睫'),
    )),
)
ROSTER_IDS = tuple(ident for _, _, rows in ROSTER_GROUPS for ident, _ in rows)
WEST_BUILDING_IDS = (
    'reported-174e0a7adb61c3ad', 'reported-f91106f326893dd0',
    'reported-af9de3e5b1e29fe6', 'reported-25db5caa2fbffbf4', COTTI,
)


def normalize_identity(catalog):
    """Return a full deep copy with only guarded aliases/category normalized."""
    result = deepcopy(catalog)
    for poi in result.get('pois', []):
        rule = IDENTITY_RULES.get(poi.get('id'))
        if not rule or poi.get('name') not in rule['names']:
            continue
        if rule['aliases']:
            existing = poi.get('aliases')
            # Malformed manual aliases are left intact, not silently discarded.
            if existing is None or isinstance(existing, list):
                aliases = list(existing or [])
                for alias in rule['aliases']:
                    if alias not in aliases:
                        aliases.append(alias)
                poi['aliases'] = aliases
        if 'category' in rule and poi.get('category') != rule['category']:
            poi.setdefault('original_category', poi.get('category'))
            poi['category'] = rule['category']
    return result


def _point(value, require_crs=False):
    if not isinstance(value, dict):
        return None
    if require_crs and value.get('crs') != 'local EPSG:32650':
        return None
    if value.get('crs') not in (None, 'local EPSG:32650'):
        return None
    if all(isinstance(value.get(k), (int, float))
           and not isinstance(value[k], bool) and math.isfinite(value[k])
           for k in ('x', 'y')):
        return value
    return None


def _location_summary(poi):
    anchor = _point(poi.get('display_anchor'), require_crs=True)
    point = anchor or _catalog_point(poi)
    if point:
        inside = abs(point['x']) <= 452 and abs(point['y']) <= 601
        return inside, ('building_anchor' if anchor else 'location') if inside else 'outside_model'
    if _point(poi.get('map_reference'), require_crs=True):
        return False, 'reference_only'
    return False, 'unlocated'


def _catalog_point(poi):
    point = poi.get('location')
    if not isinstance(point, dict):
        return None
    return _point(dict(point, crs=point.get('crs', poi.get('location_crs'))), require_crs=True)


def _row(ident, roster_name, group, label, order, index):
    poi = index.get(ident, {})
    has_point, mode = _location_summary(poi)
    return dict(id=ident, name=poi.get('name') or roster_name,
                roster_name=roster_name, present=bool(poi), group=group,
                group_label=label, order=order,
                direction='north_to_south' if order is not None else 'unknown',
                category=poi.get('category'),
                has_display_point=has_point, location_mode=mode,
                building_id=poi.get('building_id'), floor=poi.get('floor') or None,
                operational_status=poi.get('status'),
                can_measure_to_entrance=False)


def roster_review(catalog):
    """Safe, file-independent audit of the 38 rows, plus separate extra Cotti.

No point is moved. A sequence conflict reports input disagreement only; it does
not choose which source is accurate or infer a measurement precision.
"""
    projected = normalize_identity(catalog)
    index = {poi['id']: poi for poi in projected.get('pois', []) if 'id' in poi}
    rows = [_row(ident, name, group, label, order, index)
            for group, label, entries in ROSTER_GROUPS
            for order, (ident, name) in enumerate(entries, 1)]
    issues = []
    for row in rows:
        if not row['present']:
            issues.append(dict(code='missing_roster_entry', ids=[row['id']],
                               review_state='candidate', message='用户已知名录未在当前快照找到。'))
        elif not row['has_display_point']:
            issues.append(dict(code='roster_location_incomplete', ids=[row['id']],
                               review_state='unknown', message='保留名录；具体店铺点位尚不能在当前模型直接展示。'))
    for ident, rule in IDENTITY_RULES.items():
        if ident in index and index[ident].get('name') not in rule['names']:
            issues.append(dict(code='identity_mapping_name_changed', ids=[ident],
                               review_state='candidate', message='当前名称与已确认映射不同，未自动补别名或改分类。'))
    if ('laixifu' in index and LAIXIFU_CANDIDATE in index
            and index[LAIXIFU_CANDIDATE].get('canonical_poi_id') != 'laixifu'):
        issues.append(dict(code='possible_same_as', ids=['laixifu', LAIXIFU_CANDIDATE],
                           review_state='candidate', relation='possible_same_as',
                           message='来喜福两条记录可能同店；保留原ID，未自动合并。'))
    for north, south, label in ((YOUGUOHUI, TMALL, '天猫校园服务组'), (MIXUE, KFC, '小吃街主排')):
        confirmed_adjacent = any(r.get('relation') == 'adjacent_to' and r.get('target_id') == south
                                 for r in index.get(north, {}).get('confirmed_relations', []))
        if confirmed_adjacent:
            if north == YOUGUOHUI and any(index.get(i, {}).get('location_review_status') == 'conflicting_source_points' for i in (north, south)):
                issues.append(dict(code='adjacent_pair_absolute_position_pending', ids=[north, south],
                                   review_state='location_pending', relation='adjacent_to',
                                   message='两店相邻且果荟在西、天猫在东已确认；共同绝对点位尚未录入，已停用冲突源坐标参与估时。'))
            continue
        a = _catalog_point(index.get(north, {}))
        b = _catalog_point(index.get(south, {}))
        if a and b and a['y'] < b['y']:
            issues.append(dict(code='spatial_sequence_vs_location_conflict',
                               ids=[north, south], review_state='candidate',
                               group='tmall-services' if north == YOUGUOHUI else 'snack-main',
                               northing_difference_m=round(b['y'] - a['y'], 2),
                               source_point_separation_m=round(math.hypot(b['x'] - a['x'], b['y'] - a['y']), 2),
                               message=label+'的用户北南顺序与既有点位Y顺序不一致；数值仅为源坐标比较，不代表实测误差，不自动搬动坐标。'))
    counts = Counter(row['group'] for row in rows if row['present'])
    present = sum(row['present'] for row in rows)
    displayable = sum(row['has_display_point'] for row in rows)
    extra = [_row(COTTI, '库迪咖啡（西北食堂西侧）', 'northwest-west',
                  '西北食堂西侧餐厅组', None, index)]
    west_members = [dict(id=ident, present=ident in index) for ident in WEST_BUILDING_IDS]
    west_bound = all(str(index.get(ident, {}).get('building_id')) == '499437130'
                     and index.get(ident, {}).get('building_part') == 'southwest' for ident in WEST_BUILDING_IDS)
    return dict(
        rows=rows, extra_rows=extra,
        summary=dict(expected_roster_count=len(ROSTER_IDS), present_count=present,
                     missing_count=len(ROSTER_IDS) - present,
                     displayable_count=displayable,
                     without_display_point_count=present - displayable,
                     main_row_expected_count=13, main_row_present_count=counts['snack-main'],
                     extra_count=sum(row['present'] for row in extra),
                     real_world_completeness='unknown',
                     location_note='展示点包含楼栋代表点，不等于已核实店门。',
                     groups=[dict(id=group, expected_count=len(entries), present_count=counts[group])
                             for group, _, entries in ROSTER_GROUPS]),
        issues=issues,
        same_building_groups=[dict(
            id='northwest-west-same-building', name='西北食堂西侧五店同楼组',
            relation='same_building', origin='user_confirmation',
            members=west_members, member_ids=list(WEST_BUILDING_IDS),
            model_building_id=499437130 if west_bound else None,
            model_mapping_status='user_confirmed' if west_bound else 'unknown',
            reference_poi_id=NORTHWEST_REFERENCE,
            reference_relation='same_building_southwest' if west_bound else 'west_of',
            note='用户确认西北食堂同楼南面西侧；沿用该楼模型ID，非店门或轮廓重测。' if west_bound else '同楼事实与模型匹配分开；模型匹配仍待核。')])
