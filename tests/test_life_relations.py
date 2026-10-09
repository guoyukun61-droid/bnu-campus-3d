"""Data-stage regression with fabricated catalogues; no live services or accounts."""
import copy
import json
import unittest
from unittest.mock import patch

from backend.life_relations import (build_relation_snapshot, RelationRepository,
                                    SnapshotExpired, key, location_of)
from backend.agent.tools import CampusTools
from backend.agent.controller import AgentController
from backend.agent.candidates import recommend_candidates
from backend.catalog_identity import MIXUE, roster_review
from tests.test_agent import catalogue, FakeModel, call, AT


def fixture():
    c = catalogue()
    c['pois'][0].update(building_id='b1', floor='3')
    c['shops'][0].update(entity_type='floor_menu_collection', independent_merchant=False)
    c['items'][0].update(source_evidence_id='photo-stable-1', menu_section='甲窗口菜单',
                         source_file='C:/private/never-expose.jpg')
    c['items'].append(dict(c['items'][0], id='i4', name='牛肉面', price=18))
    c['pois'][1]['spatial_sequence'] = {'group': 'lane', 'label': '巷子', 'order': 2, 'direction': 'north_to_south'}
    c['pois'][1]['location'] = None
    return c


def project(c=None):
    return build_relation_snapshot(c or fixture(), [{'id': 'b1', 'name': '测试楼'}])


