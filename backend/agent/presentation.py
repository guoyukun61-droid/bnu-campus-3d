"""Public presentation is derived, never written back over source evidence."""
import re

CATEGORIES = {
    'food': ('餐饮', {'canteen', 'restaurant', 'snack'}),
    'drinks': ('咖啡饮品', {'coffee', 'drink'}),
    'retail': ('便利购物', {'retail', 'supermarket'}),
    'services': ('生活服务', {'service', 'finance'}),
    'sports': ('体育场馆', {'sports'}),
    'campus': ('校园公共设施', {'building', 'gate', 'library', 'dormitory', 'public'}),
    'other': ('其他地点', set()),
}
TECHNICAL = re.compile(r'BD[-–]?09|GCJ|WGS|EPSG|UTM|GF2|坐标|白模|模型|轮廓|匹配|投影|配准|关联|吸附|截图|实测|纠偏|核验|层高|楼高|待核|用户确认|用户补充|官方资料|来源|采集|几何|建筑说明|https?://|[A-Z]:[\\/]', re.I)


def public_address(value):
    """Keep independent address clauses; uncertain mixed clauses stay admin-only."""
    if not isinstance(value, str):
        return ''
    value = re.sub(r'^(?:百度|原始)地址[：:]\s*', '', value.strip())
    clauses = re.split(r'[；;\n。]|\s+[|｜]\s+', value)
    return '；'.join(s.strip() for s in clauses if s.strip() and not TECHNICAL.search(s))[:240]


def category_info(record):
    category = record.get('category')
    key = next((k for k, (_, members) in CATEGORIES.items() if category in members), 'other')
    label = CATEGORIES[key][0]
    collection = {'food': '菜单', 'drinks': '饮品', 'retail': '商品'}.get(key)
    return dict(display_category=key, category_label=label,
                collection_label=collection,
                capabilities=dict(items=collection is not None),
                hours_label='开放时间' if key in ('sports', 'campus') else '营业时间')


def public_source(value):
    if value in ('simulated', 'menu_photo', 'baidu_place_v2', 'field_observation'):
        return value
    if isinstance(value, str) and value.startswith('user_'):
        return 'user_reported'
    return 'published'


def public_hours_notes(value):
    if not isinstance(value,str):return ''
    return '；'.join(s.strip() for s in re.split(r'[；;。\n]',value) if s.strip() and not re.search(r'用户.*(?:确认|补充|提供)|原ID|沿用|合并|快照|批次|字段|记录ID|审核|坐标|匹配|建筑关联',s,re.I))[:240]


def clean_card(card):
    """Shared boundary for direct API and tool results sent to the model."""
    result = dict(card)
    result['address'] = public_address(card.get('address'))
    if 'hours_notes' in result:
        result['hours_notes'] = public_hours_notes(result['hours_notes'])
    if 'source' in result:
        result['source'] = public_source(result['source'])
    return result
