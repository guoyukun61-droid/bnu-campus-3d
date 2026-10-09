"""Entity context contracts use fabricated catalogues, without account/secret IO."""
import copy
import json
import unittest
from unittest.mock import Mock

from backend.agent.context import (validate_context, validate_previous_entities,
                                   previous_entities_from_cards, resolve_context, resolve_entity)
from backend.agent.tools import CampusTools


def context_tools():
    pois = [dict(id='p0', name='测试食堂', category='canteen', source='field_observation',
                 status='verified', building_id='b0', floor='2', address='测试地址',
                 location={'x': 5, 'y': 6}, location_crs='local EPSG:32650'),
            dict(id='demo', name='模拟食堂', category='canteen', source='simulated', status='verified'),
            dict(id='closed', name='旧店', category='canteen', source='field_observation', status='closed'),
            dict(id='business-closed', name='停业店', category='canteen', source='field_observation',
                 status='verified', business_status='已关闭')]
    shops = [dict(id='s0', name='测试窗口', poi_id='p0', floor='2', source='field_observation'),
             dict(id='demo-shop', name='模拟窗口', poi_id='demo', source='simulated'),
             dict(id='closed-shop', name='旧窗口', poi_id='closed', source='field_observation')]
    catalog = dict(pois=pois, shops=shops, items=[], locations=[], walking_times=[])
    return CampusTools(catalog, buildings=[dict(id='b0', name='测试楼')], areas=[])


