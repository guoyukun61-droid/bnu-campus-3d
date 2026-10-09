"""In-memory graph and isolated HTTP regressions; no model, source or account IO."""
import copy
import http.client
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import quote, urlencode

from app_server import PreviewModel, make_app_server
from backend.accounts import AccountStore
from backend.life_relations import RelationRepository
from backend.poi_network_query import network_summary, query_network


def ref(kind, ident):
    return dict(kind=kind, id=ident)


def fixture():
    nodes, edges = [], []

    def node(kind, ident, **extra):
        nodes.append(dict(ref=ref(kind, ident), name='测试-' + ident, data_mode='real',
                          browseable=True, **extra))

    def edge(kind, a, b, **extra):
        edges.append(dict(id='e' + str(len(edges)), type=kind, subject=ref(*a), object=ref(*b),
                          status='recorded', basis='fixture', rule_version='1.20.0-data.3',
                          limitations=['测试关系，不保证通行。'], **extra))

    for ident in ('meal-a', 'meal-b', 'coffee-near', 'coffee-far', 'coffee-floor', 'print-near', 'unrelated'):
        node('poi', ident)
    node('poi', 'hidden', graph_visible=False)
    node('poi', 'simulated', is_simulated=True)
    node('poi', 'alias', canonical_poi_id='meal-a')
    node('poi', 'outside', scope_status='outside')
    node('building', 'library')
    node('building', 'food-building')
    node('floor', 'food-building/3')
    node('area', 'campus')
    node('outlet', 'meal-window')
    for ident in ('dining', 'beverages', 'study', 'printing'):
        node('service', ident, concept=True)
    node('category', 'restaurant', concept=True)
    node('brand', 'fixture-brand', concept=True)
    node('trait', 'spicy', concept=True)
    for ident in ('meal-a', 'meal-b', 'hidden', 'simulated', 'alias', 'outside'):
        edge('provides_service', ('poi', ident), ('service', 'dining'))
        edge('has_category', ('poi', ident), ('category', 'restaurant'))
    edge('provides_service', ('outlet', 'meal-window'), ('service', 'dining'))
    edge('of_brand', ('poi', 'meal-a'), ('brand', 'fixture-brand'))
    edge('of_brand', ('poi', 'meal-b'), ('brand', 'fixture-brand'))
    edge('has_trait', ('poi', 'meal-a'), ('trait', 'spicy'))
    edge('has_trait', ('poi', 'meal-b'), ('trait', 'spicy'))
    for ident in ('coffee-near', 'coffee-far', 'coffee-floor'):
        edge('provides_service', ('poi', ident), ('service', 'beverages'))
    edge('provides_service', ('building', 'library'), ('service', 'study'))
    edge('provides_service', ('poi', 'print-near'), ('service', 'printing'))
    edge('service_complements', ('service', 'dining'), ('service', 'beverages'), symmetric=True)
    edge('service_complements', ('service', 'study'), ('service', 'beverages'), symmetric=True)
    edge('nearby_estimate', ('poi', 'coffee-near'), ('poi', 'meal-a'), distance_m=31.5,
         bearing_degrees=90, symmetric=True)
    edge('adjacent_to', ('poi', 'meal-a'), ('poi', 'print-near'))
    edge('contained_in', ('poi', 'meal-a'), ('floor', 'food-building/3'))
    edge('contained_in', ('poi', 'coffee-floor'), ('floor', 'food-building/3'))
    edge('contained_in', ('floor', 'food-building/3'), ('building', 'food-building'))
    edge('contained_in', ('outlet', 'meal-window'), ('poi', 'meal-a'))
    for ident in ('meal-a', 'coffee-far', 'unrelated'):
        edge('member_of', ('poi', ident), ('area', 'campus'))
    edge('same_as', ('poi', 'alias'), ('poi', 'meal-a'))
    network = dict(contract_version='poi-network.v1', rule_version='1.20.0-data.3',
                   nodes=nodes, edges=edges, issues=[dict(code='NO_VERIFIED_ROUTE_NETWORK')],
                   summary=dict(metric_point_count=2), limitations=[])
    return dict(snapshot_id='sha256:fixture-1', contract_version='life-map.v2',
                projection_version='1.20.0-data.3', entities=copy.deepcopy(nodes),
                relations=[], menu_groups=[], item_membership={}, issues=[], summary={'source_counts': {}},
                network=network)


