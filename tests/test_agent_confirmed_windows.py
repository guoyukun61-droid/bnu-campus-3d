"""Confirmed window identity/hours and archived alias DTOs, with fabricated data."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from backend.agent.candidates import recommend_candidates
from backend.agent.tools import CampusTools
from backend.menu_relations import build_menu_relations, _PHOTO_HASHES


AT = '2026-10-08T12:00:00+08:00'


def window_catalog():
    collection = 'menu-collection-xinlequn-3'
    return dict(
        pois=[dict(id='canteen-3', name='新乐群三层', floor='3', category='canteen',
                   source='published', status='verified', building_id=499434918,
                   opening_hours=[['10:30', '13:30']], opening_hours_text='楼层10:30–13:30',
                   location={'x': 10, 'y': 0}, location_crs='local EPSG:32650')],
        shops=[dict(id=collection, name='三层菜单集合', poi_id='canteen-3', floor='3',
                    source='menu_photo', entity_type='floor_menu_collection',
                    independent_merchant=False, opening_hours=[['06:00', '23:00']],
                    opening_hours_text='集合06:00–23:00')],
        items=[dict(id=f'i{n}', shop_id=collection, name=f'香辣鸡肉饭{n}', source='menu_photo',
                    source_photo_sha256=_PHOTO_HASHES[photo], price=10+n, tags=['辣'],
                    available=True, source_file='C:/private/must-not-leak.jpg',
                    field_evidence={'private_note': 'must-not-leak'})
               for n, photo in enumerate(('458', '458', '459', '460'))],
        locations=[dict(id='origin', name='起点', x=0, y=0)], walking_times=[])


def alias_catalog():
    return dict(
        pois=[dict(id='laixifu', name='来喜福', category='snack', source='field_observation',
                   status='verified', building_id=499437078, building_part='north',
                   location_description='学五食堂同建筑北面',
                   location_review_status='building_confirmed_entrance_unknown',
                   confirmed_relations=[dict(relation='located_in_part', target_kind='building',
                                             target_id='499437078', precision='qualitative',
                                             evidence={'batch': 'user-relations-20261008',
                                                       'private_path': 'must-not-leak'})]),
              dict(id='old-laixifu', name='来喜福炒酸奶鸡蛋仔', category='snack',
                   source='field_observation', status='archived', canonical_poi_id='laixifu',
                   field_evidence={'private_note': 'must-not-leak'})],
        shops=[dict(id='canonical-shop', poi_id='laixifu', name='来喜福', source='field_observation'),
               dict(id='old-shop', poi_id='old-laixifu', name='旧来喜福', source='field_observation')],
        items=[dict(id='canonical-item', shop_id='canonical-shop', name='鸡蛋仔', price=8, source='menu_photo'),
               dict(id='old-item', shop_id='old-shop', name='旧鸡蛋仔', price=7, source='menu_photo')],
        locations=[], walking_times=[])


class ConfirmedWindowAgentTests(unittest.TestCase):
    def test_same_floor_returns_distinct_confirmed_windows_not_one_collection(self):
        catalog = window_catalog(); original = deepcopy(catalog)
        result = recommend_candidates(catalog, {'budget': 20}, at=AT)
        self.assertEqual(catalog, original)
        cards = result['cards']
        self.assertEqual(len(cards), 3)
        self.assertEqual(len({c['outlet_id'] for c in cards}), 3)
        self.assertEqual({c['shop_id'] for c in cards}, {'menu-collection-xinlequn-3'})
        self.assertEqual({c['id'] for c in cards}, {'i0', 'i2', 'i3'})
        names = {o['id']: o['name'] for o in build_menu_relations(catalog)['outlets']}
        self.assertTrue(all(c['shop'] == names[c['outlet_id']] for c in cards))
        self.assertNotIn('must-not-leak', json.dumps(result))

    def test_window_unknown_hours_do_not_inherit_collection_or_floor_hours(self):
        cards = recommend_candidates(window_catalog(), {'budget': 20}, at=AT)['cards']
        for card in cards:
            self.assertEqual(card['hours'], '尚未录入')
            self.assertEqual(card['hours_scope'], 'outlet')
            self.assertIsNone(card['outlet_opening_hours'])
            self.assertEqual(card['outlet_hours_label'], '尚未录入')
            self.assertIn('窗口营业时间尚未录入', card['unknown'])
            self.assertEqual(card['venue_opening_hours'], [['10:30', '13:30']])
            self.assertNotIn('窗口身份待核，当前按楼层供餐集合保守去重', card['unknown'])

    def test_closed_parent_floor_is_a_separate_constraint_not_window_hours(self):
        result = recommend_candidates(window_catalog(), {'budget': 20}, at='2026-10-08T14:00:00+08:00')
        self.assertEqual(result['cards'], [])
        self.assertEqual(result['rejected']['所在楼层记录时段不营业'], 4)
        self.assertNotIn('记录时段不营业', result['rejected'])

    def test_actual_window_hours_when_provided_are_not_ignored(self):
        catalog = window_catalog(); projection = build_menu_relations(catalog)
        closed = projection['outlets'][0]
        closed.update(opening_hours=[['18:00', '20:00']], opening_hours_text='18:00–20:00')
        with patch('backend.menu_relations.build_menu_relations', return_value=projection):
            result = recommend_candidates(catalog, {'budget': 20}, at=AT)
        self.assertNotIn(closed['id'], {c['outlet_id'] for c in result['cards']})
        self.assertEqual(result['rejected']['记录时段不营业'], 2)

    def test_excluding_one_window_does_not_exclude_its_floor(self):
        result = recommend_candidates(window_catalog(), {
            'budget': 20, 'exclude_outlet_ids': ['outlet-xinlequn-3-001']}, at=AT)
        self.assertEqual({c['outlet_id'] for c in result['cards']},
                         {'outlet-xinlequn-3-002', 'outlet-xinlequn-3-003'})
        self.assertEqual({c['poi_id'] for c in result['cards']}, {'canteen-3'})

    def test_unknown_source_groups_still_deduplicate_by_collection(self):
        catalog = window_catalog()
        for item in catalog['items']:
            item.pop('source_photo_sha256')
        cards = recommend_candidates(catalog, {'budget': 20}, at=AT)['cards']
        self.assertEqual(len(cards), 1)
        self.assertIsNone(cards[0]['outlet_id'])
        self.assertIn('窗口身份待核，当前按楼层供餐集合保守去重', cards[0]['unknown'])

    def test_menu_dto_exposes_membership_and_window_hours_without_private_audit(self):
        result = CampusTools(window_catalog()).execute('get_place', {'poi_id': 'canteen-3'}, {})
        card = result['cards'][0]
        self.assertEqual(card['menu_total'], 4)
        self.assertEqual(len(card['outlets']), 3)
        self.assertEqual(len(card['menu_groups']), 3)
        by_id = {o['id']: o for o in card['outlets']}
        for item in card['menu']:
            self.assertEqual(item['outlet_name'], by_id[item['outlet_id']]['name'])
            self.assertEqual(item['shop_id'], 'menu-collection-xinlequn-3')
            self.assertIsNone(item['outlet_opening_hours'])
            self.assertEqual(item['outlet_hours_label'], '尚未录入')
        for group in card['menu_groups']:
            self.assertEqual(group['outlet_name'], by_id[group['outlet_id']]['name'])
            self.assertEqual(group['outlet_hours_label'], '尚未录入')
        for outlet in card['outlets']:
            self.assertIsNone(outlet['opening_hours'])
            self.assertEqual(outlet['hours_label'], '尚未录入')
            self.assertFalse(outlet['signboard_name_verified'])
            self.assertNotIn('identity_evidence', outlet)
        self.assertNotIn('must-not-leak', json.dumps(result))

    def test_search_returns_matching_confirmed_window_relation(self):
        result = CampusTools(window_catalog()).execute('search_places', {'query': '重庆嘞碗面'}, {})
        self.assertEqual(len(result['cards']), 1)
        match = result['cards'][0]['matched_menu_groups'][0]
        self.assertEqual(match['outlet_id'], 'outlet-xinlequn-3-002')
        self.assertEqual(match['identity_status'], 'confirmed')


class CanonicalAliasAgentTests(unittest.TestCase):
    def test_old_id_resolves_without_returning_archived_menu(self):
        catalog = alias_catalog(); before = deepcopy(catalog)
        card = CampusTools(catalog).execute('get_place', {'poi_id': 'old-laixifu'}, {})['cards'][0]
        self.assertEqual(card['id'], 'laixifu')
        self.assertEqual(card['requested_poi_id'], 'old-laixifu')
        self.assertEqual(card['canonical_poi_id'], 'laixifu')
        self.assertIn('旧记录', card['alias_notice'])
        self.assertEqual([i['id'] for i in card['menu']], ['canonical-item'])
        self.assertEqual(catalog, before)

    def test_search_and_directory_return_only_one_active_identity(self):
        tools = CampusTools(alias_catalog())
        for query in ('来喜福', '来喜福炒酸奶鸡蛋仔'):
            with self.subTest(query=query):
                result = tools.execute('search_places', {'query': query}, {})
                self.assertEqual([c['id'] for c in result['cards']], ['laixifu'])
                self.assertEqual(result['total'], 1)
        self.assertEqual([p['id'] for p in tools.directory()['pois']], ['laixifu'])

    def test_safe_confirmations_are_visible_and_private_audit_is_not(self):
        catalog = alias_catalog()
        catalog['pois'][0]['field_evidence'] = {'private_path': 'must-not-leak'}
        card = CampusTools(catalog).execute('get_place', {'poi_id': 'laixifu'}, {})['cards'][0]
        self.assertEqual(card['building_part'], 'north')
        self.assertEqual(card['location_description'], '学五食堂同建筑北面')
        self.assertEqual(card['confirmed_relations'][0]['target_id'], '499437078')
        self.assertNotIn('must-not-leak', json.dumps(card))

    def test_missing_cycle_or_archived_canonical_target_is_rejected(self):
        for target in ('missing', 'old-laixifu', 'archived-target'):
            with self.subTest(target=target):
                catalog = alias_catalog()
                catalog['pois'][1]['canonical_poi_id'] = target
                catalog['pois'].append(dict(id='archived-target', name='历史店', status='archived'))
                with self.assertRaises(ValueError):
                    CampusTools(catalog).execute('get_place', {'poi_id': 'old-laixifu'}, {})
        catalog = alias_catalog()
        catalog['pois'][0]['canonical_poi_id'] = 'old-laixifu'
        with self.assertRaises(ValueError):
            CampusTools(catalog).execute('get_place', {'poi_id': 'old-laixifu'}, {})


if __name__ == '__main__':
    unittest.main()
