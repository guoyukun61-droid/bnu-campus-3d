"""Evidence-carrying POI graph, derived without mutating any catalogue or geometry.

The graph separates identity, containment, topology, metric estimates and semantic
discovery. Concept hubs avoid dense all-to-all category edges. No route is invented.
"""
import copy
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from .poi_semantics import build_semantics

CONTRACT_VERSION = 'poi-network.v1'
RULE_VERSION = '1.20.0-data.3'
POLICY_FILE = Path(__file__).parent / 'seeds/poi-network-policy.json'
CONCEPTS = {'category', 'service', 'brand', 'trait'}
SPATIAL_LIMIT = '仅已有记录点之间的平面直线估算；入口、通行、步行耗时尚未核实。'


def node_key(ref):
    return ref['kind'] + ':' + str(ref['id'])


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def load_policy(policy=None):
    p = copy.deepcopy(policy) if policy is not None else json.loads(POLICY_FILE.read_text(encoding='utf-8'))
    if p.get('rule_version') != RULE_VERSION:
        raise ValueError('Unsupported POI network policy')
    for field, lower, upper in (('nearby_radius_m', 1, 1000), ('nearest_neighbors_per_poi', 1, 30),
                               ('minimum_direction_distance_m', 1, 100), ('max_local_coordinate_m', 1000, 10000)):
        value = p.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lower <= value <= upper:
            raise ValueError('Invalid network policy: ' + field)
    if not isinstance(p['nearest_neighbors_per_poi'], int):
        raise ValueError('Neighbor bound must be an integer')
    if p.get('coordinate_frame', {}).get('crs') != 'local EPSG:32650':
        raise ValueError('Network requires the campus local metre frame')
    origin = p['coordinate_frame'].get('origin_utm')
    if not isinstance(origin, list) or len(origin) != 2 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in origin):
        raise ValueError('Invalid campus origin')
    if not isinstance(p.get('complementary_services'), list) or len(p['complementary_services']) > 30:
        raise ValueError('Invalid complementarity rules')
    for rule in p['complementary_services']:
        values = rule.get('services') if isinstance(rule, dict) else None
        if not isinstance(values, list) or len(values) != 2 or len(set(values)) != 2 or not all(isinstance(v, str) for v in values):
            raise ValueError('Invalid complementarity rule')
    return p


def _recorded_point(poi, entity, policy):
    # Building centres, visual facade anchors and relative references are deliberately
    # excluded, even when a stale numerical location remains in the source row.
    if entity.get('map_target', {}).get('kind') != 'recorded_point':
        return None, 'building_or_relative_anchor' if entity.get('map_target', {}).get('kind') != 'unknown' else 'missing_point'
    point = poi.get('map_point') or poi.get('location')
    if not isinstance(point, dict):
        return None, 'missing_point'
    precision = str(point.get('precision', '')).casefold()
    if any(token in precision for token in ('building', 'centroid', 'relative', 'area', 'display', 'illustrat', 'reference')):
        return None, 'point_level_anchor'
    crs = point.get('crs', poi.get('location_crs'))
    if crs != policy['coordinate_frame']['crs']:
        return None, 'crs_unknown_or_mismatch'
    origin = point.get('origin_utm', poi.get('origin_utm'))
    if origin is not None and origin != policy['coordinate_frame']['origin_utm']:
        return None, 'origin_mismatch'
    if any(isinstance(point.get(k), bool) or not isinstance(point.get(k), (int, float)) or not math.isfinite(point[k])
           or abs(point[k]) > policy['max_local_coordinate_m'] for k in ('x', 'y')):
        return None, 'invalid_or_nonlocal_coordinate'
    source = (str(poi.get('location_source', '')) + ' ' + str(point.get('source', ''))).casefold()
    if any(token in source for token in ('simulat', 'inferred', 'generated', 'centroid', 'display_anchor')):
        return None, 'illustrative_or_inferred_point'
    if poi.get('location_review_status') == 'conflicting_source_points':
        return None, 'unresolved_coordinate_conflict'
    return (point['x'], point['y']), None


def _relation_status(relation):
    return 'confirmed' if relation.get('basis') == 'user_confirmation' else 'recorded'


