// Public, bounded Agent DTOs only. No coordinates, account identity or executable
// instructions from a model response can become a map command.
const ENTITY_KINDS = new Set(['building', 'poi', 'outlet']);
const list = value => Array.isArray(value) ? value : [];
const text = (value, limit = 600) => typeof value === 'string' ? value.slice(0, limit) : '';
const key = ref => ref ? `${ref.kind}:${ref.id}` : '';

export function entityReference(value) {
  if (!value || !ENTITY_KINDS.has(value.kind) || typeof value.id !== 'string' ||
      !value.id.trim() || value.id.length > 300 || /[\x00-\x1f\x7f]/.test(value.id)) return null;
  return {kind: value.kind, id: value.id};
}

export function previousEntities(cards) {
  const refs = new Map();
  for (const card of list(cards)) {
    if (!card || card.simulation || card.data_mode === 'simulated' || card.type === 'schedule') continue;
    const ref = entityReference(card.outlet_id ? {kind: 'outlet', id: card.outlet_id} : card.ref) ||
      entityReference({kind: 'poi', id: card.poi_id || (card.type === 'place' ? card.id : '')});
    if (ref) refs.set(key(ref), ref);
    if (refs.size >= 12) break;
  }
  return [...refs.values()];
}

export function agentRequestContext(selected) {
  return {selected: entityReference(selected)};
}

export function collectOutletRecords(cards = [], relations = [], entities = []) {
  const found = new Map();
  const add = (record, parent = {}) => {
    if (!record || record.simulation || record.data_mode === 'simulated') return;
    const id = record.outlet_id || (record.ref?.kind === 'outlet' ? record.ref.id : record.id);
    const ref = entityReference({kind: 'outlet', id});
    if (!ref) return;
    const poiId = record.poi_id || parent.poi_id || (parent.type === 'place' ? parent.id : null);
    const old = found.get(id) || {};
    found.set(id, {...old, ref, name: text(record.outlet_name || record.name || old.name, 160),
      poi_id: poiId || old.poi_id || null, building_id: record.building_id || parent.building_id || old.building_id || null});
  };
  for (const card of list(cards)) {
    if (!card) continue;
    if (card.outlet_id) add({...card, name: card.outlet_name || '已录入窗口'});
    for (const outlet of list(card.outlets)) add(outlet, card);
    for (const group of [...list(card.menu_groups), ...list(card.menu)]) {
      if (group?.outlet_id) add({...group, name: group.outlet_name || '已录入窗口'}, card);
    }
  }
  for (const relation of list(relations)) {
    for (const record of [relation?.anchor, ...list(relation?.items),
      ...list(relation?.items).flatMap(item => [...list(item?.path?.nodes), ...list(item?.spatial_evidence?.path?.nodes)])]) {
      if (record?.ref?.kind === 'outlet') add(record);
    }
  }
  for (const entity of list(entities)) if (entity?.ref?.kind === 'outlet') add(entity);
  return [...found.values()];
}

export function loadedEntity(ref, {rows = [], buildings = [], outlets = []} = {}) {
  ref = entityReference(ref);
  if (!ref) return null;
  const records = ref.kind === 'building' ? buildings : ref.kind === 'poi' ? rows : outlets;
  const record = list(records).find(item => String(item?.ref?.id || item?.id || '') === ref.id);
  return record ? {ref, name: text(record.name, 160) || '未命名对象', record} : null;
}

export function resolveMapAction(action, catalog = {}) {
  if (!action || action.type !== 'focus_entity') return null;
  const entity = loadedEntity(action.entity, catalog);
  if (!entity) return null;
  const {ref, record} = entity;
  if (ref.kind === 'building') return {...entity, target: 'building', target_id: ref.id};
  const poi = ref.kind === 'poi' ? record : list(catalog.rows).find(row => row.id === record.poi_id);
  const buildingId = poi?.building_id || record.building_id;
  // Optional target hints must agree with the already loaded entity. Never use
  // an action's coordinates or substitute its arbitrary POI/building ID.
  if (action.poi_id && action.poi_id !== (poi?.id || record.poi_id)) return null;
  if (action.building_id && String(action.building_id) !== String(buildingId || '')) return null;
  if (poi) {
    const point = poi.display_anchor || poi.location;
    const inModel = point && Number.isFinite(point.x) && Number.isFinite(point.y) && Math.abs(point.x) <= 452 && Math.abs(point.y) <= 601;
    if (inModel || poi.map_reference) return {...entity, target: 'poi', target_id: poi.id};
  }
  if (buildingId && list(catalog.buildings).some(item => item.id === String(buildingId))) {
    return {...entity, target: 'building', target_id: String(buildingId)};
  }
  return null;
}

export function safeSourceUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}

