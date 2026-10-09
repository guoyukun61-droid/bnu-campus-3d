import copy
import json
import unittest

from backend.catalog_identity import (
    COTTI, IDENTITY_RULES, KFC, LAIXIFU_CANDIDATE, MIXUE,
    NORTHWEST_REFERENCE, ROSTER_GROUPS, ROSTER_IDS, TMALL, WEST_BUILDING_IDS,
    YOUGUOHUI, ZENGSANXIAN, normalize_identity, roster_review,
)


def fixture():
    pois = [dict(id=ident, name=name, category='restaurant', location=None, location_crs='local EPSG:32650',
                 field_evidence={'source_file': 'PRIVATE-PHOTO', 'actor': 'PRIVATE-PERSON'})
            for _, _, rows in ROSTER_GROUPS for ident, name in rows]
    index = {poi['id']: poi for poi in pois}
    for ident, rule in IDENTITY_RULES.items():
        index[ident]['name'] = rule['names'][0]
    return dict(pois=pois, shops=[dict(id='fixture-shop', poi_id=MIXUE)], items=[])


class CatalogIdentityTests(unittest.TestCase):
    def test_deep_copy_preserves_all_ids_private_evidence_and_unrelated_fields(self):
        catalog = fixture()
        original = copy.deepcopy(catalog)
        result = normalize_identity(catalog)
        self.assertEqual(catalog, original)
        self.assertEqual([p['id'] for p in result['pois']], list(ROSTER_IDS))
        self.assertEqual(result['shops'], original['shops'])
        result['shops'][0]['id'] = 'mutated'
        self.assertEqual(catalog['shops'][0]['id'], 'fixture-shop')
        self.assertEqual(result['pois'][0]['field_evidence'], original['pois'][0]['field_evidence'])

    def test_exact_aliases_category_and_idempotence(self):
        catalog = fixture()
        next(p for p in catalog['pois'] if p['id'] == ZENGSANXIAN)['aliases'] = ['已有别名']
        result = normalize_identity(catalog)
        index = {p['id']: p for p in result['pois']}
        self.assertEqual(index[ZENGSANXIAN]['aliases'], ['已有别名', '曾三线米线'])
        self.assertEqual(index[TMALL]['aliases'], ['24h超市', '24小时超市'])
        self.assertEqual(index[YOUGUOHUI]['aliases'], ['优果荟水果超市'])
        self.assertEqual(index[MIXUE]['category'], 'drink')
        self.assertEqual(index[MIXUE]['original_category'], 'restaurant')
        self.assertEqual(normalize_identity(result), result)

    def test_both_id_and_name_required_no_branch_or_renamed_tenant_change(self):
        catalog = dict(pois=[
            dict(id=MIXUE, name='另一家商店', category='retail'),
            dict(id='other-branch', name=IDENTITY_RULES[MIXUE]['names'][0], category='restaurant'),
            dict(id=TMALL, name='改名店铺', aliases=['手工别名']),
        ])
        self.assertEqual(normalize_identity(catalog), catalog)
        codes = [issue['code'] for issue in roster_review(catalog)['issues']]
        self.assertIn('identity_mapping_name_changed', codes)

    def test_does_not_discard_malformed_manual_aliases(self):
        catalog = dict(pois=[dict(id=TMALL, name=IDENTITY_RULES[TMALL]['names'][0], aliases='保留人工值')])
        self.assertEqual(normalize_identity(catalog), catalog)

    def test_fixed_roster_keeps_38_rows_when_entries_missing(self):
        report = roster_review(dict(pois=[]))
        self.assertEqual(len(report['rows']), 38)
        self.assertEqual(len(set(ROSTER_IDS)), 38)
        self.assertEqual(report['summary']['missing_count'], 38)
        self.assertEqual(report['summary']['present_count'], 0)
        self.assertEqual(report['summary']['main_row_expected_count'], 13)

    def test_main_row_order_and_extra_cotti_not_counted_as_39th_roster_row(self):
        catalog = fixture()
        catalog['pois'].append(dict(id=COTTI, name='库迪咖啡（西北食堂西侧）'))
        report = roster_review(catalog)
        self.assertEqual(report['summary']['present_count'], 38)
        self.assertEqual(report['summary']['extra_count'], 1)
        self.assertEqual(report['summary']['main_row_present_count'], 13)
        main = [r for r in report['rows'] if r['group'] == 'snack-main']
        self.assertEqual([r['order'] for r in main], list(range(1, 14)))
        self.assertEqual(main[0]['roster_name'], '小果匠水果捞')
        self.assertEqual(main[-1]['roster_name'], '快客100')
        self.assertIsNone(report['extra_rows'][0]['order'])
        self.assertEqual(report['extra_rows'][0]['direction'], 'unknown')

    def test_reference_is_not_same_building_member_or_display_point(self):
        catalog = fixture()
        west = next(p for p in catalog['pois'] if p['id'] == WEST_BUILDING_IDS[0])
        west['map_reference'] = dict(x=1, y=2, crs='local EPSG:32650', building_id=499437130)
        report = roster_review(catalog)
        row = next(r for r in report['rows'] if r['id'] == west['id'])
        self.assertFalse(row['has_display_point'])
        self.assertEqual(row['location_mode'], 'reference_only')
        self.assertIsNone(row['building_id'])
        group = report['same_building_groups'][0]
        self.assertEqual(len(group['member_ids']), 5)
        self.assertNotIn(NORTHWEST_REFERENCE, group['member_ids'])
        self.assertIsNone(group['model_building_id'])

    def test_building_anchor_stays_display_only(self):
        catalog = fixture()
        poi = next(p for p in catalog['pois'] if p['id'] == 'laixifu')
        poi.update(building_id=499437078, display_anchor=dict(x=1, y=2, crs='local EPSG:32650'))
        original = copy.deepcopy(catalog)
        row = next(r for r in roster_review(catalog)['rows'] if r['id'] == 'laixifu')
        self.assertEqual(row['location_mode'], 'building_anchor')
        self.assertTrue(row['has_display_point'])
        self.assertFalse(row['can_measure_to_entrance'])
        self.assertEqual(catalog, original)
        self.assertIsNone(poi['location'])

    def test_nonfinite_wrong_crs_and_outside_points_are_not_displayable(self):
        catalog = fixture()
        for poi, point in zip(catalog['pois'], [dict(x=True, y=2), dict(x=float('nan'), y=2),
                                               dict(x=1, y=2, crs='EPSG:4326'), dict(x=453, y=2)]):
            poi['location'] = point
        rows = roster_review(catalog)['rows']
        self.assertFalse(any(r['has_display_point'] for r in rows[:4]))
        self.assertEqual(rows[3]['location_mode'], 'outside_model')

    def test_sequence_conflicts_report_source_disagreement_without_coordinate_changes(self):
        catalog = fixture()
        index = {p['id']: p for p in catalog['pois']}
        index[MIXUE]['location'] = dict(x=-259.4, y=-360.79)
        index[KFC]['location'] = dict(x=-259.4, y=-359.46)
        index[YOUGUOHUI]['location'] = dict(x=-354.73, y=-326.87)
        index[TMALL]['location'] = dict(x=359.73, y=-227.52)
        original = copy.deepcopy(catalog)
        conflicts = [i for i in roster_review(catalog)['issues'] if i['code'] == 'spatial_sequence_vs_location_conflict']
        self.assertEqual(len(conflicts), 2)
        mixue = next(i for i in conflicts if i['ids'][0] == MIXUE)
        self.assertEqual(mixue['northing_difference_m'], 1.33)
        self.assertEqual(mixue['review_state'], 'candidate')
        self.assertEqual(catalog, original)

    def test_possible_duplicate_not_merged_and_safe_report_excludes_private_fields(self):
        catalog = fixture()
        catalog['pois'].append(dict(id=LAIXIFU_CANDIDATE, name='来喜福炒酸奶鸡蛋仔'))
        result = normalize_identity(catalog)
        report = roster_review(catalog)
        self.assertEqual(len(result['pois']), 39)
        duplicate = next(i for i in report['issues'] if i['code'] == 'possible_same_as')
        self.assertEqual(duplicate['ids'], ['laixifu', LAIXIFU_CANDIDATE])
        raw = json.dumps(report, ensure_ascii=False)
        for private in ('PRIVATE-PHOTO', 'PRIVATE-PERSON', 'field_evidence', 'source_file'):
            self.assertNotIn(private, raw)


if __name__ == '__main__':
    unittest.main()
