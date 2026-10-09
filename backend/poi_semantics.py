"""Pure, explainable semantic concepts for the POI network.

Concepts are shared nodes, not pairwise links asserting that branches are the
same shop. Recorded classification is not a guarantee of service availability;
guarded name rules are always marked inferred. Item traits require explicit
recorded tags and never propagate to a shop, building, or another menu item.
"""
import re

from .menu_relations import record_data_mode


RULE_VERSION = '1.20.0-data.3'

CATEGORY_NAMES = {
    'food': '餐饮', 'drinks': '咖啡饮品', 'retail': '便利购物',
    'services': '生活服务', 'sports': '体育运动', 'campus': '校园公共设施',
    'other': '其他地点',
}
SERVICE_NAMES = {
    'dining': '餐饮供餐', 'beverages': '咖啡与饮品', 'shopping': '零售购物',
    'life-services': '生活服务', 'printing': '打印复印', 'study': '学习与阅读',
    'sports': '体育活动', 'financial-services': '金融服务',
    'campus-access': '校园出入口', 'haircare': '美发与美容',
    'repair': '设备维修', 'laundry': '衣物清洗养护', 'floral': '鲜花绿植',
    'optical': '眼镜零售', 'parcel': '快递收寄',
}

_CATEGORY = {
    'restaurant': 'food', 'canteen': 'food', 'snack': 'food', 'food': 'food',
    'coffee': 'drinks', 'drink': 'drinks', 'drinks': 'drinks',
    'retail': 'retail', 'supermarket': 'retail',
    'service': 'services', 'services': 'services', 'finance': 'services',
    'sports': 'sports', 'building': 'campus', 'gate': 'campus',
    'library': 'campus', 'dormitory': 'campus', 'public': 'campus',
    'campus': 'campus', 'other': 'other',
}
_GENERAL_SERVICE = {
    'food': 'dining', 'drinks': 'beverages', 'retail': 'shopping',
    'services': 'life-services', 'sports': 'sports',
}

# Entire business names (optionally followed by one branch suffix), never a
# free substring match such as finding “打印” in “打印社旁咖啡店”.
_NAMED_SERVICES = (
    ('printing', 'services', frozenset(('复印社', '打印复印', '打印复印店',
        '雲起时图文广告', '云起时图文广告', '图文复印中心'))),
    ('haircare', 'services', frozenset(('魔都剪艺', '美甲美发美睫'))),
    ('repair', 'services', frozenset(('电子维修', '电子维修店'))),
    ('laundry', 'services', frozenset(('干洗养护', '洗衣店'))),
    ('floral', 'retail', frozenset(('鲜花绿植', '鲜花店'))),
    ('optical', 'retail', frozenset(('平凡眼镜', '明亮眼镜'))),
    ('parcel', 'services', frozenset(('快递服务中心', '快递中心', '校园快递中心',
        '北京师范大学快递服务中心', '北师大快递服务中心'))),
    ('shopping', 'retail', frozenset(('天猫校园超市', '24h超市', '24小时超市',
        '学子超市', '优果荟', '优果荟水果超市', '薛记炒货'))),
)
_STUDY_NAME = re.compile(
    r'^(?:(?:北京师范大学|北师大)?(?:图书馆|自习室|学习中心)'
    r'|教[一二三四五六七八九十0-9]+楼?'
    r'|第?[一二三四五六七八九十0-9]+教学楼)$')
_BRANCH_NAME = re.compile(r'^([^()]+?)(?:\([^()]{1,80}\))?$')

# Brand attribution is inferred from a guarded recorded name, not an ownership,
# franchise verification, shared menu, or same-place assertion.
_BRANDS = (
    ('luckin', '瑞幸咖啡', ('瑞幸咖啡', 'luckin coffee', 'luckin'), 'drinks'),
    ('mixue', '蜜雪冰城', ('蜜雪冰城', 'mixue'), 'drinks'),
    ('kfc', '肯德基', ('肯德基', 'kfc', 'kfc肯德基'), 'food'),
    ('starbucks', '星巴克', ('星巴克', 'starbucks'), 'drinks'),
    ('cotti', '库迪咖啡', ('库迪咖啡', 'cotti coffee', 'cotti'), 'drinks'),
    ('tastin', '塔斯汀', ('塔斯汀', '塔斯汀中国汉堡'), 'food'),
    ('xiangcunji', '乡村基', ('乡村基',), 'food'),
    ('hushangayi', '沪上阿姨', ('沪上阿姨', '沪上阿姨鲜果茶'), 'drinks'),
    ('tmall-campus', '天猫校园', ('天猫校园超市',), 'retail'),
)