def build_poi_network(snapshot, catalog, policy=None):
    """Pure bounded graph assembly from safe projected entities + normalized catalogue."""
    p = load_policy(policy)
    nodes = copy.deepcopy(snapshot['entities'])
    index = {node_key(n['ref']): n for n in nodes}
    if len(index) != len(nodes):
        raise ValueError('Duplicate network node')
    raw_pois = {r['id']: r for r in catalog.get('pois', [])}
    for n in nodes:
        raw = raw_pois.get(n['ref']['id'] if n['ref']['kind'] == 'poi' else n.get('poi_id'), {})
        scope = raw.get('zone')
        if scope is not None:
            n['scope_status'] = scope
        n['graph_visible'] = (n.get('browseable', False) and n.get('data_mode', 'real') == 'real'
                              and not n.get('canonical_poi_id') and scope not in {'outside', 'pending'})

    semantics = build_semantics([n for n in nodes if n['graph_visible']], catalog)
    for concept in semantics['nodes']:
        ident = node_key(concept['ref'])
        if ident in index or concept['ref']['kind'] not in CONCEPTS:
            raise ValueError('Invalid semantic node')
        concept = copy.deepcopy(concept)
        concept['graph_visible'] = True
        nodes.append(concept)
        index[ident] = concept
    edges, issues = {}, copy.deepcopy(semantics.get('issues', []))

    def add_edge(relation):
        r = copy.deepcopy(relation)
        a, b = node_key(r['subject']), node_key(r['object'])
        if a not in index or b not in index:
            raise ValueError('Dangling network edge')
        if a == b:
            raise ValueError('Self network edge')
        r.setdefault('status', _relation_status(r))
        if r['status'] not in {'confirmed', 'recorded', 'computed', 'inferred'}:
            raise ValueError('Invalid relationship evidence status')
        r.setdefault('limitations', [])
        r.setdefault('basis', 'existing_record')
        modes = {index[v].get('data_mode', 'real') for v in (a, b)}
        r['data_mode'] = 'simulated' if 'simulated' in modes else 'inferred' if 'inferred' in modes else 'real'
        r['graph_visible'] = all(index[v]['graph_visible'] for v in (a, b))
        r['rule_version'] = RULE_VERSION
        r['evidence_refs'] = list({node_key(v): v for v in r.get('evidence_refs', [r['subject'], r['object']])}.values())
        if any(node_key(v) not in index for v in r['evidence_refs']):
            raise ValueError('Dangling evidence reference')
        identity = [r['type'], a, b, r.get('group_id'), r.get('building_part')]
        r['id'] = 'edge-' + digest(identity)[:24]
        if r['id'] in edges and edges[r['id']] != r:
            raise ValueError('Conflicting duplicate relationship')
        edges[r['id']] = r
        return r['id']

    for relation in snapshot['relations']:
        r = copy.deepcopy(relation)
        if r['type'] in {'relative_to', 'adjacent_to', 'west_of', 'east_of', 'located_in_part', 'same_building_member'}:
            r['limitations'] = ['定性空间关系，不包含精确店门坐标、可达性或步行耗时。']
        if r['type'] == 'ordered_along':
            r['limitations'] = ['名录顺序不是店门距离或连续通行关系。']
        add_edge(r)
    for relation in semantics['edges']:
        add_edge(relation)

    # An outlet may have a rice option without every dish being rice. Carry the
    # witnessed item paths; do not derive absence, allergens or current stock.
    offered = {node_key(e['subject']): e for e in edges.values()
               if e['type'] == 'offered_by' and e['graph_visible']}
    trait_witnesses = defaultdict(list)
    for e in list(edges.values()):
        sale = offered.get(node_key(e['subject']))
        if e['type'] == 'has_trait' and e['graph_visible'] and sale:
            trait_witnesses[(node_key(sale['object']), node_key(e['object']))].append((sale, e))
    for (outlet, trait), witnesses in sorted(trait_witnesses.items()):
        add_edge(dict(type='offers_trait', subject=index[outlet]['ref'], object=index[trait]['ref'],
                      status='computed', basis='recorded_menu_item_paths',
                      recorded_item_count=len(witnesses),
                      supporting_edge_ids=sorted({e['id'] for pair in witnesses for e in pair}),
                      evidence_refs=[index[outlet]['ref'], index[trait]['ref']] +
                                    [pair[0]['subject'] for pair in witnesses],
                      limitations=['有真实记录菜品携带该标签；不表示全部菜单、实时在售或饮食安全，也不能由无标签推导无该成分。']))

    # Materialized containment shortcuts are backed by paths; no O(n²) same-floor
    # cliques. Queries compare membership in these hubs when useful.
    parents = {node_key(r['subject']): r for r in edges.values()
               if r['type'] == 'contained_in' and r['graph_visible'] and r['data_mode'] == 'real'}
    for n in nodes:
        if n['ref']['kind'] not in {'poi', 'outlet'} or not n['graph_visible']:
            continue
        current, path, seen = node_key(n['ref']), [], set()
        while current in parents:
            if current in seen:
                raise ValueError('Network containment cycle')
            seen.add(current)
            edge = parents[current]
            path.append(edge['id'])
            current = node_key(edge['object'])
            target = index[current]
            if target['ref']['kind'] in {'building', 'floor'}:
                add_edge(dict(type='in_building' if target['ref']['kind'] == 'building' else 'on_floor',
                              subject=n['ref'], object=target['ref'], status='computed',
                              basis='containment_path', supporting_edge_ids=list(path),
                              limitations=['由已有包含关系推导；同楼/同层不保证室内连通或营业。']))

    sequences = defaultdict(list)
    for e in edges.values():
        if e['type'] == 'ordered_along' and e['graph_visible'] and e['data_mode'] == 'real':
            order = e.get('order')
            if isinstance(order, (int, float)) and not isinstance(order, bool) and math.isfinite(order):
                sequences[node_key(e['object'])].append(e)
    for group_id, members in sorted(sequences.items()):
        members.sort(key=lambda e: (e['order'], node_key(e['subject'])))
        duplicate_ranks = {rank for rank, count in Counter(e['order'] for e in members).items() if count > 1}
        if duplicate_ranks:
            issues.append(dict(code='AMBIGUOUS_SEQUENCE_RANK', entity=members[0]['object'], severity='medium'))
        for first, second in zip(members, members[1:]):
            if first['order'] in duplicate_ranks or second['order'] in duplicate_ranks:
                continue
            add_edge(dict(type='next_in_roster', subject=first['subject'], object=second['subject'],
                          group_id=group_id, status='computed', basis='ordered_roster',
                          direction=first.get('direction') if first.get('direction') == second.get('direction') else 'unknown',
                          order_gap=second['order'] - first['order'],
                          supporting_edge_ids=[first['id'], second['id']],
                          limitations=['在已记录名录中相继；可能漏店，不保证物理紧邻或可直接通行。']))

    points, point_gaps = {}, Counter()
    eligible_pois = [n for n in nodes if n['ref']['kind'] == 'poi' and n['graph_visible']]
    for n in eligible_pois:
        point, gap = _recorded_point(raw_pois.get(n['ref']['id'], {}), n, p)
        if point:
            points[node_key(n['ref'])] = point
        else:
            point_gaps[gap] += 1
            issues.append(dict(code='METRIC_POINT_UNAVAILABLE', entity=n['ref'], severity='info', reason=gap))
    pair_distances, selections, eligible_pairs = {}, set(), Counter()
    point_keys = sorted(points)
    candidates = defaultdict(list)
    for i, a in enumerate(point_keys):
        for b in point_keys[i + 1:]:
            d = math.dist(points[a], points[b])
            if d <= p['nearby_radius_m']:
                pair_distances[(a, b)] = d
                candidates[a].append((d, b)); candidates[b].append((d, a))
    for a in point_keys:
        choices = sorted(candidates[a])
        eligible_pairs[a] = len(choices)
        for _, b in choices[:p['nearest_neighbors_per_poi']]:
            selections.add(tuple(sorted((a, b))))
    truncated_points = sum(count > p['nearest_neighbors_per_poi'] for count in eligible_pairs.values())
    for a, b in sorted(selections):
        d = pair_distances[(a, b)]
        dx, dy = points[b][0] - points[a][0], points[b][1] - points[a][1]
        bearing = (math.degrees(math.atan2(dx, dy)) + 360) % 360 if d >= p['minimum_direction_distance_m'] else None
        direction = ('north', 'northeast', 'east', 'southeast', 'south', 'southwest', 'west', 'northwest')[int((bearing + 22.5) // 45) % 8] if bearing is not None else 'uncertain_at_short_distance'
        add_edge(dict(type='nearby_estimate', subject=index[a]['ref'], object=index[b]['ref'],
                      status='computed', basis='recorded_local_points', distance_m=round(d, 1),
                      bearing_degrees=round(bearing, 1) if bearing is not None else None,
                      direction=direction, symmetric=True, precision='recorded_unverified',
                      limitations=[SPATIAL_LIMIT, '坐标近邻按半径与每点前K条截取；不等于完整周边名录。']))
    if truncated_points:
        issues.append(dict(code='NEARBY_GRAPH_CAPPED', severity='info', affected_poi_count=truncated_points,
                           note='稠密区域每点仅选最近K个，图中仍可能收到其他点的反向入选；无边不表示不近。'))

    for rule in p['complementary_services']:
        a, b = [{'kind': 'service', 'id': v} for v in rule['services']]
        if node_key(a) in index and node_key(b) in index:
            add_edge(dict(type='service_complements', subject=a, object=b, symmetric=True,
                          status='inferred', basis='explicit_task_rule', task=rule.get('task'),
                          limitations=['服务功能上的组合候选；实际地点还须有空间依据并核对时段、预算和通行。']))
    issues.append(dict(code='NO_VERIFIED_ROUTE_NETWORK', severity='medium',
                       note='未接入经核验的道路/入口/楼梯/闸门通行网络；不输出可达或顺路事实。'))
    if not catalog.get('walking_times'):
        issues.append(dict(code='WALKING_TIMES_EMPTY', severity='medium', note='人工步行时间表尚未录入。'))
    result = dict(contract_version=CONTRACT_VERSION, rule_version=RULE_VERSION,
                  policy=p, policy_hash='sha256:' + digest(p),
                  nodes=sorted(nodes, key=lambda n: node_key(n['ref'])),
                  edges=sorted(edges.values(), key=lambda e: e['id']), issues=issues,
                  limitations=p['limitations'])
    result['summary'] = dict(node_count=len(nodes), edge_count=len(edges),
                            node_kinds=dict(Counter(n['ref']['kind'] for n in nodes)),
                            edge_types=dict(Counter(e['type'] for e in edges.values())),
                            evidence_statuses=dict(Counter(e['status'] for e in edges.values())),
                            visible_edge_types=dict(Counter(e['type'] for e in edges.values() if e['graph_visible'])),
                            edge_data_modes=dict(Counter(e['data_mode'] for e in edges.values())),
                            visible_poi_count=len(eligible_pois), metric_point_count=len(points),
                            point_gaps=dict(point_gaps), nearby_pair_count=len(selections),
                            within_radius_pair_count=len(pair_distances), capped_poi_count=truncated_points,
                            issue_codes=dict(Counter(i['code'] for i in issues)))
    validate_network(result)
    return result


def validate_network(network):
    node_ids = {node_key(n['ref']) for n in network['nodes']}
    edge_ids = {e['id'] for e in network['edges']}
    if len(node_ids) != len(network['nodes']) or len(edge_ids) != len(network['edges']):
        raise ValueError('Network IDs are not unique')
    for e in network['edges']:
        if node_key(e['subject']) not in node_ids or node_key(e['object']) not in node_ids:
            raise ValueError('Dangling network edge')
        if node_key(e['subject']) == node_key(e['object']):
            raise ValueError('Self network edge')
        if any(v not in edge_ids for v in e.get('supporting_edge_ids', [])):
            raise ValueError('Missing supporting edge')
        if e['type'] in {'walkable_to', 'route_to', 'accessible_to', 'open_now'}:
            raise ValueError('Unsupported factual route or live state')
    return True