class RelationTests(unittest.TestCase):
    def test_lossless_nonmutating_projection(self):
        c = fixture(); before = copy.deepcopy(c); s = project(c)
        self.assertEqual(c, before)
        self.assertEqual(set(s['item_membership']), {i['id'] for i in c['items']})
        self.assertEqual(s['summary']['source_counts'], {'pois': 4, 'shops': 4, 'items': 5})
        self.assertNotIn('never-expose', json.dumps(s))
        self.assertNotIn('source_file', json.dumps(s))
        self.assertEqual(len(s['menu_groups']), 4)

    def test_breadcrumbs_preserve_unconfirmed_window(self):
        s = project(); e = {key(e['ref']): e for e in s['entities']}
        row = e['item:i0']
        self.assertIsNone(row['outlet_id'])
        self.assertEqual([a['ref']['kind'] for a in row['breadcrumbs']], ['building', 'floor', 'poi', 'menu_group'])
        self.assertEqual(e['poi:p0']['map_target']['kind'], 'building_anchor')
        self.assertFalse(e['poi:p0']['map_target']['can_measure_to_entrance'])
        self.assertEqual(e['poi:p1']['map_target']['kind'], 'area_list')

    def test_inactive_collection_does_not_leak_items(self):
        c = fixture(); c['shops'][0]['status'] = 'closed'
        repo = RelationRepository(lambda: project(c))
        result = repo.query('search', kind='item', include_simulated=True)
        self.assertNotIn('i0', [x['ref']['id'] for x in result['items']])
        self.assertNotIn('i4', [x['ref']['id'] for x in result['items']])
        self.assertEqual(project(c)['summary']['source_counts']['items'], 5)

    def test_parent_simulation_and_inference_not_real(self):
        for origin in ('simulated', 'inferred', 'generated'):
            with self.subTest(origin=origin):
                c = fixture(); c['pois'][2]['source'] = origin
                repo = RelationRepository(lambda: project(c))
                self.assertNotIn('s2', [e['ref']['id'] for e in repo.query('search', kind='outlet')['items']])
                item = repo.query('entity', kind='item', ident='i2', include_simulated=True)['entity']
                self.assertEqual(item['data_mode'], 'simulated' if origin == 'simulated' else 'inferred')
                self.assertFalse(item['price_is_verified'])

    def test_inferred_source_remains_explicit(self):
        c = fixture(); c['items'][2]['source'] = 'inferred'
        repo = RelationRepository(lambda: project(c))
        item = repo.query('entity', kind='item', ident='i2', include_simulated=True)['entity']
        self.assertEqual(item['source'], 'inferred')
        self.assertEqual(item['data_mode'], 'inferred')
        gid = item['group_id']
        group = repo.query('entity', kind='menu_group', ident=gid, include_simulated=True)['entity']
        self.assertEqual(group['source'], 'inferred')
        self.assertEqual(group['data_mode'], 'inferred')

    def test_invalid_or_inferred_price_not_verified(self):
        for value in (None, -1, True):
            c=fixture(); c['items'][0]['price']=value
            item=RelationRepository(lambda: project(c)).query('entity',kind='item',ident='i0')['entity']
            self.assertIsNone(item['price']); self.assertFalse(item['price_is_verified'])
        c=fixture(); c['items'][0]['price_source']='inferred'
        item=RelationRepository(lambda: project(c)).query('entity',kind='item',ident='i0',include_simulated=True)['entity']
        self.assertEqual(item['data_mode'],'inferred'); self.assertFalse(item['price_is_verified'])

    def test_identity_and_spatial_validation(self):
        self.assertIsNone(location_of({'location': 'not-a-point'}))
        self.assertIsNone(location_of({'location': {'x': True, 'y': 0, 'crs': 'local EPSG:32650'}}))
        self.assertIsNone(location_of({'location': {'x': 116, 'y': 40}, 'location_crs': 'BD-09'}))
        c = fixture(); c['items'][0]['shop_id'] = 'missing'
        with self.assertRaisesRegex(ValueError, 'Orphan'): project(c)
        c = fixture(); c['pois'].append(copy.deepcopy(c['pois'][0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate'): project(c)

    def test_category_guard_and_crs_across_projection(self):
        c=fixture(); c['pois'][0].update(id=MIXUE,name='新租户小卖部',category='retail',location_crs='BD-09',location={'x':116,'y':40})
        c['shops'][0]['poi_id']=MIXUE
        snapshot=project(c)
        group=next(g for g in snapshot['menu_groups'] if 'i0' in g['item_ids'])
        self.assertEqual(group['category'],'retail')
        row=next(r for r in roster_review(c)['rows'] if r['id']==MIXUE)
        self.assertFalse(row['has_display_point'])

    def test_paging_snapshot_filter_binding(self):
        holder = [project()]; repo = RelationRepository(lambda: holder[0], retain=2)
        first = repo.query('search', kind='item', limit=2)
        c = fixture(); c['items'][0]['name'] = '新版菜单'
        holder[0] = project(c)
        latest = repo.query('search', kind='item', limit=2)
        self.assertNotEqual(first['snapshot_id'], latest['snapshot_id'])
        second = repo.query('search', kind='item', cursor=first['next_cursor'], limit=2)
        self.assertEqual(first['snapshot_id'], second['snapshot_id'])
        self.assertFalse(set(e['ref']['id'] for e in first['items']) & set(e['ref']['id'] for e in second['items']))
        for kwargs in ({'kind': 'poi'}, {'kind': 'item', 'include_simulated': True},
                       {'kind': 'item', 'snapshot_id': latest['snapshot_id']}):
            with self.assertRaises(ValueError): repo.query('search', cursor=first['next_cursor'], **kwargs)
        c['items'][0]['name'] = '再新版'; holder[0] = project(c); repo.snapshot()
        with self.assertRaises(SnapshotExpired): repo.snapshot(first['snapshot_id'])

    def test_snapshot_copies_and_invalid_cursor(self):
        repo = RelationRepository(project)
        one = repo.snapshot(); one['entities'].clear()
        self.assertTrue(repo.snapshot(one['snapshot_id'])['entities'])
        for token in ('???', 'W10', 'bnVsbA', 'a', 'e30'):
            with self.subTest(token=token), self.assertRaises(ValueError): repo.query('search', cursor=token)
        with self.assertRaises(ValueError): repo.query('search', limit=True)

    def test_same_building_group_children(self):
        s = project()
        for rel in s['relations']:
            if rel['type'] == 'member_of':
                rel['type'] = 'same_building_member'
        repo = RelationRepository(lambda: s)
        rows = repo.query('children', kind='area', ident='lane')['items']
        self.assertEqual([r['ref']['id'] for r in rows], ['p1'])


class DataConsumerTests(unittest.TestCase):
    def test_generated_any_parent_excluded_from_real_candidates(self):
        for table in ('items','shops','pois'):
            c=catalogue(); c[table][0]['content_origin']='generated'
            self.assertNotIn('i0',[r['id'] for r in recommend_candidates(c,{'budget':20},at=AT)['cards']])

    def test_legacy_tool_parent_simulation_and_closed_search(self):
        c=fixture(); c['pois'][0]['content_origin']='simulated'; tools=CampusTools(c)
        self.assertNotIn('p0',[p['id'] for p in tools.directory()['pois']])
        with self.assertRaises(ValueError): tools.execute('get_place',{'poi_id':'p0'}, {})
        self.assertTrue(tools.place(c['pois'][0])['simulation'])
        c=fixture(); c['shops'][0]['status']='closed'; tools=CampusTools(c)
        for query in ('甲窗口','牛肉面'):
            self.assertEqual(tools.execute('search_places',{'query':query},{})['cards'],[])

    def test_null_aliases_dont_break_search(self):
        c=fixture(); c['pois'][0]['aliases']=None
        self.assertTrue(CampusTools(c).execute('search_places',{'query':'测试食堂0'},{})['cards'])
        self.assertTrue(project(c))

    def test_side_and_weighted_prices_not_meals(self):
        for role in ('side', 'weight_based'):
            c = catalogue(); c['items'][0].update(meal_role=role, price=3, name='香辣菜')
            self.assertNotIn('i0', [r['id'] for r in recommend_candidates(c, {'budget': 20}, at=AT)['cards']])

    def test_inferred_and_closed_not_candidates(self):
        for field, value in (('source', 'inferred'), ('status', 'historical'), ('content_origin', 'inferred')):
            c = catalogue(); c['items'][0][field] = value
            self.assertNotIn('i0', [r['id'] for r in recommend_candidates(c, {'budget': 20}, at=AT)['cards']])

    def test_same_floor_window_exclusion_works_via_tools(self):
        c = catalogue(); c['shops'][1]['poi_id'] = 'p0'
        r = CampusTools(c).execute('recommend_food', {'budget':20, 'exclude_outlet_ids':['s0']}, {}, at=AT)
        self.assertNotIn('i0', [x['id'] for x in r['cards']])
        self.assertIn('i1', [x['id'] for x in r['cards']])
        with self.assertRaises(ValueError): CampusTools(c).execute('recommend_food', {'budget':20, 'exclude_outlet_ids':['p0']}, {}, at=AT)

    def test_flat_api_compatibility_plus_relations(self):
        c = fixture(); tools = CampusTools(c)
        card = tools.execute('get_place', {'poi_id':'p0'}, {})['cards'][0]
        self.assertEqual(card['menu_total'], 2)
        self.assertEqual(len(card['menu']), 2)
        self.assertEqual(len(card['menu_groups']), 1)
        self.assertEqual(card['menu'][0]['group_id'], card['menu_groups'][0]['id'])
        found = tools.execute('search_places', {'query':'甲窗口'}, {})['cards']
        self.assertEqual(found[0]['poi_id'], 'p0')

    def test_agent_turn_freezes_catalog(self):
        c = catalogue(); tools = CampusTools(c)
        class MutatingModel(FakeModel):
            def complete(self, *args):
                c['items'][0]['price'] = 999
                return super().complete(*args)
        model = MutatingModel([call(budget=20), {'content':'done'}])
        with patch('backend.agent.candidates.now', return_value=AT):
            result = AgentController(model, tools).run({'message':'查菜单'})
        self.assertEqual(next(r for r in result['cards'] if r['id']=='i0')['price'], 10)
        self.assertEqual(c['items'][0]['price'], 999)


if __name__ == '__main__':
    unittest.main()
