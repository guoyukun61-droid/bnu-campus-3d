"""Bounded entity references, resolved from the current public catalogue only.

Selection is conversation context, never a measured position or an authority.
No client-supplied names, coordinates or history facts survive this boundary.
"""
import re
import unicodedata


KINDS = frozenset({'poi', 'building', 'outlet'})
MAX_PREVIOUS = 12
INACTIVE = frozenset({'archived', 'inactive', 'historical', 'closed'})
PRIVATE = re.compile(r'(?i)(?:(?<![a-z0-9])[a-z]:[\\/]|\\\\|file://|/(?:Users|home|data/life)/|sk-[a-z0-9]{12,})')


def _reference(value):
    if not isinstance(value, dict) or set(value) != {'kind', 'id'}:
        raise ValueError('对象引用仅支持 kind 和 id')
    kind, ident = value['kind'], value['id']
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError('对象类型无效')
    if (not isinstance(ident, str) or not ident.strip() or len(ident) > 100
            or any(unicodedata.category(c).startswith('C') for c in ident)):
        raise ValueError('对象 ID 无效')
    return dict(kind=kind, id=ident)


def validate_context(value=None):
    """Normalize an omitted/cleared selection; reject all client fact fields."""
    if value is None:
        return {'selected': None}
    if not isinstance(value, dict) or set(value) - {'selected'}:
        raise ValueError('上下文仅支持 selected')
    selected = value.get('selected')
    return {'selected': None if selected is None else _reference(selected)}


def validate_previous_entities(value=None):
    """Validate anonymous request references; account callers reconstruct them."""
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_PREVIOUS:
        raise ValueError('上轮对象须为最多 12 项的数组')
    result, seen = [], set()
    for value_ref in value:
        ref = _reference(value_ref)
        token = (ref['kind'], ref['id'])
        if token not in seen:
            seen.add(token)
            result.append(ref)
    return result


def previous_entities_from_cards(cards):
    """Recover identities from older cards without interpreting item IDs as POIs."""
    if not isinstance(cards, list):
        return []
    result, seen = [], set()

    def add(value):
        try:
            ref = _reference(value)
        except ValueError:
            return
        token = (ref['kind'], ref['id'])
        if token not in seen and len(result) < MAX_PREVIOUS:
            seen.add(token)
            result.append(ref)

    for card in cards:
        if not isinstance(card, dict):
            continue
        # A food card's id identifies an Item; preserve its window first.
        if card.get('outlet_id'):
            add(dict(kind='outlet', id=card['outlet_id']))
        if card.get('poi_id'):
            add(dict(kind='poi', id=card['poi_id']))
        if isinstance(card.get('ref'), dict):
            add(card['ref'])
        elif not card.get('poi_id') and not card.get('outlet_id') and card.get('type') in {'place', 'building', 'outlet'}:
            add(dict(kind={'place': 'poi'}.get(card['type'], card['type']), id=card.get('id')))
        if len(result) == MAX_PREVIOUS:
            break
    return result


def _public_text(value, maximum=160):
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        text = str(value)
        if text and not PRIVATE.search(text) and not any(unicodedata.category(c).startswith('C') for c in text):
            return text[:maximum]
    return None


def _public_entity(entity, pois, mode):
    """Return identity metadata only; facts such as menus require a tool query."""
    ref = entity.get('ref')
    try:
        ref = _reference(ref)
    except ValueError:
        return None
    data_mode = entity.get('data_mode', 'real')
    if (not entity.get('browseable') or entity.get('source_active') is False
            or entity.get('operational_status') in INACTIVE or entity.get('status') in INACTIVE
            or entity.get('canonical_poi_id') or entity.get('canonical_outlet_id')
            or data_mode not in ({'real'} if mode == 'real' else {'real', 'simulated'})
            or mode == 'real' and entity.get('is_simulated')):
        return None
    poi_id = ref['id'] if ref['kind'] == 'poi' else entity.get('poi_id')
    poi = pois.get(poi_id)
    if poi and (poi.get('status') in INACTIVE or poi.get('canonical_poi_id')
                or poi.get('business_status') in {'暂停营业', '可能已关闭', '已关闭'}):
        return None
    result = dict(ref, name=_public_text(entity.get('name')) or '未命名记录',
                  data_mode=data_mode, is_simulated=data_mode == 'simulated')
    if poi_id and (text := _public_text(poi_id, 100)):
        result['poi_id'] = text
    building_id = ref['id'] if ref['kind'] == 'building' else entity.get('building_id')
    if not building_id:
        target = entity.get('map_target') or {}
        if target.get('kind') == 'building_anchor':
            building_id = target.get('building_id')
    if not building_id:
        building_id = next((p['ref']['id'] for p in entity.get('breadcrumbs', [])
                            if p.get('ref', {}).get('kind') == 'building'), None)
    if building_id and (text := _public_text(building_id, 100)):
        result['building_id'] = text
    if entity.get('floor') is not None and (text := _public_text(entity['floor'], 80)):
        result['floor'] = text
    return result


def resolve_context(tools, context=None, previous_entities=None, mode='real'):
    """Resolve refs using the caller's frozen CampusTools; never set conditions."""
    selected = validate_context(context)['selected']
    previous = validate_previous_entities(previous_entities)
    if mode not in ('real', 'demo'):
        raise ValueError('模式无效')
    result = dict(selected=None, previous_entities=[], notices=[])
    if selected is None and not previous:
        return result
    catalog = tools.snapshot()
    snapshot = tools.relation_snapshot(catalog)
    pois = {p['id']: p for p in catalog['pois']}
    entities = {}
    for entity in snapshot['entities']:
        public = _public_entity(entity, pois, mode)
        if public:
            entities[(public['kind'], public['id'])] = public
    if selected:
        result['selected'] = entities.get((selected['kind'], selected['id']))
        if result['selected'] is None:
            result['notices'].append('所选对象在当前模式下不可用，已清除本轮选择。')
    for ref in previous:
        public = entities.get((ref['kind'], ref['id']))
        if public:
            result['previous_entities'].append(dict(public))
    if len(result['previous_entities']) < len(previous):
        result['notices'].append('部分上轮对象已不可用，本轮不再引用。')
    return result


def resolve_entity(tools, reference, mode='real'):
    """Shared identity gate for detail tools; unavailable entities return None.

    Callers may query public details after this check, using the returned kind/id.
    This helper intentionally returns no description, location or menu facts.
    """
    return resolve_context(tools, {'selected': _reference(reference)}, mode=mode)['selected']
