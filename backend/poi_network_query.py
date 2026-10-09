"""Bounded, public read models for the derived POI graph; never route planning.

This module deliberately does not import life_relations or load a private store.
All traversal uses a caller-supplied, versioned snapshot and real visible nodes.
"""
from collections import Counter, defaultdict, deque
import heapq
import math
import re

MODES = {'neighbors', 'same_type', 'complementary', 'chain'}
CONCEPTS = {'category', 'service', 'brand', 'trait'}
SEMANTIC = {'has_category', 'provides_service', 'of_brand', 'has_trait', 'offers_trait'}
ALIASES = {'same_as', 'alias_of', 'canonical_of'}
PARENTS = {'contained_in', 'same_building_member', 'in_building', 'on_floor'}
BASE_LIMITS = [
    '关系解释不是导航路线，不保证步行可达、入口位置或无障碍通行。',
    '仅查询真实且可浏览的记录；同类或互补不保证预算、饮食、营业或预约条件。',
]
PRIVATE = re.compile(r'(?i)(?:(?<![a-z0-9])[a-z]:[\\/]|\\\\|file://|/(?:Users|home|data/life)/|sk-[a-z0-9]{12,})')


def _text(value, maximum=600):
    return value[:maximum] if isinstance(value, str) and not PRIVATE.search(value) else None


def _ref(value):
    if not isinstance(value, dict):
        return None
    kind, ident = value.get('kind'), value.get('id')
    if not isinstance(kind, str) or not isinstance(ident, (str, int)) or isinstance(ident, bool):
        return None
    ident = str(ident)
    if len(kind) > 80 or len(ident) > 300 or not _text(kind, 80) or not _text(ident, 300):
        return None
    return {'kind': kind, 'id': ident}


def _key(value):
    r = _ref(value)
    return (r['kind'], r['id']) if r else None


def _limits(value):
    values = value if isinstance(value, list) else [value]
    return list(dict.fromkeys(v for v in (_text(x) for x in values) if v))[:24]


