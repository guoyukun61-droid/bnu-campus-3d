"""The second human-confirmation batch; only fabricated source snapshots."""
import copy
import json
import unittest

from backend.confirmed_relations import apply_confirmed_relations, public_confirmations, BATCH
from backend.catalog_identity import (WEST_BUILDING_IDS, NORTHWEST_REFERENCE, LAIXIFU_CANDIDATE,
    YOUGUOHUI, TMALL, MIXUE, KFC, roster_review)
from backend.life_relations import build_relation_snapshot, RelationRepository


def fixture():
    names = {**dict(zip(WEST_BUILDING_IDS, ('乡村基', '塔斯汀', '鹏记重庆鸡公煲', '夜罐罐米线', '库迪咖啡（西北食堂西侧）'))),
             NORTHWEST_REFERENCE: '西北风味餐厅(北师大店)', 'laixifu': '来喜福',
             LAIXIFU_CANDIDATE: '来喜福炒酸奶鸡蛋仔', YOUGUOHUI: '优果荟', TMALL: '天猫校园超市(北师大店)',
             MIXUE: '蜜雪冰城(北师大店)', KFC: '肯德基(北京师范大学店)'}
    pois = [dict(id=i, name=n, category='restaurant', source='user_reported', status='unverified',
                 location=None, building_id=None, opening_hours=None) for i, n in names.items()]
    p = {row['id']: row for row in pois}
    p[NORTHWEST_REFERENCE]['building_id'] = 499437130
    for ident in WEST_BUILDING_IDS:
        p[ident]['map_reference'] = dict(x=-278.648, y=-400.365, crs='local EPSG:32650',
                                          building_id=499437130, precision='reference_only')
    p[WEST_BUILDING_IDS[2]]['floor'] = '2'
    p['laixifu'].update(building_id=499437078, opening_hours_text='09:00或10:00-23:30',
                       display_anchor=dict(x=-278.347, y=-355.63, crs='local EPSG:32650', building_id=499437078))
    p[YOUGUOHUI]['location'] = dict(x=-354.73, y=-326.87)
    p[TMALL]['location'] = dict(x=359.73, y=-227.52)
    for i in (YOUGUOHUI, TMALL):
        p[i]['location_crs'] = 'local EPSG:32650'
        p[i]['spatial_sequence'] = dict(group='tmall-services', order=1, direction='north_to_south')
    return dict(pois=pois, shops=[dict(id='shop-'+p['id'], poi_id=p['id'], name=p['name']) for p in pois], items=[])