def ids(result):
    return {item['ref']['id'] for item in result['items']}


class NetworkQueryTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = fixture()

    def query(self, ident='meal-a', **options):
        return query_network(self.snapshot, kind='poi', ident=ident, **options)

    def test_summary_and_old_snapshot_without_network(self):
        result = network_summary(self.snapshot)
        self.assertTrue(result['configured'])
        self.assertEqual(result['summary']['metric_point_count'], 2)
        self.assertEqual(result['summary']['issue_codes'], {'NO_VERIFIED_ROUTE_NETWORK': 1})
        self.assertEqual(result['snapshot_id'], 'sha256:fixture-1')
        self.assertEqual(result['rule_version'], '1.20.0-data.3')
        old = network_summary({'snapshot_id': 'old'})
        self.assertFalse(old['configured'])
        self.assertEqual(old['items'], [])
        self.assertIn('未配置', old['limitations'][-1])

    def test_neighbors_direct_incoming_edges_and_distance_orientation(self):
        result = self.query(limit=30)
        self.assertIn('coffee-near', ids(result))
        self.assertNotIn('meal-b', ids(result))
        coffee = next(i for i in result['items'] if i['ref']['id'] == 'coffee-near')
        edge = coffee['edges'][0]
        self.assertEqual(edge['subject'], ref('poi', 'coffee-near'))
        self.assertEqual(edge['bearing_degrees'], 90)  # preserve documented original direction
        self.assertFalse(coffee['path']['is_route'])

    def test_same_type_uses_shared_concepts_without_duplicate_outlets(self):
        result = self.query(mode='same_type', limit=30)
        self.assertIn('meal-b', ids(result))
        self.assertNotIn('meal-window', ids(result))
        other = next(i for i in result['items'] if i['ref']['id'] == 'meal-b')
        self.assertEqual({c['ref']['kind'] for c in other['shared_concepts']}, {'category', 'service', 'brand', 'trait'})
        self.assertEqual(other['path']['hop_count'], 2)

    def test_same_floor_alone_does_not_establish_same_type(self):
        self.assertNotIn('coffee-floor', ids(self.query(mode='same_type')))
        self.snapshot['network']['edges'].append(dict(id='shared-trait', type='has_trait',
            subject=ref('poi', 'coffee-floor'), object=ref('trait', 'spicy')))
        coffee = next(i for i in self.query(mode='same_type')['items'] if i['ref']['id'] == 'coffee-floor')
        self.assertEqual(coffee['shared_concepts'][0]['ref'], ref('trait', 'spicy'))
        self.assertEqual(coffee['spatial_evidence']['type'], 'same_floor')
        self.assertEqual([n['ref']['id'] for n in coffee['spatial_evidence']['path']['nodes']],
                         ['meal-a', 'food-building/3', 'coffee-floor'])

    def test_evidence_ranking_and_same_brand_priority(self):
        self.snapshot['network']['edges'].append(dict(id='confirmed-neighbor', type='adjacent_to',
            subject=ref('poi', 'meal-a'), object=ref('poi', 'unrelated'), status='confirmed'))
        self.assertEqual(self.query(limit=1)['items'][0]['ref']['id'], 'unrelated')
        self.snapshot['network']['nodes'].append(dict(ref=ref('poi', 'aaa-plain'), name='排在前面的无品牌餐饮',
            data_mode='real', browseable=True))
        self.snapshot['network']['edges'].append(dict(id='plain-dining', type='provides_service',
            subject=ref('poi', 'aaa-plain'), object=ref('service', 'dining')))
        self.assertEqual(self.query(mode='same_type', limit=1)['items'][0]['ref']['id'], 'meal-b')

    def test_closed_node_and_shortcut_through_hidden_parent_are_excluded(self):
        meal_b = next(n for n in self.snapshot['network']['nodes'] if n['ref'] == ref('poi', 'meal-b'))
        meal_b.update(graph_visible=True, operational_status='closed')
        self.assertNotIn('meal-b', ids(self.query(mode='same_type')))
        self.snapshot['network']['edges'].extend([
            dict(id='hidden-parent', type='contained_in', subject=ref('poi', 'meal-a'), object=ref('poi', 'hidden')),
            dict(id='hidden-building', type='contained_in', subject=ref('poi', 'hidden'), object=ref('building', 'library')),
            dict(id='hidden-shortcut', type='in_building', subject=ref('poi', 'meal-a'), object=ref('building', 'library'),
                 supporting_edge_ids=['hidden-parent', 'hidden-building'])])
        self.assertNotIn('library', ids(self.query(limit=30)))

    def test_complementary_deduplicates_only_same_name_existing_shop(self):
        for ident, identity in [('coffee-mirror', 'existing_shop'), ('coffee-window', 'confirmed')]:
            self.snapshot['network']['nodes'].append(dict(ref=ref('outlet', ident), name='测试-coffee-floor',
                data_mode='real', browseable=True, poi_id='coffee-floor', identity_status=identity))
            self.snapshot['network']['edges'].extend([
                dict(id=ident+'-parent', type='contained_in', subject=ref('outlet', ident), object=ref('poi', 'coffee-floor')),
                dict(id=ident+'-service', type='provides_service', subject=ref('outlet', ident), object=ref('service', 'beverages'))])
        result = self.query(mode='complementary')
        self.assertNotIn('coffee-mirror', ids(result))
        self.assertIn('coffee-window', ids(result))
        self.assertEqual(result['items'][0]['ref']['id'], 'coffee-near')

    def test_existing_shop_short_name_and_parent_branch_suffix_deduplicate(self):
        parent = next(n for n in self.snapshot['network']['nodes'] if n['ref'] == ref('poi', 'coffee-floor'))
        parent['name'] = '校园咖啡（北京师范大学店）'
        for ident, identity, name in [('short-name', 'existing_shop', '校园咖啡'),
                                      ('independent', 'confirmed', '校园咖啡'),
                                      ('dietary-note', 'existing_shop', '校园咖啡（清真）')]:
            self.snapshot['network']['nodes'].append(dict(ref=ref('outlet', ident), name=name,
                data_mode='real', browseable=True, poi_id='coffee-floor', identity_status=identity))
            self.snapshot['network']['edges'].extend([
                dict(id=ident+'-parent', type='contained_in', subject=ref('outlet', ident), object=ref('poi', 'coffee-floor')),
                dict(id=ident+'-service', type='provides_service', subject=ref('outlet', ident), object=ref('service', 'beverages'))])
        for mode in ('complementary', 'chain'):
            with self.subTest(mode=mode):
                result = self.query(mode=mode, limit=30)
                self.assertIn('coffee-floor', ids(result))
                self.assertNotIn('short-name', ids(result))
                self.assertIn('independent', ids(result))
                self.assertIn('dietary-note', ids(result))
        parent['name'] = '校园咖啡(北京师范大学店)'
        self.assertNotIn('short-name', ids(self.query(mode='complementary')))

    def test_equal_basename_at_different_parent_pois_is_not_merged(self):
        names = {'coffee-floor': '校园咖啡（北门店）', 'coffee-near': '校园咖啡（南门店）'}
        for node in self.snapshot['network']['nodes']:
            if node['ref']['kind'] == 'poi' and node['ref']['id'] in names:
                node['name'] = names[node['ref']['id']]
        result = self.query(mode='complementary')
        self.assertEqual(ids(result), {'coffee-floor', 'coffee-near'})
        # A window matching another POI is not its alias: compare only its parent.
        self.snapshot['network']['nodes'].append(dict(ref=ref('outlet', 'different-parent-window'),
            name='另一饮品', data_mode='real', browseable=True, poi_id='coffee-floor', identity_status='existing_shop'))
        next(n for n in self.snapshot['network']['nodes'] if n['ref'] == ref('poi', 'coffee-near'))['name'] = '另一饮品(南门店)'
        self.snapshot['network']['edges'].extend([
            dict(id='different-parent', type='contained_in', subject=ref('outlet', 'different-parent-window'), object=ref('poi', 'coffee-floor')),
            dict(id='different-service', type='provides_service', subject=ref('outlet', 'different-parent-window'), object=ref('service', 'beverages'))])
        self.assertEqual(ids(self.query(mode='complementary')),
                         {'coffee-floor', 'coffee-near', 'different-parent-window'})

    def test_same_brand_then_campus_scope_is_not_distance_order(self):
        next(n for n in self.snapshot['network']['nodes'] if n['ref'] == ref('poi', 'meal-b'))['scope_status'] = 'nearby'
        for ident, scope, brand in [('zzz-campus-brand', 'campus', True),
                                    ('aaa-unknown-brand', 'unknown', True), ('campus-no-brand', 'campus', False)]:
            self.snapshot['network']['nodes'].append(dict(ref=ref('poi', ident), name=ident,
                data_mode='real', browseable=True, scope_status=scope))
            self.snapshot['network']['edges'].append(dict(id=ident+'-service', type='provides_service',
                subject=ref('poi', ident), object=ref('service', 'dining')))
            if brand:
                self.snapshot['network']['edges'].append(dict(id=ident+'-brand', type='of_brand',
                    subject=ref('poi', ident), object=ref('brand', 'fixture-brand')))
        result = self.query(mode='same_type', limit=30)
        self.assertEqual([i['ref']['id'] for i in result['items']],
                         ['zzz-campus-brand', 'meal-b', 'aaa-unknown-brand', 'campus-no-brand'])
        self.assertIn('不是距离排序', result['limitations'][-1])

    def test_original_classification_and_rule_origin_are_public(self):
        self.snapshot['network']['edges'][0].update(original_category='service', rule_origin='reviewed_category_override')
        service = next(i for i in self.query(limit=30)['items'] if i['ref'] == ref('service', 'dining'))
        self.assertEqual(service['edges'][0]['original_category'], 'service')
        self.assertEqual(service['edges'][0]['rule_origin'], 'reviewed_category_override')

    def test_offers_trait_supports_outlet_comparison_with_recorded_item_limits(self):
        self.snapshot['network']['nodes'].append(dict(ref=ref('outlet', 'other-window'), name='另一窗口',
            data_mode='real', browseable=True))
        for ident in ('meal-window', 'other-window'):
            self.snapshot['network']['edges'].append(dict(id=ident+'-trait', type='offers_trait',
                subject=ref('outlet', ident), object=ref('trait', 'spicy'), status='computed',
                recorded_item_count=1, limitations=['仅曾记录该标签菜品，不代表所有菜品或当前在售。']))
        result = query_network(self.snapshot, kind='outlet', ident='meal-window', mode='same_type')
        self.assertEqual(ids(result), {'other-window'})
        self.assertEqual(result['items'][0]['path']['edges'][0]['recorded_item_count'], 1)
        self.assertIn('不代表所有菜品', result['items'][0]['limitations'][0])

    def test_evidence_reference_payload_is_bounded_with_honest_totals(self):
        edge = self.snapshot['network']['edges'][0]
        edge['evidence_refs'] = [n['ref'] for n in self.snapshot['network']['nodes']]
        edge['supporting_edge_ids'] = [e['id'] for e in self.snapshot['network']['edges'][1:]]
        # Some referenced alias/hidden edges are intentionally unavailable. Use a
        # different edge whose source proof consists only of visible references.
        edge['supporting_edge_ids'] = []
        for number in range(25):
            ident = 'bounded-proof-' + str(number)
            self.snapshot['network']['edges'].append(dict(id=ident, type='has_trait',
                subject=ref('poi', 'meal-a'), object=ref('trait', 'spicy')))
            edge['supporting_edge_ids'].append(ident)
        row = next(i for i in self.query(limit=30)['items'] if i['ref'] == ref('service', 'dining'))
        public = row['edges'][0]
        self.assertEqual(len(public['evidence_refs']), 12)
        self.assertGreater(public['evidence_refs_total'], 12)
        self.assertTrue(public['evidence_refs_truncated'])
        self.assertEqual(len(public['supporting_edge_ids']), 24)
        self.assertEqual(public['supporting_edge_ids_total'], 25)
        self.assertTrue(public['supporting_edge_ids_truncated'])

    def test_complementary_requires_both_service_rule_and_spatial_evidence(self):
        result = self.query(mode='complementary')
        self.assertEqual(ids(result), {'coffee-near', 'coffee-floor'})
        self.assertEqual(result['gaps']['semantic_matches_without_spatial_evidence'], 1)
        self.assertNotIn('print-near', ids(result))  # spatial adjacency alone is not a task rule
        for row in result['items']:
            self.assertEqual(row['path']['hop_count'], 3)
            self.assertIn('service_complements', [e['type'] for e in row['path']['edges']])
            self.assertIsNotNone(row['spatial_evidence'])
        floor = next(i for i in result['items'] if i['ref']['id'] == 'coffee-floor')
        self.assertEqual(floor['spatial_evidence']['type'], 'same_building')

    def test_building_service_without_spatial_proof_returns_gap_not_campus_shortcut(self):
        result = query_network(self.snapshot, kind='building', ident='library', mode='complementary')
        self.assertEqual(result['total'], 0)
        self.assertEqual(result['gaps']['semantic_matches_without_spatial_evidence'], 3)

    def test_chain_is_two_to_three_hops_and_never_uses_area_hub(self):
        result = self.query(mode='chain', limit=30)
        self.assertIn('meal-b', ids(result))
        self.assertNotIn('unrelated', ids(result))
        for row in result['items']:
            self.assertIn(row['path']['hop_count'], (2, 3))
            self.assertFalse(row['path']['is_route'])
            self.assertNotIn('area', [n['ref']['kind'] for n in row['path']['nodes']])

    def test_chain_does_not_expand_a_large_generic_food_hub(self):
        for number in range(250):
            ident = 'generic-food-' + str(number)
            self.snapshot['network']['nodes'].append(dict(ref=ref('poi', ident), name=ident,
                data_mode='real', browseable=True))
            self.snapshot['network']['edges'].extend([
                dict(id=ident+'-category', type='has_category', subject=ref('poi', ident), object=ref('category', 'restaurant')),
                dict(id=ident+'-service', type='provides_service', subject=ref('poi', ident), object=ref('service', 'dining'))])
        result = self.query(mode='chain', limit=30)
        self.assertLess(result['total'], 20)
        self.assertEqual(result['related_entity_count'], result['total'])
        self.assertFalse(any(ident.startswith('generic-food-') for ident in ids(result)))
        for item in result['items']:
            self.assertFalse({'category', 'service', 'area'} & {n['ref']['kind'] for n in item['path']['nodes']})

    def test_chain_nearby_is_not_transitive_and_structure_precedes_traits(self):
        self.snapshot['network']['edges'].append(dict(id='second-nearby', type='nearby_estimate',
            subject=ref('poi', 'coffee-near'), object=ref('poi', 'unrelated'), distance_m=10))
        result = self.query(mode='chain', limit=30)
        self.assertNotIn('unrelated', ids(result))
        ordered = [i['ref']['id'] for i in result['items']]
        self.assertLess(ordered.index('food-building'), ordered.index('meal-b'))
        self.assertLess(ordered.index('coffee-floor'), ordered.index('meal-b'))
        for item in result['items']:
            self.assertLessEqual(sum(e['type'] == 'nearby_estimate' for e in item['path']['edges']), 1)

    def test_hidden_simulated_alias_outside_never_anchor_or_bridge(self):
        for unavailable in ('hidden', 'simulated', 'alias', 'outside'):
            with self.subTest(unavailable=unavailable):
                with self.assertRaises(KeyError):
                    self.query(unavailable)
        for mode in ('neighbors', 'same_type', 'complementary', 'chain'):
            payload = json.dumps(self.query(mode=mode, limit=30), ensure_ascii=False)
            for unavailable in ('hidden', 'simulated', 'alias', 'outside'):
                self.assertNotIn('测试-' + unavailable, payload)

    def test_real_data_mode_and_browseable_fallback(self):
        node = next(n for n in self.snapshot['network']['nodes'] if n['ref'] == ref('poi', 'meal-b'))
        node['data_mode'] = 'simulated'
        self.assertNotIn('meal-b', ids(self.query(mode='same_type')))
        node['data_mode'] = 'real'; node['browseable'] = False
        self.assertNotIn('meal-b', ids(self.query(mode='same_type')))
        node['graph_visible'] = True
        self.assertNotIn('meal-b', ids(self.query(mode='same_type')))
        node['browseable'] = True
        self.assertIn('meal-b', ids(self.query(mode='same_type')))

    def test_alias_relation_never_creates_direct_neighbor(self):
        self.snapshot['network']['edges'].append(dict(id='alias-visible', type='same_as',
            subject=ref('poi', 'meal-a'), object=ref('poi', 'unrelated')))
        self.assertNotIn('unrelated', ids(self.query()))

    def test_limit_metadata_and_stable_no_mutation(self):
        original = copy.deepcopy(self.snapshot)
        first = self.query(limit=1)
        self.assertTrue(first['truncated'])
        self.assertEqual(first['loaded_count'], 1)
        self.assertGreater(first['total'], 1)
        self.assertEqual(first, self.query(limit=1))
        self.assertEqual(self.snapshot, original)

    def test_bad_parameters_and_missing_entity(self):
        for invalid in (True, 0, 31, 1.5, '3'):
            with self.assertRaises(ValueError):
                self.query(limit=invalid)
        for options in ({'mode': 'route'}, {'kind': '../poi'}, {'ident': ''}, {'ident': 'x' * 301}):
            with self.assertRaises(ValueError):
                query_network(self.snapshot, **({'kind': 'poi', 'ident': 'meal-a'} | options))
        with self.assertRaises(KeyError):
            self.query('not-present')

    def test_public_evidence_whitelist_removes_private_fields_and_paths(self):
        n = self.snapshot['network']['nodes'][0]
        n.update(source_file='PRIVATE-FILE', field_evidence={'actor': 'PRIVATE-ACTOR'},
                 password='PRIVATE-PASSWORD', location={'private': 'PRIVATE-LOCATION'})
        e = self.snapshot['network']['edges'][0]
        e.update(evidence={'source': 'user_confirmation', 'actor': 'PRIVATE-ACTOR',
                           'source_file': 'PRIVATE-FILE', 'description': r'C:\Users\private\picture.jpg',
                           'url': 'https://www.bnu.edu.cn/'},
                 limitations=[r'C:\Users\private\picture.jpg', '真实限制'],
                 evidence_refs=[ref('poi', 'hidden'), ref('poi', 'meal-a')])
        payload = json.dumps(self.query(limit=30), ensure_ascii=False)
        for secret in ('PRIVATE-', 'C:\\', 'picture.jpg', 'actor', 'password', 'source_file', 'field_evidence'):
            self.assertNotIn(secret, payload)
        self.assertIn('https://www.bnu.edu.cn/', payload)
        self.assertIn('真实限制', payload)