_TRAITS = {
    'spicy': ('辣', ('辣', '香辣', 'spicy')),
    'mild-spicy': ('微辣', ('微辣', 'mild-spicy')),
    'medium-spicy': ('中辣', ('中辣', 'medium-spicy')),
    'hot-spicy': ('重辣', ('重辣', 'hot-spicy')),
    'not-spicy': ('不辣', ('不辣', 'non-spicy', 'not-spicy')),
    'rice': ('米饭类', ('米饭', '饭', 'rice')),
    'noodles': ('面食类', ('面', '面食', 'noodles')),
    'rice-noodles': ('米线米粉类', ('米线', '米粉', 'rice-noodles')),
    'sweet': ('甜味', ('甜', '甜味', 'sweet')),
    'sour': ('酸味', ('酸', '酸味', 'sour')),
    'light-flavour': ('清淡', ('清淡', 'light-flavour')),
    'beverage': ('饮品类', ('饮品', 'beverage')),
    'coffee': ('咖啡类', ('咖啡', 'coffee')),
    'dessert': ('甜品类', ('甜品', 'dessert')),
    'vegetarian': ('原记录素食标签', ('素', '素食', 'vegetarian')),
    'vegan': ('原记录纯素标签', ('纯素', 'vegan')),
    'halal': ('原记录清真标签', ('清真', 'halal')),
    'peanut-free': ('原记录无花生标签', ('无花生', '不含花生', 'peanut-free')),
    'gluten-free': ('原记录无麸质标签', ('无麸质', 'gluten-free')),
}
_TRAIT_LOOKUP = {tag.casefold(): ident for ident, (_, tags) in _TRAITS.items() for tag in tags}
_INACTIVE = frozenset(('historical', 'archived', 'closed'))
_BUILDING_SERVICES = {
    'library': 'study', 'study': 'study', 'teaching': 'study',
    'teaching_candidate': 'study', 'dining': 'dining',
    'retail': 'shopping', 'shopping': 'shopping', 'sports': 'sports',
    'parcel': 'parcel', 'parcel_services': 'parcel',
}
_SERVICE_LIMITS = ('类别或名称只表示服务线索，不保证当前营业、商品在售、预约可用或对外开放。',)
_TRAIT_LIMITS = ('仅保留该商品原记录标签；不代表过敏原、清真认证或严格饮食安全核验，需向窗口确认。',
                 '标签不继承到其他商品、窗口或所属建筑。')


def _ref(kind, ident):
    return dict(kind=kind, id=ident)


def _index(rows):
    return {r['id']: r for r in rows if isinstance(r, dict) and isinstance(r.get('id'), str)}


def _base_name(value):
    if not isinstance(value, str) or len(value) > 200:
        return ''
    text = ' '.join(value.strip().replace('（', '(').replace('）', ')').split())
    match = _BRANCH_NAME.fullmatch(text)
    return match[1].strip().casefold() if match else ''


def _context(entity, pois, shops, items):
    kind, ident = entity['ref']['kind'], entity['ref']['id']
    if kind == 'poi':
        primary = pois.get(ident, {})
        return primary, [primary]
    if kind == 'outlet':
        primary = shops.get(ident, {})
        source = shops.get(entity.get('source_collection_id'), {})
        parent = pois.get(primary.get('poi_id') or entity.get('poi_id'), {})
        return primary, [primary, source, parent]
    primary = items.get(ident, {})
    shop = shops.get(primary.get('shop_id'), {})
    parent = pois.get(shop.get('poi_id') or entity.get('poi_id'), {})
    return primary, [primary, shop, parent]