class ConfirmedRelationsTests(unittest.TestCase):
    def test_read_projection_idempotent_lossless_and_keeps_original_evidence(self):
        c = fixture(); original = copy.deepcopy(c)
        result = apply_confirmed_relations(c)
        self.assertEqual(c, original)
        self.assertEqual(apply_confirmed_relations(result), result)
        self.assertEqual([s['id'] for s in result['shops']], [s['id'] for s in original['shops']])
        self.assertEqual([p['id'] for p in result['pois']], [p['id'] for p in c['pois']])

    def test_west_binding_is_building_part_not_a_new_entrance(self):
        result = apply_confirmed_relations(fixture()); p = {p['id']: p for p in result['pois']}
        for ident in WEST_BUILDING_IDS:
            self.assertEqual(p[ident]['building_id'], 499437130)
            self.assertEqual(p[ident]['building_part'], 'southwest')
            self.assertEqual(p[ident]['display_anchor']['precision'], 'building')
            self.assertIsNone(p[ident]['location'])
            self.assertIsNone(p[ident]['map_reference'])
        self.assertEqual(p[WEST_BUILDING_IDS[2]]['floor'], '2')
        self.assertEqual(roster_review(result)['same_building_groups'][0]['model_mapping_status'], 'user_confirmed')

    def test_same_store_alias_and_north_part_keep_hours(self):
        result = apply_confirmed_relations(fixture()); p = {p['id']: p for p in result['pois']}
        self.assertEqual(p[LAIXIFU_CANDIDATE]['canonical_poi_id'], 'laixifu')
        self.assertEqual(p[LAIXIFU_CANDIDATE]['status'], 'archived')
        self.assertEqual(p['laixifu']['building_part'], 'north')
        self.assertEqual(p['laixifu']['opening_hours_text'], '09:00或10:00-23:30')
        self.assertNotIn('possible_same_as', [r['code'] for r in roster_review(result)['issues']])

    def test_conflicting_absolute_points_not_arbitrarily_chosen(self):
        result = apply_confirmed_relations(fixture()); p = {p['id']: p for p in result['pois']}
        for ident, direction in ((YOUGUOHUI, 'west_of'), (TMALL, 'east_of')):
            self.assertIsNone(p[ident]['location'])
            self.assertIsNone(p[ident]['map_point'])
            self.assertIsNone(p[ident]['display_anchor'])
            self.assertIn(direction, [r['relation'] for r in p[ident]['confirmed_relations']])
            self.assertEqual(p[ident]['spatial_sequence']['direction'], 'unknown')
        self.assertIn('adjacent_pair_absolute_position_pending', [i['code'] for i in roster_review(result)['issues']])

    def test_adjacent_does_not_swap_points(self):
        c = fixture(); p = {p['id']: p for p in c['pois']}
        p[MIXUE]['location'] = dict(x=1, y=0)
        p[KFC]['location'] = dict(x=1, y=1.33)
        result = {p['id']: p for p in apply_confirmed_relations(c)['pois']}
        self.assertEqual(result[MIXUE]['location'], p[MIXUE]['location'])
        self.assertEqual(result[KFC]['location'], p[KFC]['location'])
        self.assertEqual(result[MIXUE]['confirmed_relations'][0]['relation'], 'adjacent_to')

    def test_name_guards_future_edits_and_corrected_points_win(self):
        c = fixture(); p = {p['id']: p for p in c['pois']}
        p[WEST_BUILDING_IDS[0]]['name'] = '另一个租户'
        p[WEST_BUILDING_IDS[1]]['field_evidence'] = {'building_id': {'reviewed_at': '2026-10-08T22:00:00+08:00'}}
        p[LAIXIFU_CANDIDATE]['field_evidence'] = {'canonical_poi_id': {'reviewed_at': '2026-10-09'}}
        p[YOUGUOHUI]['location'] = dict(x=100, y=100)
        result = {p['id']: p for p in apply_confirmed_relations(c)['pois']}
        for ident in WEST_BUILDING_IDS[:2]:
            self.assertIsNone(result[ident]['building_id'])
        self.assertNotIn('canonical_poi_id', result[LAIXIFU_CANDIDATE])
        self.assertEqual(result[YOUGUOHUI]['location'], dict(x=100, y=100))

    def test_typed_relations_alias_query_and_visibility(self):
        c = fixture()
        buildings = [dict(id=499437130, name='西北食堂'), dict(id=499437078, name='学五食堂')]
        snapshot = build_relation_snapshot(c, buildings)
        repo = RelationRepository(lambda: snapshot)
        redirected = repo.query('entity', kind='poi', ident=LAIXIFU_CANDIDATE)
        self.assertEqual(redirected['entity']['ref']['id'], 'laixifu')
        self.assertEqual(redirected['redirected_from']['id'], LAIXIFU_CANDIDATE)
        found = repo.query('search', query='来喜福', kind='poi')
        self.assertEqual(found['total'], 1)
        types = {r['type'] for r in snapshot['relations']}
        self.assertTrue({'same_as', 'adjacent_to', 'west_of', 'east_of', 'located_in_part'} <= types)
        west = repo.query('entity', kind='poi', ident=WEST_BUILDING_IDS[2])['entity']
        self.assertEqual([x['ref']['kind'] for x in west['breadcrumbs']], ['building', 'floor'])
        self.assertFalse(west['map_target']['can_measure_to_entrance'])
        self.assertEqual(west['hours'], '尚未录入')

    def test_public_metadata_does_not_copy_raw_audit(self):
        row = apply_confirmed_relations(fixture())['pois'][0]
        row['field_evidence'] = {'actor': 'PRIVATE', 'source_file': 'SECRET-PATH'}
        row['confirmed_relations'][0]['evidence'].update(private_path='SECRET-PATH', note='PRIVATE')
        safe = json.dumps(public_confirmations(row), ensure_ascii=False)
        self.assertNotIn('PRIVATE', safe)
        self.assertNotIn('SECRET-PATH', safe)
        self.assertIn(BATCH, safe)

    def test_future_description_wins_and_wrong_building_anchor_is_retired(self):
        c = fixture(); p = {p['id']: p for p in c['pois']}
        p['laixifu'].update(location_description='后续人工选点说明',
                            field_evidence={'location_description': {'reviewed_at': '2026-10-09'}})
        p[WEST_BUILDING_IDS[0]]['display_anchor'] = dict(x=9, y=9, crs='local EPSG:32650', building_id=999)
        p[WEST_BUILDING_IDS[1]]['map_reference'] = None
        p[WEST_BUILDING_IDS[1]]['display_anchor'] = dict(x=9, y=9, crs='local EPSG:32650', building_id=999)
        result = {p['id']: p for p in apply_confirmed_relations(c)['pois']}
        self.assertEqual(result['laixifu']['location_description'], '后续人工选点说明')
        self.assertEqual(result[WEST_BUILDING_IDS[0]]['display_anchor']['building_id'], 499437130)
        self.assertIsNone(result[WEST_BUILDING_IDS[1]]['display_anchor'])

    def test_description_cannot_expose_private_paths_or_credentials(self):
        for value in ('管理员备注 C:/private/photos/a.jpg', '资料 /private/photo.jpg', 'token=PRIVATE'):
            self.assertNotIn('location_description', public_confirmations(dict(location_description=value)))

    def test_existing_canonical_reverse_relation_is_not_overridden(self):
        c = fixture(); p = {p['id']: p for p in c['pois']}
        p['laixifu']['canonical_poi_id'] = LAIXIFU_CANDIDATE
        result = {p['id']: p for p in apply_confirmed_relations(c)['pois']}
        self.assertNotIn('canonical_poi_id', result[LAIXIFU_CANDIDATE])
        self.assertEqual(result[LAIXIFU_CANDIDATE]['status'], 'unverified')

    def test_alias_children_are_preserved_under_canonical_identity(self):
        from backend.agent.tools import CampusTools
        c = fixture()
        c['locations'] = []
        c['items'] = [dict(id='old-item', shop_id='shop-'+LAIXIFU_CANDIDATE,
                           name='鸡蛋仔', price=8, source='menu_photo')]
        result = apply_confirmed_relations(c)
        self.assertEqual(result['items'], c['items'])
        oldshop = next(s for s in result['shops'] if s['id'] == 'shop-'+LAIXIFU_CANDIDATE)
        self.assertEqual(oldshop['poi_id'], 'laixifu')
        self.assertEqual(oldshop['source_poi_id'], LAIXIFU_CANDIDATE)
        self.assertEqual(oldshop['canonical_shop_id'], 'shop-laixifu')
        card = CampusTools(result).execute('get_place', {'poi_id': 'laixifu'}, {})['cards'][0]
        self.assertEqual(card['menu_total'], 1)
        self.assertEqual(card['menu'][0]['outlet_id'], 'shop-laixifu')
        repo = RelationRepository(lambda: build_relation_snapshot(result, []))
        item = repo.query('search', kind='item')['items'][0]
        self.assertEqual(item['ref']['id'], 'old-item')
        self.assertEqual(item['outlet_id'], 'shop-laixifu')


if __name__ == '__main__':
    unittest.main()