def _evidence(value, depth=0):
    """Explicit public provenance keys, not arbitrary source dictionaries."""
    if depth > 3:
        return None
    if isinstance(value, str):
        return _text(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value if math.isfinite(value) else None
    if isinstance(value, list):
        return [v for item in value[:20] if (v := _evidence(item, depth + 1)) is not None]
    if isinstance(value, dict):
        allowed = {'source', 'type', 'title', 'url', 'source_url', 'published_at', 'retrieved_at',
                   'confirmed_at', 'observed_at', 'rule', 'rule_id', 'method', 'status', 'scope',
                   'kind', 'id', 'relation', 'batch', 'description'}
        return {k: v for k in sorted(allowed & value.keys())
                if (v := _evidence(value[k], depth + 1)) is not None}
    return None


def _visible(node):
    return (bool(node.get('graph_visible', node.get('browseable', False)))
            and node.get('browseable') is not False
            and node.get('data_mode', 'real') == 'real' and not node.get('is_simulated')
            and not node.get('canonical_poi_id') and not node.get('canonical_outlet_id')
            and node.get('operational_status') not in {'archived', 'inactive', 'historical', 'closed'}
            and node.get('status') not in {'archived', 'inactive', 'historical', 'closed'}
            and node.get('scope_status') not in {'outside', 'pending'})


def _merchant_basename(name):
    """For an already-known parent only: ignore one explicit branch suffix.

    No fuzzy brand matching, arbitrary parentheses removal, or cross-parent merge.
    Dietary notes such as （清真） and independent window names stay distinct.
    """
    value = re.sub(r'\s+', '', str(name or '')).casefold()
    return re.sub(r'[（(][^()（）]+店[)）]$', '', value)


def _card(node):
    result = {'ref': _ref(node['ref']), 'name': _text(node.get('name'), 160) or '未命名记录',
              'data_mode': 'real', 'browseable': True}
    for field in ('poi_id', 'floor', 'building_id', 'scope_status', 'category', 'description_status'):
        if node.get(field) is not None and (value := _text(str(node[field]), 160)):
            result[field] = value
    if node['ref']['kind'] in CONCEPTS:
        result['concept'] = True
    return result


class _Graph:
    def __init__(self, network):
        self.nodes = {_key(n.get('ref')): n for n in network.get('nodes', [])
                      if isinstance(n, dict) and _key(n.get('ref')) and _visible(n)}
        self.edges = []
        self.adj = defaultdict(list)
        self.out = defaultdict(list)
        self.semantic = defaultdict(dict)
        for edge in network.get('edges', []):
            if not isinstance(edge, dict) or edge.get('type') in ALIASES:
                continue
            a, b = _key(edge.get('subject')), _key(edge.get('object'))
            if a not in self.nodes or b not in self.nodes or a == b:
                continue
            self.edges.append(edge)
        # A materialized shortcut must not smuggle traversal through an excluded
        # alias/closed/simulated node in its supporting containment chain.
        while True:
            available = {e.get('id') for e in self.edges}
            filtered = [e for e in self.edges if all(i in available for i in e.get('supporting_edge_ids', []))]
            if len(filtered) == len(self.edges):
                break
            self.edges = filtered
        for edge in self.edges:
            a, b = _key(edge['subject']), _key(edge['object'])
            self.adj[a].append((b, edge)); self.adj[b].append((a, edge))
            self.out[a].append((b, edge))
            if edge.get('type') in SEMANTIC and b[0] in CONCEPTS:
                self.semantic[a][b] = edge
        self.edge_ids = {e.get('id') for e in self.edges}
        for pairs in self.adj.values():
            pairs.sort(key=lambda pair: (pair[0], str(pair[1].get('id', ''))))

    def edge(self, e):
        result = {'id': _text(e.get('id'), 160), 'type': _text(e.get('type'), 80),
                  'subject': _ref(e['subject']), 'object': _ref(e['object']),
                  'status': _text(e.get('status'), 40), 'basis': _evidence(e.get('basis')),
                  'limitations': _limits(e.get('limitations', [])),
                  'rule_version': _text(e.get('rule_version'), 80)}
        for field in ('evidence', 'source_links'):
            if e.get(field) is not None:
                result[field] = _evidence(e[field])
        for field in ('direction', 'precision', 'task', 'building_part', 'relation', 'original_category', 'rule_origin'):
            if (value := _text(e.get(field), 200)) is not None:
                result[field] = value
        for field in ('distance_m', 'bearing_degrees', 'order_gap', 'recorded_item_count'):
            value = e.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                result[field] = value
        if e.get('symmetric') is True:
            result['symmetric'] = True
        refs = [r for raw in e.get('evidence_refs', [])
                if _key(raw) in self.nodes and (r := _ref(raw))]
        support = [i for i in e.get('supporting_edge_ids', []) if i in self.edge_ids and _text(i, 160)]
        result.update(evidence_refs=refs[:12], evidence_refs_total=len(refs),
                      evidence_refs_truncated=len(refs) > 12,
                      supporting_edge_ids=support[:24], supporting_edge_ids_total=len(support),
                      supporting_edge_ids_truncated=len(support) > 24)
        return result

    def path(self, start, steps):
        nodes = [start] + [n for n, _ in steps]
        return {'nodes': [_card(self.nodes[n]) for n in nodes],
                'edges': [self.edge(e) for _, e in steps], 'hop_count': len(steps),
                'is_route': False}

    def ancestors(self, start):
        # Only directed containment, never adjacency or area membership. Shortcuts
        # generally reduce this to one hop; a fallback supports older graph fixtures.
        result, seen, queue = {}, {start}, deque([(start, [])])
        if start[0] in {'building', 'floor', 'building_group'}:
            result[start] = []
        while queue:
            current, path = queue.popleft()
            if len(path) >= 6:
                continue
            for other, edge in self.out[current]:
                if edge.get('type') not in PARENTS or other in seen or other[0] in CONCEPTS | {'area'}:
                    continue
                seen.add(other)
                steps = path + [(other, edge)]
                if other[0] in {'building', 'floor', 'building_group'}:
                    result[other] = steps
                queue.append((other, steps))
        return result

    def shared_space(self, a, b, *, building_only=False):
        left, right = self.ancestors(a), self.ancestors(b)
        shared = set(left) & set(right)
        if building_only:
            shared = {k for k in shared if k[0] in {'building', 'building_group'}}
        if not shared:
            return None
        common = min(shared, key=lambda k: (k[0] != 'floor', len(left[k]) + len(right[k]), k))
        reverse = list(reversed(right[common]))
        steps = left[common] + [(b if i == len(reverse) - 1 else reverse[i + 1][0], e)
                                for i, (_, e) in enumerate(reverse)]
        return {'type': 'same_floor' if common[0] == 'floor' else 'same_building',
                'shared': _ref(self.nodes[common]['ref']), 'path': self.path(a, steps),
                'limitations': ['同楼或同层不保证室内连通、当前营业或可进入。']}


def _base(snapshot):
    network = snapshot.get('network') or {}
    return {'contract_version': 'poi-network.v1', 'snapshot_id': snapshot.get('snapshot_id'),
            'rule_version': network.get('rule_version'), 'configured': bool(network),
            'limitations': _limits(BASE_LIMITS + network.get('limitations', []))}


def network_summary(snapshot):
    result = _base(snapshot)
    network = snapshot.get('network') or {}
    graph = _Graph(network)
    # Recompute safe aggregate counts; neither raw nodes nor arbitrary issues leak.
    result.update(items=[], total=len(graph.nodes), loaded_count=0, truncated=False,
                  summary={'visible_node_count': len(graph.nodes), 'visible_edge_count': len(graph.edges),
                           'node_kinds': dict(Counter(k[0] for k in graph.nodes)),
                           'edge_types': dict(Counter(e['type'] for e in graph.edges)),
                           'evidence_statuses': dict(Counter(e.get('status', 'unknown') for e in graph.edges)),
                           'issue_codes': dict(Counter(i['code'] for i in network.get('issues', [])
                                                      if isinstance(i, dict) and _text(i.get('code'), 80)))})
    for field in ('metric_point_count', 'nearby_pair_count', 'within_radius_pair_count', 'capped_poi_count'):
        value = network.get('summary', {}).get(field)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            result['summary'][field] = value
    if not network:
        result['limitations'].append('该快照未配置 POI 关系网络；既有实体接口仍可使用。')
    return result


def query_network(snapshot, *, kind=None, ident=None, mode='neighbors', limit=12):
    """Return deterministic, bounded cards with evidence paths, not routes.

    same_type compares identical entity kinds; complementary may cross POI,
    outlet and building kinds. chain returns one evidence-prioritized 2–3-hop explanation
    per entity and excludes area hubs, alias edges and unavailable nodes.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 30 or mode not in MODES:
        raise ValueError('Invalid network mode or limit')
    if not isinstance(kind, str) or not re.fullmatch(r'[a-z_]{1,40}', kind):
        raise ValueError('Invalid entity kind')
    if not isinstance(ident, str) or not 1 <= len(ident) <= 300 or any(ord(c) < 32 for c in ident):
        raise ValueError('Invalid entity ID')
    graph = _Graph(snapshot.get('network') or {})
    anchor = (kind, ident)
    if anchor not in graph.nodes:
        raise KeyError('Entity unavailable in network')
    result = _base(snapshot)
    result.update(mode=mode, anchor=_card(graph.nodes[anchor]))
    found, semantic_without_space = {}, 0

    def row(target, steps, **extra):
        return {**_card(graph.nodes[target]), 'path': graph.path(anchor, steps),
                'limitations': _limits([v for _, e in steps for v in _limits(e.get('limitations', []))]),
                **extra}

    if mode == 'neighbors':
        for target, edge in graph.adj[anchor]:
            if target not in found:
                found[target] = row(target, [(target, edge)], edges=[])
            found[target]['edges'].append(graph.edge(edge))
    elif mode == 'same_type':
        for target in sorted(graph.nodes):
            if target == anchor or target[0] != kind or kind in CONCEPTS:
                continue
            shared = sorted(set(graph.semantic[anchor]) & set(graph.semantic[target]),
                            key=lambda k: ({'brand': 0, 'trait': 1, 'service': 2, 'category': 3}[k[0]], k))
            space = graph.shared_space(anchor, target)
            if shared:
                concept = shared[0]
                steps = [(concept, graph.semantic[anchor][concept]), (target, graph.semantic[target][concept])]
                found[target] = row(target, steps,
                                    shared_concepts=[_card(graph.nodes[c]) for c in shared],
                                    spatial_evidence=space)
    elif mode == 'complementary':
        services = {k: e for k, e in graph.semantic[anchor].items() if k[0] == 'service'}
        direct = {n: e for n, e in graph.adj[anchor] if e.get('type') in {'nearby_estimate', 'adjacent_to'}}
        for target in sorted(graph.nodes):
            if target == anchor or target[0] not in {'poi', 'outlet', 'building'}:
                continue
            candidates = []
            for first, own_edge in services.items():
                for other, complement in graph.adj[first]:
                    target_edge = graph.semantic[target].get(other)
                    if complement.get('type') == 'service_complements' and target_edge:
                        candidates.append([(first, own_edge), (other, complement), (target, target_edge)])
            if not candidates:
                continue
            if target in direct:
                spatial = {'type': direct[target]['type'], 'path': graph.path(anchor, [(target, direct[target])]),
                           'limitations': _limits(direct[target].get('limitations', []))}
            else:
                spatial = graph.shared_space(anchor, target, building_only=True)
            if not spatial:
                semantic_without_space += 1
                continue
            found[target] = row(target, candidates[0], spatial_evidence=spatial)
        # An existing_shop projection may mirror its parent merchant. Only drop
        # that explicit same-name/branch-suffix duplicate, not confirmed windows.
        for target in list(found):
            node = graph.nodes[target]
            if target[0] != 'outlet' or node.get('identity_status') != 'existing_shop':
                continue
            parent = ('poi', str(node.get('poi_id', '')))
            if parent not in graph.nodes or parent not in found and parent != anchor:
                continue
            own_name = _merchant_basename(node.get('name'))
            parent_name = _merchant_basename(graph.nodes[parent].get('name'))
            if own_name and own_name == parent_name:
                del found[target]
        result['gaps'] = {'semantic_matches_without_spatial_evidence': semantic_without_space}
        result['limitations'].append('互补是功能组合推测；没有直接邻近或同楼依据的地点不列为候选。')
    else:
        # Generic service/category discovery has dedicated modes. Crossing these
        # hubs here would make a broad food class look like a specific relation.
        blocked_hubs = {'area', 'category', 'service'}
        spatial = {'adjacent_to', 'west_of', 'east_of', 'located_in_part', 'relative_to', 'next_in_roster'}

        def chain_edge_rank(edge):
            return (0 if edge.get('type') in PARENTS or edge.get('status') == 'confirmed'
                    and edge.get('type') in spatial else 1 if edge.get('type') in spatial | {'nearby_estimate'}
                    else 2 if edge.get('type') in SEMANTIC else 0)

        # At most six states per node (1..3 hops, with/without metric edge), not
        # enumeration of every possible path. Priority chooses structural proof
        # before an equally short semantic path; cycles cannot improve proof.
        queue, seen, scores, serial = [(0, 0, 0, anchor, [], False)], set(), {}, 0
        direct = {n for n, _ in graph.adj[anchor] if n[0] not in blocked_hubs}
        while queue:
            rank, hops, _, current, path, has_metric = heapq.heappop(queue)
            state = (current, hops, has_metric)
            if state in seen:
                continue
            seen.add(state)
            if hops >= 2 and current not in direct and current[0] not in CONCEPTS and current != anchor:
                score = (rank, hops)
                if current not in scores or score < scores[current]:
                    scores[current] = score
                    found[current] = row(current, path)
            if hops == 3 or current[0] in blocked_hubs:
                continue
            path_nodes = {anchor, *(n for n, _ in path)}
            for target, edge in graph.adj[current]:
                metric = edge.get('type') == 'nearby_estimate'
                if (target in path_nodes or target[0] in blocked_hubs
                        or edge.get('type') in {'member_of', 'ordered_along'} or metric and has_metric):
                    continue
                steps = path + [(target, edge)]
                serial += 1
                heapq.heappush(queue, (max(rank, chain_edge_rank(edge)), hops + 1, serial,
                                      target, steps, has_metric or metric))
        result['max_hops'] = 3
        result['limitations'].append('仅展示两至三跳有界解释；不穿越全校区域或泛类别/服务枢纽，不连续推导直线近邻；未返回不代表没有关系。')
        for target in list(found):
            node = graph.nodes[target]
            parent = ('poi', str(node.get('poi_id', '')))
            if (target[0] == 'outlet' and node.get('identity_status') == 'existing_shop'
                    and parent in found
                    and _merchant_basename(node.get('name'))
                    and _merchant_basename(node.get('name')) == _merchant_basename(graph.nodes[parent].get('name'))):
                del found[target]
    spatial_facts = {'adjacent_to', 'west_of', 'east_of', 'located_in_part', 'same_building_member'}

    def order(target):
        item = found[target]
        if mode == 'neighbors':
            def edge_rank(e):
                kind = e.get('type')
                priority = (0 if kind in spatial_facts and e.get('status') == 'confirmed' else
                            1 if kind in PARENTS else 2 if kind in SEMANTIC else
                            3 if kind == 'nearby_estimate' else 4)
                return priority, e.get('distance_m', float('inf'))
            rank = min(edge_rank(e) for e in item['edges'])
        elif mode == 'same_type':
            shared = Counter(n['ref']['kind'] for n in item['shared_concepts'])
            space = (item.get('spatial_evidence') or {}).get('type')
            scope = {'campus': 0, 'nearby': 1}.get(graph.nodes[target].get('scope_status'), 2)
            rank = (not shared['brand'], scope, not shared['trait'], -(shared['service'] + shared['category']),
                    0 if space == 'same_floor' else 1 if space == 'same_building' else 2)
        elif mode == 'complementary':
            space = item['spatial_evidence']
            distances = [e['distance_m'] for e in space['path']['edges'] if 'distance_m' in e]
            rank = (0 if space['type'] == 'adjacent_to' else 1 if distances else 2,
                    min(distances, default=float('inf')))
        else:
            rank = (scores[target][0], 0 if target[0] in {'building', 'outlet', 'poi'} else
                    1 if target[0] == 'floor' else 3 if target[0] == 'item' else 2,
                    item['path']['hop_count'])
        return (*rank, item['name'], target)

    items = [found[k] for k in sorted(found, key=order)]
    result.update(items=items[:limit], total=len(items), loaded_count=min(limit, len(items)),
                  truncated=len(items) > limit, related_entity_count=len(items),
                  related_entity_kinds=dict(Counter(k[0] for k in found)))
    if mode == 'same_type':
        result['ordering'] = 'same_brand_then_campus_scope_then_semantics_and_shared_space'
        result['limitations'].append('同品牌比较优先校内，再附近与范围未知；这是范围偏好，不是距离排序。')
    return result