export function sourceDetails(value, depth = 0) {
  if (depth > 3 || value == null) return [];
  if (typeof value === 'string') return value ? [text(value)] : [];
  if (Array.isArray(value)) return value.slice(0, 20).flatMap(item => sourceDetails(item, depth + 1));
  if (typeof value !== 'object') return [];
  return ['title', 'description', 'source', 'type', 'method', 'rule', 'rule_id', 'published_at',
    'confirmed_at', 'observed_at', 'retrieved_at', 'url', 'source_url'].flatMap(field => sourceDetails(value[field], depth + 1));
}

export function evidencePresentation(values) {
  return list(values).slice(0, 120).filter(item => item && ['fact', 'limitation'].includes(item.kind) && text(item.text))
    .map(item => ({id: text(item.id, 160), text: text(item.text, 2000), kind: item.kind,
      entity: entityReference(item.entity), source: sourceDetails(item.source),
      simulated: item.data_mode === 'simulated'}));
}

const RELATIONS = {contained_in: '包含关系', in_building: '所在建筑', on_floor: '所在楼层', same_building_member: '同楼',
  adjacent_to: '相邻', west_of: '位于西侧', east_of: '位于东侧', located_in_part: '所在区域', relative_to: '相对位置',
  next_in_roster: '名录顺序相邻', nearby_estimate: '直线近邻估计', within_radius: '直线范围内', has_category: '类别',
  provides_service: '提供服务', of_brand: '品牌', has_trait: '属性', offers_trait: '提供属性', service_complements: '功能互补推测',
  offered_by: '所属窗口', derived_from: '资料来源关系', same_floor: '同层', same_building: '同楼'};
const STATUSES = {confirmed: '已确认', recorded: '资料记录', computed: '计算结果', derived: '推导结果', inferred: '推测', unknown: '状态未注明'};
const labels = {neighbors: '直接关系', same_type: '同类比较', complementary: '功能组合', chain: '关系解释链'};

function edgePresentation(edge) {
  if (!edge || typeof edge !== 'object') return null;
  return {label: RELATIONS[edge.type] || '关系', status: STATUSES[edge.status] || '状态未注明',
    source: [...sourceDetails(edge.basis), ...sourceDetails(edge.evidence), ...sourceDetails(edge.source_links)],
    limitations: list(edge.limitations).filter(item => typeof item === 'string').map(item => text(item)),
    distance: Number.isFinite(edge.distance_m) ? `记录点直线距离约 ${edge.distance_m} 米；不是步行距离。` : ''};
}

export function relationPresentation(value) {
  if (!value || typeof value !== 'object') return null;
  const items = list(value.items).slice(0, 30).map(item => {
    const path = item?.path || {}, space = item?.spatial_evidence || {};
    const edges = [...list(item?.edges), ...list(path.edges), ...list(space.path?.edges)];
    const seen = new Set();
    return {name: text(item?.name, 160) || '未命名记录', ref: entityReference(item?.ref),
      kind: {building: '建筑', poi: '地点', outlet: '窗口', floor: '楼层', item: '菜单记录', menu_group: '菜单组',
        area: '区域', building_group: '建筑组', category: '类别', service: '服务', brand: '品牌', trait: '属性'}[item?.ref?.kind] || '关联记录',
      path: list(path.nodes).map(n => text(n?.name, 160)).filter(Boolean),
      spatialPath: list(space.path?.nodes).map(n => text(n?.name, 160)).filter(Boolean),
      concepts: list(item?.shared_concepts).map(n => text(n?.name, 160)).filter(Boolean),
      edges: edges.filter(edge => {if (!edge || seen.has(edge.id)) return false;seen.add(edge.id);return true;}).map(edgePresentation).filter(Boolean),
      limitations: [...list(item?.limitations), ...list(space.limitations)].filter(x => typeof x === 'string').map(x => text(x))};
  });
  return {title: labels[value.mode] || '地点关系', anchor: text(value.anchor?.name, 160), items,
    total: Number.isInteger(value.total) && value.total >= 0 ? value.total : items.length,
    truncated: value.truncated === true || list(value.items).length > 30,
    limitations: list(value.limitations).filter(x => typeof x === 'string').map(x => text(x)),
    gap: Number.isInteger(value.gaps?.semantic_matches_without_spatial_evidence) && value.gaps.semantic_matches_without_spatial_evidence > 0
      ? `${value.gaps.semantic_matches_without_spatial_evidence} 个功能相关记录缺少空间依据，未列为组合候选。` : ''};
}

export function agentResponseExtras(value) {
  return {relations: list(value?.relations).map(relationPresentation).filter(Boolean),
    evidence: evidencePresentation(value?.evidence), map_actions: list(value?.map_actions).slice(0, 60),
    notices: list(value?.context?.notices).filter(item => typeof item === 'string').map(item => text(item))};
}
