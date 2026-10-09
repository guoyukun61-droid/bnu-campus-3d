"""HTTP contract checks with in-memory relations, no private store or model IO."""
import copy
import http.client
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlencode, quote

from app_server import PreviewModel, make_app_server
from backend.agent.tools import CampusTools
from backend.life_relations import RelationRepository, build_relation_snapshot
from backend.menu_relations import _PHOTO_HASHES


def fixture_catalog():
    return dict(
        pois=[dict(id='canteen-3', name='隔离测试三层食堂', category='canteen',
                   building_id=9001, floor='3', source='field_observation', status='active',
                   location=None, aliases=['隔离食堂'], address='测试楼三层',
                   source_file='PRIVATE-PHOTO-PATH', field_evidence={'actor': 'PRIVATE-ACTOR'}),
              dict(id='fixture-sports', name='隔离体育馆', category='sports',
                   source='field_observation', status='active', aliases=[])],
        shops=[dict(id='menu-collection-xinlequn-3', poi_id='canteen-3', name='测试菜单集合',
                    floor='3', source='menu_photo', entity_type='floor_menu_collection',
                    independent_merchant=False),
               dict(id='fixture-demo-shop', poi_id='canteen-3', name='模拟窗口', source='simulated')],
        items=[dict(id='fixture-item-'+str(i), shop_id='menu-collection-xinlequn-3',
                    name='隔离菜品'+str(i), price=10+i, specification='份', source='menu_photo',
                    source_photo_sha256=_PHOTO_HASHES['458' if i < 3 else '459'],
                    source_file='PRIVATE-PHOTO-PATH', field_evidence={'actor': 'PRIVATE-ACTOR'})
               for i in range(4)] + [
                   dict(id='fixture-demo-item', shop_id='fixture-demo-shop', name='模拟测试餐',
                        price=9, specification='份', source='simulated')],
        locations=[])