class NetworkHTTPTests(unittest.TestCase):
    def setUp(self):
        self.current = fixture()
        self.repository = RelationRepository(loader=lambda: copy.deepcopy(self.current), retain=2)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patches = [patch('app_server.ROOT', self.root),
                        patch('backend.life_relations.RelationRepository.load', side_effect=AssertionError('Private IO forbidden')),
                        patch('backend.adapters.CatalogAdapter.snapshot', side_effect=AssertionError('Private IO forbidden'))]
        for p in self.patches:
            p.start()
        # Empty isolated account store; the HTTP tests also prove that public
        # graph reads neither authenticate users nor reveal their private chats.
        self.accounts = AccountStore(self.root / 'accounts')
        self.controller = SimpleNamespace(model=PreviewModel(), tools=SimpleNamespace(directory=lambda: {'pois': []}))
        self.server = make_app_server(0, controller=self.controller,
            preview_origin='https://network-test.trycloudflare.com', accounts=self.accounts, relations=self.repository)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=5)
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def request(self, path, params=None, host=None, body=None):
        if params:
            path += '?' + urlencode(params)
        headers = {'Host': host or self.server.allowed_host, 'Origin': self.server.origin,
                   'X-BNU-Client': '1', 'Content-Type': 'application/json'}
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            conn.request('GET' if body is None else 'POST', path,
                         json.dumps(body) if body is not None else None, headers)
            response = conn.getresponse()
            return response.status, json.loads(response.read()), dict(response.getheaders())
        finally:
            conn.close()

    def test_summary_entity_encoded_id_and_no_store(self):
        status, result, headers = self.request('/api/app/v2/network/summary')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(result['contract_version'], 'poi-network.v1')
        status, body, _ = self.request('/api/app/v2/network/entities/floor/' + quote('food-building/3', safe=''))
        self.assertEqual(status, 200)
        self.assertEqual(body['anchor']['ref'], ref('floor', 'food-building/3'))

    def test_all_modes_and_separate_parameter_validation(self):
        endpoint = '/api/app/v2/network/entities/poi/meal-a'
        for mode in ('neighbors', 'same_type', 'complementary', 'chain'):
            self.assertEqual(self.request(endpoint, {'mode': mode, 'limit': 2})[0], 200)
        for query in ('limit=0', 'limit=31', 'limit=-1', 'limit=1.2', 'limit=true', 'limit=',
                      'limit=2&limit=3', 'mode=route', 'mode=', 'mode=neighbors&mode=',
                      'include_simulated=true', 'cursor=anything', 'snapshot_id=', 'q=test'):
            with self.subTest(query=query):
                self.assertEqual(self.request(endpoint + '?' + query)[0], 400)
        self.assertEqual(self.request('/api/app/v2/network/summary?limit=2')[0], 400)
        self.assertEqual(self.request('/api/app/v2/network/entities/poi/missing')[0], 404)
        self.assertEqual(self.request(endpoint + '/children')[0], 404)
        self.assertEqual(self.request(endpoint + '/')[0], 404)

    def test_retained_snapshot_and_expiration(self):
        old = self.request('/api/app/v2/network/summary')[1]['snapshot_id']
        self.current['snapshot_id'] = 'sha256:fixture-2'
        self.current['network']['nodes'][0]['name'] = '更新名称'
        self.request('/api/app/v2/network/summary')
        endpoint = '/api/app/v2/network/entities/poi/meal-a'
        status, body, _ = self.request(endpoint, {'snapshot_id': old})
        self.assertEqual(status, 200)
        self.assertEqual(body['anchor']['name'], '测试-meal-a')
        self.current['snapshot_id'] = 'sha256:fixture-3'
        self.request('/api/app/v2/network/summary')
        status, body, _ = self.request(endpoint, {'snapshot_id': old})
        self.assertEqual(status, 409)
        self.assertEqual(body['code'], 'SNAPSHOT_EXPIRED')

    def test_legacy_v2_and_missing_network_are_not_blocked(self):
        self.assertEqual(self.request('/api/app/v2/summary')[0], 200)
        self.assertEqual(self.request('/api/app/directory')[0], 200)
        self.assertEqual(self.request('/api/app/v2/summary?mode=neighbors')[0], 400)
        del self.current['network']
        status, body, _ = self.request('/api/app/v2/network/summary')
        self.assertEqual(status, 200)
        self.assertFalse(body['configured'])
        self.assertEqual(self.request('/api/app/v2/summary')[0], 200)

    def test_host_and_private_account_boundaries_unchanged(self):
        with patch.object(self.repository, 'snapshot', side_effect=AssertionError('Host must be checked first')):
            self.assertEqual(self.request('/api/app/v2/network/summary', host='evil.test')[0], 403)
        self.assertEqual(self.request('/api/account/conversations')[0], 401)
        self.assertEqual(self.request('/api/agent/chat', body={'message': 'test'})[0], 401)
        for path in ('/data/life/accounts/accounts.json', '/data/life/organized/run/network.json',
                     '/backend/poi_network_query.py'):
            self.assertEqual(self.request(path)[0], 404)
        self.assertEqual(self.request('/api/app/v2/network/summary', body={})[0], 403)


if __name__ == '__main__':
    unittest.main()