class ContextValidationTests(unittest.TestCase):
    def test_optional_and_clear_shapes(self):
        for value in (None, {}, {'selected': None}):
            self.assertEqual(validate_context(value), {'selected': None})
        ref = {'selected': {'kind': 'outlet', 'id': 's0'}}
        self.assertEqual(validate_context(ref), ref)
        self.assertIsNot(validate_context(ref)['selected'], ref['selected'])

    def test_fact_fields_and_invalid_ids_are_rejected(self):
        invalid = [[], 'p0', {'name': 'fake'}, {'selected': {}},
                   {'selected': {'kind': 'item', 'id': 'p0'}},
                   {'selected': {'kind': 'poi', 'id': 'p0', 'name': 'fake'}},
                   {'selected': {'kind': 'poi', 'id': 'p0', 'location': {'x': 1}}}]
        invalid += [{'selected': {'kind': 'poi', 'id': value}}
                    for value in (None, 5, True, '', ' ', 'x' * 101, 'x\n', 'x\x7f', 'x\u0085', 'x\u202e')]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_context(value)

    def test_previous_references_are_bounded_and_deduplicated(self):
        ref = {'kind': 'poi', 'id': 'p0'}
        self.assertEqual(validate_previous_entities([ref, ref]), [ref])
        for value in ({}, [ref] * 13, [dict(ref, name='fake')]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_previous_entities(value)

    def test_card_references_preserve_windows_without_promoting_item_ids(self):
        cards = [dict(type='food', id='item-1', outlet_id='s0', poi_id='p0'),
                 dict(type='food', id='item-2', outlet_id='s1', poi_id='p0'),
                 dict(type='food', id='item-only'), dict(type='schedule', id='course'),
                 dict(type='place', id='place-old'), dict(ref={'kind': 'building', 'id': 'b0'}),
                 None, dict(type='food', poi_id={'fake': True})]
        self.assertEqual(previous_entities_from_cards(cards), [
            {'kind': 'outlet', 'id': 's0'}, {'kind': 'poi', 'id': 'p0'},
            {'kind': 'outlet', 'id': 's1'}, {'kind': 'poi', 'id': 'place-old'},
            {'kind': 'building', 'id': 'b0'}])
        self.assertEqual(len(previous_entities_from_cards([dict(type='place', id=str(n)) for n in range(40)])), 12)

    def test_window_detail_card_id_does_not_become_an_extra_poi(self):
        cards = [dict(type='place', id='s0', outlet_id='s0', poi_id='p0')]
        self.assertEqual(previous_entities_from_cards(cards), [
            {'kind': 'outlet', 'id': 's0'}, {'kind': 'poi', 'id': 'p0'}])


class ContextResolutionTests(unittest.TestCase):
    def setUp(self):
        self.tools = context_tools().frozen()

    def resolve(self, kind='poi', ident='p0', **kwargs):
        return resolve_context(self.tools, {'selected': {'kind': kind, 'id': ident}}, **kwargs)

    def test_empty_context_needs_no_catalogue_access(self):
        tools = Mock()
        self.assertEqual(resolve_context(tools), dict(selected=None, previous_entities=[], notices=[]))
        tools.snapshot.assert_not_called()

    def test_detail_tools_share_the_identity_gate(self):
        result = resolve_entity(self.tools, {'kind': 'outlet', 'id': 's0'})
        self.assertEqual(result['id'], 's0')
        self.assertNotIn('description', result)
        self.assertIsNone(resolve_entity(self.tools, {'kind': 'poi', 'id': 'missing'}))
        with self.assertRaises(ValueError):
            resolve_entity(self.tools, None)

    def test_selected_and_previous_metadata_come_from_frozen_catalogue(self):
        before = copy.deepcopy(self.tools.catalog)
        result = self.resolve('outlet', 's0', previous_entities=[{'kind': 'poi', 'id': 'p0'}])
        selected = result['selected']
        self.assertEqual((selected['kind'], selected['id'], selected['name']), ('outlet', 's0', '测试窗口'))
        self.assertEqual((selected['poi_id'], selected['building_id'], selected['floor']), ('p0', 'b0', '2'))
        self.assertEqual(result['previous_entities'][0]['name'], '测试食堂')
        self.assertEqual(self.resolve('building', 'b0')['selected']['building_id'], 'b0')
        self.assertEqual(self.tools.catalog, before)
        for field in ('location', 'address', 'conditions', 'current_location', 'source', 'field_evidence'):
            self.assertNotIn(field, selected)

    def test_missing_closed_and_closed_parent_objects_are_cleared(self):
        for kind, ident in (('poi', 'missing'), ('poi', 'closed'), ('outlet', 'closed-shop'),
                            ('poi', 'business-closed'), ('outlet', 'p0'), ('building', 'p0')):
            with self.subTest(kind=kind, ident=ident):
                result = self.resolve(kind, ident)
                self.assertIsNone(result['selected'])
                self.assertTrue(result['notices'])

    def test_stale_history_is_filtered_after_current_catalogue_lookup(self):
        result = resolve_context(self.tools, previous_entities=[{'kind': 'outlet', 'id': 's0'},
                                                               {'kind': 'poi', 'id': 'closed'}])
        self.assertEqual([r['id'] for r in result['previous_entities']], ['s0'])
        self.assertTrue(result['notices'])

    def test_simulated_records_never_enter_real_context(self):
        self.assertIsNone(self.resolve('poi', 'demo')['selected'])
        self.assertIsNone(self.resolve('outlet', 'demo-shop')['selected'])
        selected = self.resolve('outlet', 'demo-shop', mode='demo')['selected']
        self.assertEqual(selected['data_mode'], 'simulated')
        self.assertTrue(selected['is_simulated'])
        self.assertFalse(self.resolve('building', 'b0', mode='demo')['selected']['is_simulated'])

    def test_private_source_fields_and_private_names_do_not_escape(self):
        self.tools.catalog['pois'][0].update(name=r'C:\private\photo.jpg', field_evidence={'password': 'not-public'})
        result = self.resolve()
        self.assertEqual(result['selected']['name'], '未命名记录')
        self.assertNotIn('private', json.dumps(result))
        self.assertNotIn('not-public', json.dumps(result))

    def test_one_turn_keeps_frozen_identity(self):
        original = context_tools()
        frozen = original.frozen()
        original.catalog['pois'][0]['name'] = '后续修改名称'
        result = resolve_context(frozen, {'selected': {'kind': 'poi', 'id': 'p0'}})
        self.assertEqual(result['selected']['name'], '测试食堂')

    def test_reference_building_never_becomes_containment(self):
        poi = self.tools.catalog['pois'][0]
        poi.pop('building_id')
        poi.pop('location')
        poi['map_reference'] = {'building_id': 'b0', 'precision': 'reference_only'}
        result = self.resolve()['selected']
        self.assertNotIn('building_id', result)
        # Defensive handling if a later public DTO places the reference at top level.
        row = next(e for e in self.tools._relation_snapshot['entities'] if e['ref'] == {'kind': 'poi', 'id': 'p0'})
        row['map_target'] = {'kind': 'reference_area', 'building_id': 'b0'}
        self.assertNotIn('building_id', self.resolve()['selected'])


if __name__ == '__main__':
    unittest.main()