class LifeRelationsHTTPTests(unittest.TestCase):
    def setUp(self):
        self.catalog = fixture_catalog()
        self.buildings = [dict(id='9001', name='隔离测试楼', description='测试简介')]
        self.current = build_relation_snapshot(self.catalog, self.buildings)
        self.repository = RelationRepository(loader=lambda: copy.deepcopy(self.current), retain=2)
        self.private_temp = tempfile.TemporaryDirectory()
        self.private_root = Path(self.private_temp.name)
        target = self.private_root / 'data/life/organized/fixture/manifest.json'
        target.parent.mkdir(parents=True)
        target.write_text('{"secret":"PRIVATE-EXPORT-MARKER"}', encoding='utf-8')
        self.root_patch = patch('app_server.ROOT', self.private_root)
        self.root_patch.start()
        self.loader_patch = patch('backend.life_relations.RelationRepository.load',
                                  side_effect=AssertionError('No real source loading in HTTP tests'))
        self.loader_patch.start()
        self.catalog_patch = patch('backend.adapters.CatalogAdapter.snapshot',
                                   side_effect=AssertionError('No real catalog loading in HTTP tests'))
        self.catalog_patch.start()
        controller = SimpleNamespace(model=PreviewModel(), tools=CampusTools(self.catalog))
        self.server = make_app_server(0, controller=controller, relations=self.repository)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.catalog_patch.stop()
        self.loader_patch.stop()
        self.root_patch.stop()
        self.private_temp.cleanup()

    def get(self, path, params=None, headers=None):
        if params:
            path += '?' + urlencode(params)
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        request_headers = {'Host': self.server.allowed_host}
        request_headers.update(headers or {})
        try:
            conn.request('GET', path, headers=request_headers)
            response = conn.getresponse()
            raw = response.read()
            return response.status, json.loads(raw), dict(response.getheaders())
        finally:
            conn.close()

    def menu_group(self):
        return next(g for g in self.current['menu_groups']
                    if 'fixture-item-0' in g['item_ids'])['id']

    def update_snapshot(self, suffix):
        data = copy.deepcopy(self.catalog)
        data['pois'][0]['name'] += suffix
        self.current = build_relation_snapshot(data, self.buildings)
        return self.get('/api/app/v2/summary')[1]['snapshot_id']

    def test_summary_version_source_counts_and_no_store_headers(self):
        status, body, headers = self.get('/api/app/v2/summary')
        self.assertEqual(status, 200)
        self.assertEqual(body['contract_version'], 'life-map.v2')
        self.assertEqual(body['projection_version'], '1.20.0-data.3')
        self.assertEqual(body['summary']['source_counts'], dict(pois=2, shops=2, items=5))
        self.assertTrue(body['snapshot_id'].startswith('sha256:'))
        self.assertIsInstance(body['issues'], list)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')

    def test_search_alias_returns_typed_poi_and_ancestor_path(self):
        status, body, _ = self.get('/api/app/v2/entities/search', {'q': '新三', 'kind': 'poi'})
        self.assertEqual(status, 200)
        self.assertEqual(body['total'], 1)
        row = body['items'][0]
        self.assertEqual(row['ref'], dict(kind='poi', id='canteen-3'))
        self.assertEqual([p['ref']['kind'] for p in row['breadcrumbs']], ['building', 'floor'])
        self.assertEqual(row['map_target']['kind'], 'building_anchor')
        self.assertFalse(row['map_target']['can_measure_to_entrance'])

    def test_entity_children_and_percent_encoded_floor_id(self):
        status, entity, _ = self.get('/api/app/v2/entities/building/9001')
        self.assertEqual(status, 200)
        self.assertEqual(entity['entity']['name'], '隔离测试楼')
        sid = entity['snapshot_id']
        status, children, _ = self.get('/api/app/v2/entities/building/9001/children', {'snapshot_id': sid})
        self.assertEqual(status, 200)
        self.assertEqual(children['total'], 1)
        floor_id = children['items'][0]['ref']['id']
        status, floor, _ = self.get('/api/app/v2/entities/floor/'+quote(floor_id, safe=''), {'snapshot_id': sid})
        self.assertEqual(status, 200)
        self.assertEqual(floor['entity']['floor'], '3')
        status, pois, _ = self.get('/api/app/v2/entities/floor/'+quote(floor_id, safe='')+'/children', {'snapshot_id': sid})
        self.assertEqual(status, 200)
        self.assertEqual([p['ref']['id'] for p in pois['items']], ['canteen-3'])

    def test_menu_items_page_is_group_scoped_no_duplicates_or_other_groups(self):
        path = '/api/app/v2/menu-groups/'+self.menu_group()+'/items'
        status, first, _ = self.get(path, {'limit': 2})
        self.assertEqual(status, 200)
        self.assertEqual(first['total'], 3)
        self.assertEqual(first['loaded_count'], 2)
        self.assertTrue(first['next_cursor'])
        status, second, _ = self.get(path, {'limit': 2, 'cursor': first['next_cursor'], 'snapshot_id': first['snapshot_id']})
        self.assertEqual(status, 200)
        self.assertEqual(second['snapshot_id'], first['snapshot_id'])
        self.assertEqual(second['loaded_count'], 1)
        self.assertIsNone(second['next_cursor'])
        ids = [r['ref']['id'] for r in first['items'] + second['items']]
        self.assertEqual(ids, ['fixture-item-0', 'fixture-item-1', 'fixture-item-2'])

    def test_confirmed_window_has_its_own_menu_and_unknown_hours(self):
        path = '/api/app/v2/entities/outlet/outlet-xinlequn-3-001'
        status, body, _ = self.get(path)
        self.assertEqual(status, 200)
        window = body['entity']
        self.assertEqual(window['identity_status'], 'confirmed')
        self.assertIsNone(window['opening_hours'])
        self.assertEqual(window['hours_label'], '尚未录入')
        self.assertEqual(window['source_collection_id'], 'menu-collection-xinlequn-3')
        status, children, _ = self.get(path+'/children')
        self.assertEqual(status, 200)
        self.assertEqual([row['ref']['id'] for row in children['items']], [self.menu_group()])
        _, items, _ = self.get('/api/app/v2/menu-groups/'+self.menu_group()+'/items')
        self.assertTrue(all(row['outlet_id'] == window['ref']['id'] for row in items['items']))
        self.assertEqual([p['ref']['kind'] for p in items['items'][0]['breadcrumbs']],
                         ['building', 'floor', 'poi', 'outlet', 'menu_group'])

    def test_cursor_scope_mismatch_returns_400(self):
        path = '/api/app/v2/entities/search'
        status, first, _ = self.get(path, {'kind': 'item', 'limit': 1})
        self.assertEqual(status, 200)
        self.assertTrue(first['next_cursor'])
        for changed in ({'kind': 'poi'}, {'kind': 'item', 'q': '隔离菜品'},
                        {'kind': 'item', 'include_simulated': 'true'}):
            with self.subTest(changed=changed):
                status, body, _ = self.get(path, dict(changed, cursor=first['next_cursor']))
                self.assertEqual(status, 400)
                self.assertIn('error', body)
        status, _, _ = self.get('/api/app/v2/menu-groups/'+self.menu_group()+'/items', {'cursor': first['next_cursor']})
        self.assertEqual(status, 400)

    def test_explicit_wrong_snapshot_cursor_returns_400(self):
        path = '/api/app/v2/menu-groups/'+self.menu_group()+'/items'
        _, first, _ = self.get(path, {'limit': 1})
        status, _, _ = self.get(path, {'cursor': first['next_cursor'], 'snapshot_id': 'wrong'})
        self.assertEqual(status, 400)

    def test_expired_snapshot_and_cursor_return_409_not_empty_menu(self):
        path = '/api/app/v2/menu-groups/'+self.menu_group()+'/items'
        _, first, _ = self.get(path, {'limit': 1})
        self.update_snapshot('一')
        self.update_snapshot('二')
        for params in ({'snapshot_id': first['snapshot_id']}, {'cursor': first['next_cursor']}):
            status, body, _ = self.get(path, params)
            self.assertEqual(status, 409)
            self.assertEqual(body['code'], 'SNAPSHOT_EXPIRED')
            self.assertNotIn('items', body)

    def test_previous_snapshot_is_consistent_while_retained(self):
        _, old, _ = self.get('/api/app/v2/entities/poi/canteen-3')
        newer = self.update_snapshot('更新')
        self.assertNotEqual(newer, old['snapshot_id'])
        status, retained, _ = self.get('/api/app/v2/entities/poi/canteen-3', {'snapshot_id': old['snapshot_id']})
        self.assertEqual(status, 200)
        self.assertEqual(retained['entity']['name'], old['entity']['name'])

    def test_simulated_entities_are_opt_in(self):
        path = '/api/app/v2/entities/search'
        status, real, _ = self.get(path, {'kind': 'item'})
        self.assertEqual(status, 200)
        self.assertEqual(real['total'], 4)
        status, demo, _ = self.get(path, {'kind': 'item', 'include_simulated': 'true'})
        self.assertEqual(status, 200)
        self.assertEqual(demo['total'], 5)
        status, _, _ = self.get('/api/app/v2/entities/item/fixture-demo-item')
        self.assertEqual(status, 404)

    def test_invalid_parameters_unknown_routes_and_missing_entities(self):
        for params in ({'limit': 0}, {'limit': 61}, {'limit': 'x'}, {'unknown': 'x'},
                       {'q': 'x'*201}, {'cursor': 'not-a-valid-cursor'}):
            with self.subTest(params=params):
                self.assertEqual(self.get('/api/app/v2/entities/search', params)[0], 400)
        self.assertEqual(self.get('/api/app/v2/entities/search?limit=1&limit=2')[0], 400)
        for path in ('/api/app/v2/unknown', '/api/app/v2/entities/poi/missing',
                     '/api/app/v2/entities/poi/missing/children', '/api/app/v2/menu-groups/missing/items'):
            with self.subTest(path=path):
                self.assertEqual(self.get(path)[0], 404)

    def test_private_paths_denied_even_with_existing_fixture_file(self):
        for path in ('/data/life/organized/fixture/manifest.json', '/data/life/catalog.json',
                     '/api/app/v2/../../data/life/organized/fixture/manifest.json',
                     '/api/app/v2/entities/poi/%2e%2e%2fdata%2flife', '/.env', '/.git/config'):
            with self.subTest(path=path):
                status, body, _ = self.get(path)
                self.assertEqual(status, 404)
                self.assertNotIn('PRIVATE-EXPORT-MARKER', json.dumps(body))

    def test_wrong_host_is_rejected_before_relations_loading(self):
        status, _, _ = self.get('/api/app/v2/summary', headers={'Host': 'untrusted.invalid'})
        self.assertEqual(status, 403)

    def test_public_responses_do_not_include_private_evidence(self):
        for path in ('/api/app/v2/summary', '/api/app/v2/entities/search',
                     '/api/app/v2/entities/poi/canteen-3',
                     '/api/app/v2/menu-groups/'+self.menu_group()+'/items'):
            status, body, _ = self.get(path)
            self.assertEqual(status, 200)
            raw = json.dumps(body, ensure_ascii=False)
            for secret in ('PRIVATE-PHOTO-PATH', 'PRIVATE-ACTOR', 'source_file', 'field_evidence'):
                self.assertNotIn(secret, raw)

    def test_legacy_directory_and_place_keep_original_contract(self):
        status, directory, _ = self.get('/api/app/directory')
        self.assertEqual(status, 200)
        self.assertEqual({p['id'] for p in directory['pois']}, {'canteen-3', 'fixture-sports'})
        self.assertEqual(directory['locations'], [])
        status, body, _ = self.get('/api/app/place', {'id': 'canteen-3', 'offset': 1})
        self.assertEqual(status, 200)
        self.assertIn('notice', body)
        card = body['cards'][0]
        self.assertEqual(card['id'], 'canteen-3')
        self.assertEqual(card['poi_id'], 'canteen-3')
        self.assertEqual(card['menu_total'], 4)
        self.assertEqual(card['menu_offset'], 1)
        self.assertEqual(len(card['menu']), 3)
        self.assertTrue(all({'name', 'price', 'specification', 'source'} <= set(item) for item in card['menu']))
        status, sports, _ = self.get('/api/app/place', {'id': 'fixture-sports'})
        self.assertEqual(status, 200)
        self.assertNotIn('menu', sports['cards'][0])


if __name__ == '__main__':
    unittest.main()
