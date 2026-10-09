"""Graph checks use fabricated points in the declared local metre frame."""
import copy
import unittest

from backend.poi_network import build_poi_network, load_policy, validate_network


def ref(kind, ident):
    return dict(kind=kind, id=ident)


def fixture():
    pois = [dict(id='p' + str(i), name=name, category=category, status='active', source='field_observation',
                 zone='campus', location=dict(x=x, y=y, crs='local EPSG:32650'))
            for i, (name, category, x, y) in enumerate((('餐厅甲', 'restaurant', 0, 0),
                                                       ('咖啡乙', 'coffee', 30, 40),
                                                       ('打印复印', 'service', 100, 0),
                                                       ('远处餐厅', 'restaurant', 900, 900)))]
    entities = [dict(ref=ref('poi', p['id']), name=p['name'], data_mode='real', browseable=True,
                     map_target=dict(kind='recorded_point'), category=p['category']) for p in pois]
    return dict(entities=entities, relations=[]), dict(pois=pois, shops=[], items=[], walking_times=[])


class PoiNetworkTests(unittest.TestCase):
    def test_pure_deterministic_typed_graph_with_no_routes(self):
        snapshot, catalog = fixture()
        before = copy.deepcopy((snapshot, catalog))
        graph = build_poi_network(snapshot, catalog)
        self.assertEqual((snapshot, catalog), before)
        self.assertEqual(graph, build_poi_network(snapshot, catalog))
        self.assertTrue(validate_network(graph))
        self.assertEqual(graph['contract_version'], 'poi-network.v1')
        self.assertFalse(any(e['type'] in {'walkable_to', 'route_to', 'open_now'} for e in graph['edges']))
        self.assertIn('WALKING_TIMES_EMPTY', graph['summary']['issue_codes'])
        self.assertTrue(all(e['limitations'] is not None and e['evidence_refs'] for e in graph['edges']))

    def test_distance_and_direction_are_estimates_not_routes(self):
        snapshot, catalog = fixture(); graph = build_poi_network(snapshot, catalog)
        edge = next(e for e in graph['edges'] if e['type'] == 'nearby_estimate' and e['subject']['id'] == 'p0' and e['object']['id'] == 'p1')
        self.assertEqual(edge['distance_m'], 50)
        self.assertEqual(edge['direction'], 'northeast')
        self.assertEqual(edge['status'], 'computed')
        self.assertTrue(edge['symmetric'])
        self.assertTrue(any('步行' in s for s in edge['limitations']))
        self.assertFalse(any(e['type'] == 'nearby_estimate' and 'p3' in [e['subject']['id'], e['object']['id']] for e in graph['edges']))

    def test_coincident_or_close_points_do_not_invent_direction_or_identity(self):
        snapshot, catalog = fixture(); catalog['pois'][1]['location'].update(x=0, y=0)
        graph = build_poi_network(snapshot, catalog)
        edge = next(e for e in graph['edges'] if e['type'] == 'nearby_estimate' and e['object']['id'] == 'p1')
        self.assertEqual(edge['distance_m'], 0)
        self.assertIsNone(edge['bearing_degrees'])
        self.assertFalse(any(e['type'] == 'same_as' for e in graph['edges']))

    def test_ineligible_coordinates_and_anchor_never_metric_points(self):
        cases = [dict(location=dict(x=116.3, y=39.9, crs='BD-09')),
                 dict(map_point=dict(x=0, y=0, crs='local EPSG:32650', precision='building', building_id='b')),
                 dict(map_point=dict(x=0, y=0, crs='local EPSG:32650', source='model_centroid_approximate')),
                 dict(location=dict(x=445333, y=4423619, crs='local EPSG:32650')),
                 dict(location=dict(x=True, y=2, crs='local EPSG:32650')),
                 dict(location=dict(x=float('nan'), y=2, crs='local EPSG:32650')),
                 dict(location_source='model_centroid_approximate'),
                 dict(location_review_status='conflicting_source_points'),
                 dict(origin_utm=[1, 2])]
        for updates in cases:
            with self.subTest(updates=updates):
                snapshot, catalog = fixture(); catalog['pois'][0].update(updates)
                graph = build_poi_network(snapshot, catalog)
                self.assertFalse(any(e['type'] == 'nearby_estimate' and e['subject']['id'] == 'p0' for e in graph['edges']))
        for kind in ('building_anchor', 'reference_area', 'area_list', 'unknown'):
            snapshot, catalog = fixture(); snapshot['entities'][0]['map_target']['kind'] = kind
            graph = build_poi_network(snapshot, catalog)
            self.assertEqual(graph['summary']['metric_point_count'], 3)

    def test_inactive_simulation_outside_and_alias_excluded_from_spatial_derivation(self):
        for field, value in [('browseable', False), ('data_mode', 'simulated'),
                             ('data_mode', 'inferred'), ('canonical_poi_id', 'p1')]:
            snapshot, catalog = fixture(); snapshot['entities'][0][field] = value
            self.assertEqual(build_poi_network(snapshot, catalog)['summary']['metric_point_count'], 3)
        snapshot, catalog = fixture(); catalog['pois'][0]['zone'] = 'outside'
        self.assertEqual(build_poi_network(snapshot, catalog)['summary']['visible_poi_count'], 3)
        for poi in catalog['pois']: poi['zone'] = 'outside'
        graph = build_poi_network(snapshot, catalog)
        self.assertFalse(any(n.get('concept') for n in graph['nodes']))
        self.assertFalse(graph['summary']['visible_edge_types'])

    def test_qualitative_relations_survive_missing_coordinates(self):
        snapshot, catalog = fixture()
        snapshot['entities'][0]['map_target'] = dict(kind='unknown')
        snapshot['entities'][1]['map_target'] = dict(kind='unknown')
        snapshot['relations'] = [dict(type='adjacent_to', subject=ref('poi', 'p0'), object=ref('poi', 'p1'), basis='user_confirmation')]
        graph = build_poi_network(snapshot, catalog)
        edge = next(e for e in graph['edges'] if e['type'] == 'adjacent_to')
        self.assertEqual(edge['status'], 'confirmed')
        self.assertNotIn('distance_m', edge)

    def test_building_and_floor_membership_are_path_backed(self):
        snapshot, catalog = fixture()
        snapshot['entities'] += [dict(ref=ref('building', 'b'), name='楼甲', data_mode='real', browseable=True),
                                 dict(ref=ref('floor', 'b:floor:2'), name='二层', data_mode='real', browseable=True)]
        snapshot['relations'] = [dict(type='contained_in', subject=ref('poi', 'p0'), object=ref('floor', 'b:floor:2')),
                                 dict(type='contained_in', subject=ref('floor', 'b:floor:2'), object=ref('building', 'b'))]
        graph = build_poi_network(snapshot, catalog)
        edge = next(e for e in graph['edges'] if e['type'] == 'in_building')
        self.assertEqual(len(edge['supporting_edge_ids']), 2)
        self.assertEqual(edge['status'], 'computed')
        snapshot['entities'][-1]['data_mode'] = 'simulated'
        graph = build_poi_network(snapshot, catalog)
        self.assertNotIn('in_building', graph['summary']['edge_types'])
        self.assertNotIn('on_floor', graph['summary']['edge_types'])

    def test_roster_order_is_not_adjacency_and_duplicate_ranks_are_flagged(self):
        snapshot, catalog = fixture()
        snapshot['entities'].append(dict(ref=ref('area', 'lane'), name='巷子', browseable=True, data_mode='real'))
        snapshot['relations'] = [dict(type='ordered_along', subject=ref('poi', 'p' + str(i)), object=ref('area', 'lane'), order=i + 1, direction='north_to_south') for i in range(3)]
        graph = build_poi_network(snapshot, catalog)
        self.assertEqual(graph['summary']['edge_types']['next_in_roster'], 2)
        self.assertNotIn('adjacent_to', graph['summary']['edge_types'])
        snapshot['entities'][-1]['data_mode'] = 'simulated'
        self.assertNotIn('next_in_roster', build_poi_network(snapshot, catalog)['summary']['edge_types'])
        snapshot['entities'][-1]['data_mode'] = 'real'
        snapshot['relations'][1]['order'] = 1
        graph = build_poi_network(snapshot, catalog)
        self.assertIn('AMBIGUOUS_SEQUENCE_RANK', graph['summary']['issue_codes'])
        self.assertNotIn('next_in_roster', graph['summary']['edge_types'])

    def test_nearest_neighbor_cap_is_explicit(self):
        snapshot, catalog = fixture(); policy = load_policy(); policy['nearest_neighbors_per_poi'] = 1
        graph = build_poi_network(snapshot, catalog, policy)
        self.assertEqual(graph['summary']['within_radius_pair_count'], 3)
        self.assertEqual(graph['summary']['nearby_pair_count'], 2)
        self.assertIn('NEARBY_GRAPH_CAPPED', graph['summary']['issue_codes'])

    def test_outlet_traits_require_real_item_paths_and_do_not_mean_all_dishes(self):
        snapshot, catalog = fixture()
        snapshot['entities'] += [dict(ref=ref('outlet', 's'), name='餐厅甲', poi_id='p0', browseable=True, data_mode='real'),
                                 dict(ref=ref('item', 'i'), name='米饭', browseable=True, data_mode='real'),
                                 dict(ref=ref('item', 'demo'), name='模拟面食', browseable=True, data_mode='simulated')]
        catalog['shops'] = [dict(id='s', name='餐厅甲', poi_id='p0', source='field_observation')]
        catalog['items'] = [dict(id='i', name='米饭', shop_id='s', tags=['米饭'], source='menu_photo'),
                            dict(id='demo', name='模拟面食', shop_id='s', tags=['面食'], source='simulated')]
        snapshot['relations'] = [dict(type='offered_by', subject=ref('item', ident), object=ref('outlet', 's')) for ident in ('i', 'demo')]
        graph = build_poi_network(snapshot, catalog)
        traits = [e for e in graph['edges'] if e['type'] == 'offers_trait']
        self.assertEqual(len(traits), 1)
        self.assertEqual(traits[0]['recorded_item_count'], 1)
        self.assertEqual(len(traits[0]['supporting_edge_ids']), 2)
        self.assertTrue(any('不表示全部菜单' in s for s in traits[0]['limitations']))

    def test_policy_and_integrity_reject_invalid_inputs(self):
        snapshot, catalog = fixture()
        for value in (True, 0, -1, float('inf'), 3000):
            policy = load_policy(); policy['nearby_radius_m'] = value
            with self.assertRaises(ValueError): build_poi_network(snapshot, catalog, policy)
        snapshot['relations'] = [dict(type='contained_in', subject=ref('poi', 'p0'), object=ref('poi', 'missing'))]
        with self.assertRaisesRegex(ValueError, 'Dangling'): build_poi_network(snapshot, catalog)


if __name__ == '__main__':
    unittest.main()