def build_semantics(entities, catalog):
    """Return new concept nodes, semantic edges and issues; inputs stay intact.

    Real, browseable POIs/outlets receive shared category/service/brand concepts.
    A real building's official or explicitly inferred function tags provide
    service hints with their own provenance, not a live availability guarantee.
    Real Items receive traits only from whitelisted, explicit source tags. Neither
    archived aliases, collections, simulated nor inferred source entities enter
    this real semantic graph. Inferred edges are only conservative name rules.
    """
    pois = _index(catalog.get('pois', []))
    shops = _index(catalog.get('shops', []))
    items = _index(catalog.get('items', []))
    nodes, edges, issues = {}, {}, []

    def add_edge(entity, edge_type, kind, ident, name, status, basis, limits=(), original_category=None, rule_origin=None):
        target = (kind, ident)
        if target not in nodes:
            nodes[target] = dict(ref=_ref(kind, ident), name=name, data_mode='real', browseable=True, concept=True)
        subject = _ref(entity['ref']['kind'], entity['ref']['id'])
        edge_key = (subject['kind'], subject['id'], edge_type, kind, ident)
        existing = edges.get(edge_key)
        # An explicit recorded category outranks a duplicate inferred name hint.
        if existing and (existing['status'] == 'recorded' or status == 'inferred'):
            return
        edges[edge_key] = dict(type=edge_type, subject=subject, object=_ref(kind, ident),
                              status=status, basis=basis, limitations=list(limits), rule_version=RULE_VERSION)
        if original_category in _CATEGORY:
            edges[edge_key]['original_category'] = original_category
        if rule_origin in {'recorded_category', 'safe_entity_category', 'parent_category',
                           'exact_name_rule', 'recorded_item_tags', 'official_function_tags',
                           'inferred_function_tags'}:
            edges[edge_key]['rule_origin'] = rule_origin

    def issue(code, entity, **fields):
        issues.append(dict(code=code, entity=_ref(entity['ref']['kind'], entity['ref']['id']), **fields))

    for entity in entities:
        reference = entity.get('ref') if isinstance(entity, dict) else None
        if not isinstance(reference, dict) or reference.get('kind') not in {'poi', 'outlet', 'item', 'building'}:
            continue
        if not isinstance(reference.get('id'), str) or not reference['id']:
            continue
        if entity.get('browseable') is not True or entity.get('data_mode', 'real') != 'real' or entity.get('is_simulated') is True:
            continue
        if reference['kind'] == 'building':
            origin = entity.get('content_origin')
            tags = entity.get('function_tags')
            if origin not in {'official_public_source', 'inferred'} or not isinstance(tags, list):
                continue
            if entity.get('operational_status') in _INACTIVE or entity.get('review_state') in {'identity_mismatch', 'source_pending'}:
                continue
            for tag in tags:
                if not isinstance(tag, str) or tag not in _BUILDING_SERVICES:
                    continue
                service = _BUILDING_SERVICES[tag]
                inferred = origin == 'inferred' or tag.endswith('_candidate')
                add_edge(entity, 'provides_service', 'service', service, SERVICE_NAMES[service],
                         'inferred' if inferred else 'recorded',
                         'building.function_tags:' + tag,
                         _SERVICE_LIMITS + ('楼宇用途不表示教室当前空闲、能自习或已接入预约。',),
                         rule_origin='inferred_function_tags' if inferred else 'official_function_tags')
            continue
        primary, records = _context(entity, pois, shops, items)
        if record_data_mode(entity, *records) != 'real' or any(r.get('status') in _INACTIVE for r in records):
            continue
        kind = reference['kind']
        if kind == 'item':
            tags = primary.get('tags')
            if tags is None:
                continue
            if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
                issue('INVALID_ITEM_TAGS', entity, message='标签格式不是文本数组，未生成特征关系。')
                continue
            evidence = primary.get('field_evidence')
            tag_evidence = evidence.get('tags') if isinstance(evidence, dict) else None
            provenance = dict(source=primary.get('tags_source'), content_origin=primary.get('tags_origin'))
            if record_data_mode(provenance, tag_evidence if isinstance(tag_evidence, dict) else {}) != 'real':
                issue('NONREAL_ITEM_TAGS_EXCLUDED', entity, message='标签来自模拟或推测，未加入真实特征网络。')
                continue
            unknown = 0
            for tag in tags:
                ident = _TRAIT_LOOKUP.get(tag.strip().casefold())
                if ident is None:
                    unknown += 1
                    continue
                add_edge(entity, 'has_trait', 'trait', ident, _TRAITS[ident][0], 'recorded',
                         'catalog.item.tags:explicit-registry-v1', _TRAIT_LIMITS, rule_origin='recorded_item_tags')
            if unknown:
                issue('UNMAPPED_ITEM_TAGS', entity, count=unknown,
                      message='部分标签尚无规范概念；原值保留在源记录中，不以菜名猜测标签。')
            continue

        # Even malformed callers cannot promote a floor collection to a shop.
        if kind == 'outlet' and (primary.get('entity_type') == 'floor_menu_collection'
                or primary.get('independent_merchant') is False or reference['id'].startswith('menu-collection-')):
            issue('COLLECTION_IS_NOT_OUTLET', entity, message='楼层菜单集合不作为独立窗口分类。')
            continue
        raw_category = primary.get('category')
        category_basis = 'catalog.' + ('poi' if kind == 'poi' else 'shop') + '.category'
        category_origin = 'recorded_category'
        if raw_category not in _CATEGORY:
            raw_category = entity.get('category')
            category_basis = 'safe_entity.category'
            category_origin = 'safe_entity_category'
        if raw_category not in _CATEGORY and kind == 'outlet':
            parent = pois.get(primary.get('poi_id') or entity.get('poi_id'), {})
            raw_category = parent.get('category')
            category_basis = 'catalog.parent_poi.category'
            category_origin = 'parent_category'
        category = _CATEGORY.get(raw_category)
        base = _base_name(entity.get('name'))
        named_services = [(service, cat) for service, cat, names in _NAMED_SERVICES if base in names]
        if _STUDY_NAME.fullmatch(base):
            named_services.append(('study', 'campus'))
        brand = next((b for b in _BRANDS if base in b[2]), None)
        refined = named_services[0][1] if named_services else brand[3] if brand else None
        cat_status = 'recorded'
        if refined and refined != category:
            if category is not None:
                issue('CATEGORY_NAME_RULE_DIFFERS', entity,
                      recorded_category=category, proposed_category=refined,
                      message='严格全名规则与原类别不同；仅派生推测分类，不覆盖源类别。')
            category, cat_status = refined, 'inferred'
            category_basis = 'name_rule:whole-business-name-v1'
            category_origin = 'exact_name_rule'
        if category:
            add_edge(entity, 'has_category', 'category', category, CATEGORY_NAMES[category],
                     cat_status, category_basis, _SERVICE_LIMITS,
                     original_category=raw_category, rule_origin=category_origin)
            general = _GENERAL_SERVICE.get(category)
            if general:
                add_edge(entity, 'provides_service', 'service', general, SERVICE_NAMES[general],
                         cat_status, category_basis + ':service-map-v1', _SERVICE_LIMITS,
                         original_category=raw_category, rule_origin=category_origin)
        else:
            issue('CATEGORY_NOT_CLASSIFIED', entity, message='类别无规范映射；保留地点，不从未知名称泛化业态。')
        specific = {'finance': 'financial-services', 'gate': 'campus-access', 'library': 'study'}.get(raw_category)
        if specific:
            add_edge(entity, 'provides_service', 'service', specific, SERVICE_NAMES[specific],
                     'recorded', category_basis + ':explicit-service-map-v1', _SERVICE_LIMITS,
                     original_category=raw_category, rule_origin='recorded_category')
        for service, _ in named_services:
            add_edge(entity, 'provides_service', 'service', service, SERVICE_NAMES[service],
                     'inferred', 'name_rule:exact-service-name-v1', _SERVICE_LIMITS,
                     original_category=raw_category, rule_origin='exact_name_rule')
        if brand:
            add_edge(entity, 'of_brand', 'brand', brand[0], brand[1], 'inferred',
                     'name_rule:whole-brand-name-with-optional-branch-v1',
                     ('名称符合已知品牌规则，未核实品牌授权或产权。',
                      '同品牌不代表同店、同菜单、同价格、同营业时间或相邻。'),
                     original_category=raw_category, rule_origin='exact_name_rule')

    return dict(nodes=[nodes[k] for k in sorted(nodes)],
                edges=[edges[k] for k in sorted(edges)],
                issues=sorted(issues, key=lambda value: (value['entity']['kind'], value['entity']['id'], value['code'])))
