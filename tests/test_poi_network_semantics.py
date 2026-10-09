"""Semantic network checks use invented records only, with no source IO."""
import copy
import json
import unittest

from backend.poi_semantics import build_semantics, RULE_VERSION


def entity(kind, ident, name, **values):
    row = dict(ref=dict(kind=kind, id=ident), name=name, data_mode='real', browseable=True)
    row.update(values)
    return row


def fixture():
    pois = [dict(id='coffee-a', name='瑞幸咖啡（甲楼店）', category='coffee', source='field_observation'),
            dict(id='coffee-b', name='瑞幸咖啡（乙楼店）', category='coffee', source='field_observation'),
            dict(id='food', name='测试餐厅', category='restaurant', source='field_observation')]
    shops = [dict(id='shop-food', poi_id='food', name='测试窗口', source='field_observation')]
    items = [dict(id='item-food', shop_id='shop-food', name='清真无花生素食饭', tags=['辣', '米饭'], source='field_observation')]
    entities = [entity('poi', p['id'], p['name'], category=p['category']) for p in pois]
    entities += [entity('outlet', 'shop-food', '测试窗口', poi_id='food'),
                 entity('item', 'item-food', items[0]['name'], poi_id='food')]
    return entities, dict(pois=pois, shops=shops, items=items)


class PoiNetworkSemanticsTests(unittest.TestCase):
    def test_source_not_mutated_and_output_deterministic(self):
        entities, catalog = fixture()
        original = copy.deepcopy((entities, catalog))
        first = build_semantics(entities, catalog)
        self.assertEqual((entities, catalog), original)
        self.assertEqual(first, build_semantics(list(reversed(entities)), catalog))
        for edge in first['edges']:
            required = {'type', 'subject', 'object', 'status', 'basis', 'limitations', 'rule_version'}
            self.assertTrue(required <= set(edge))
            self.assertTrue(set(edge) <= required | {'original_category', 'rule_origin'})
            self.assertEqual(edge['rule_version'], RULE_VERSION)
            self.assertIn(edge['status'], {'recorded', 'inferred'})
        for node in first['nodes']:
            self.assertTrue(node['concept'])
            self.assertEqual(node['data_mode'], 'real')
            self.assertTrue(node['browseable'])

    def test_two_branches_share_brand_not_identity_or_menus(self):
        entities, catalog = fixture()
        result = build_semantics(entities, catalog)
        brands = [edge for edge in result['edges'] if edge['type'] == 'of_brand']
        self.assertEqual(len(brands), 2)
        self.assertEqual({e['subject']['id'] for e in brands}, {'coffee-a', 'coffee-b'})
        self.assertEqual({e['object']['id'] for e in brands}, {'luckin'})
        self.assertTrue(all(e['status'] == 'inferred' for e in brands))
        self.assertNotIn('same_as', {e['type'] for e in result['edges']})
        self.assertEqual(len([n for n in result['nodes'] if n['ref'] == dict(kind='brand', id='luckin')]), 1)

    def test_categories_and_services_share_concepts_not_complete_graph(self):
        entities, catalog = fixture()
        result = build_semantics(entities, catalog)
        self.assertTrue(all(e['object']['kind'] in {'category', 'service', 'brand', 'trait'} for e in result['edges']))
        drinks = [e for e in result['edges'] if e['type'] == 'has_category' and e['object']['id'] == 'drinks']
        self.assertEqual(len(drinks), 2)
        self.assertTrue(all(e['status'] == 'recorded' for e in drinks))
        self.assertIn('beverages', {e['object']['id'] for e in result['edges'] if e['type'] == 'provides_service'})

    def test_simulated_inferred_and_archived_entities_excluded(self):
        for change in (dict(data_mode='simulated'), dict(data_mode='inferred'), dict(browseable=False), dict(is_simulated=True)):
            with self.subTest(change=change):
                entities, catalog = fixture()
                for e in entities:
                    e.update(change)
                self.assertEqual(build_semantics(entities, catalog), dict(nodes=[], edges=[], issues=[]))

    def test_simulated_source_or_ancestor_cannot_masquerade_as_real_entity(self):
        for table, field in (('items', 'source'), ('shops', 'content_origin'), ('pois', 'source')):
            with self.subTest(table=table, field=field):
                entities, catalog = fixture()
                target = catalog[table][-1]
                target[field] = 'simulated'
                result = build_semantics(entities, catalog)
                self.assertNotIn('item-food', {e['subject']['id'] for e in result['edges']})

    def test_explicit_item_tags_only_never_dietary_guesses_or_parent_inheritance(self):
        entities, catalog = fixture()
        result = build_semantics(entities, catalog)
        traits = [e for e in result['edges'] if e['type'] == 'has_trait']
        self.assertEqual({e['object']['id'] for e in traits}, {'spicy', 'rice'})
        self.assertTrue(all(e['subject'] == dict(kind='item', id='item-food') for e in traits))
        self.assertTrue(all(e['status'] == 'recorded' and e['limitations'] for e in traits))
        catalog['items'][0].pop('tags')
        self.assertFalse(any(e['type'] == 'has_trait' for e in build_semantics(entities, catalog)['edges']))

    def test_explicit_dietary_tag_is_record_not_safety_guarantee(self):
        entities, catalog = fixture()
        catalog['items'][0]['tags'] = ['清真', '无花生', '纯素']
        traits = [e for e in build_semantics(entities, catalog)['edges'] if e['type'] == 'has_trait']
        self.assertEqual({e['object']['id'] for e in traits}, {'halal', 'peanut-free', 'vegan'})
        self.assertTrue(all('不代表过敏原' in e['limitations'][0] for e in traits))

    def test_nonreal_tag_provenance_is_excluded_without_affecting_real_shop(self):
        for patch in (dict(tags_source='simulated'), dict(tags_origin='inferred'),
                      dict(field_evidence={'tags': {'source': 'generated'}})):
            with self.subTest(patch=patch):
                entities, catalog = fixture()
                catalog['items'][0].update(patch)
                result = build_semantics(entities, catalog)
                self.assertFalse(any(e['type'] == 'has_trait' for e in result['edges']))
                self.assertIn('shop-food', {e['subject']['id'] for e in result['edges']})
                self.assertIn('NONREAL_ITEM_TAGS_EXCLUDED', {i['code'] for i in result['issues']})

    def test_unknown_tags_and_private_data_not_exposed_as_concepts(self):
        entities, catalog = fixture()
        catalog['items'][0]['tags'] = ['C:/private/photo.jpg', '新造标签', '辣']
        catalog['items'][0]['field_evidence'] = {'actor': 'PRIVATE-PERSON'}
        result = build_semantics(entities, catalog)
        self.assertEqual({n['ref']['id'] for n in result['nodes'] if n['ref']['kind'] == 'trait'}, {'spicy'})
        self.assertEqual(next(i for i in result['issues'] if i['code'] == 'UNMAPPED_ITEM_TAGS')['count'], 2)
        self.assertNotIn('private', json.dumps(result))
        self.assertNotIn('PRIVATE-PERSON', json.dumps(result))

    def test_bad_tags_do_not_crash_or_become_characters(self):
        entities, catalog = fixture()
        catalog['items'][0]['tags'] = '清真'
        result = build_semantics(entities, catalog)
        self.assertFalse(any(e['type'] == 'has_trait' for e in result['edges']))
        self.assertIn('INVALID_ITEM_TAGS', {i['code'] for i in result['issues']})

    def test_exact_printing_study_and_retail_refinement_is_inferred(self):
        pois = [dict(id='print', name='雲起时图文广告', category='other'),
                dict(id='study', name='教八楼', category='building'),
                dict(id='shop', name='学子超市', category='other')]
        entities = [entity('poi', p['id'], p['name']) for p in pois]
        result = build_semantics(entities, dict(pois=pois))
        for ident, service in (('print', 'printing'), ('study', 'study'), ('shop', 'shopping')):
            matches = [e for e in result['edges'] if e['subject']['id'] == ident and e['object'] == dict(kind='service', id=service)]
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0]['status'], 'inferred')
        self.assertIn('CATEGORY_NAME_RULE_DIFFERS', {i['code'] for i in result['issues']})

    def test_partial_words_never_trigger_brand_printing_or_study(self):
        pois = [dict(id='p'+str(i), name=name, category='other') for i, name in enumerate((
            '瑞幸咖啡旁的测试店', '复印社旁咖啡店', '不是图书馆', '图书馆南门', '学习用品餐厅',
            '品牌瑞幸咖啡介绍', '我想去教八楼', '自习室风味饭'))]
        entities = [entity('poi', p['id'], p['name']) for p in pois]
        result = build_semantics(entities, dict(pois=pois))
        self.assertFalse(any(e['type'] in {'of_brand', 'provides_service'} for e in result['edges']))

    def test_floor_collection_is_not_promoted_to_outlet(self):
        entities = [entity('collection', 'collection', '整层菜单'), entity('outlet', 'collection', '整层菜单')]
        data = dict(pois=[dict(id='p', name='食堂', category='canteen')],
                    shops=[dict(id='collection', poi_id='p', name='整层菜单', entity_type='floor_menu_collection')])
        result = build_semantics(entities, data)
        self.assertEqual(result['nodes'], [])
        self.assertEqual(result['edges'], [])
        self.assertIn('COLLECTION_IS_NOT_OUTLET', {i['code'] for i in result['issues']})

    def test_confirmed_derived_outlet_can_use_its_recorded_menu_category(self):
        e = entity('outlet', 'outlet-xinlequn-3-001', '广式现炒／现炒盖饭', category='food',
                   poi_id='canteen-3', source_collection_id='menu-collection-xinlequn-3', identity_status='confirmed')
        data = dict(pois=[dict(id='canteen-3', name='食堂三层', category='canteen', source='published')],
                    shops=[dict(id='menu-collection-xinlequn-3', poi_id='canteen-3', name='三层集合', source='menu_photo', entity_type='floor_menu_collection')])
        result = build_semantics([e], data)
        self.assertEqual({edge['object']['id'] for edge in result['edges']}, {'food', 'dining'})
        self.assertTrue(all(edge['status'] == 'recorded' for edge in result['edges']))
        self.assertNotIn('same_as', {edge['type'] for edge in result['edges']})

    def test_explicit_gate_library_finance_service_mapping(self):
        pois = [dict(id=cat, name='测试'+cat, category=cat) for cat in ('gate', 'library', 'finance')]
        entities = [entity('poi', p['id'], p['name']) for p in pois]
        result = build_semantics(entities, dict(pois=pois))
        for service in ('campus-access', 'study', 'financial-services'):
            self.assertTrue(any(e['object'] == dict(kind='service', id=service) and e['status'] == 'recorded' for e in result['edges']))

    def test_official_library_building_and_inferred_teaching_building_use_different_evidence(self):
        entities = [entity('building', '267944894', '图书馆', function_tags=['library', 'study'],
                           content_origin='official_public_source', review_state='source_checked_identity_bound'),
                    entity('building', 'test-teaching', '教六楼', function_tags=['teaching_candidate'], content_origin='inferred'),
                    entity('building', 'unknown', '图书馆名字但未核实', function_tags=[], content_origin='model_inventory')]
        result = build_semantics(entities, {})
        self.assertEqual(len(result['edges']), 2)
        by_id = {edge['subject']['id']: edge for edge in result['edges']}
        self.assertEqual(by_id['267944894']['status'], 'recorded')
        self.assertEqual(by_id['267944894']['rule_origin'], 'official_function_tags')
        self.assertEqual(by_id['test-teaching']['status'], 'inferred')
        self.assertEqual(by_id['test-teaching']['rule_origin'], 'inferred_function_tags')
        self.assertTrue(all(e['object'] == dict(kind='service', id='study') for e in result['edges']))

    def test_brand_category_refinement_preserves_original_category_in_edge_and_source(self):
        pois = [dict(id='branch', name='瑞幸咖啡(德胜国际中心店)', category='restaurant', source='baidu_place_v2')]
        result = build_semantics([entity('poi', 'branch', pois[0]['name'])], dict(pois=pois))
        category = next(e for e in result['edges'] if e['type'] == 'has_category')
        self.assertEqual(category['object']['id'], 'drinks')
        self.assertEqual(category['original_category'], 'restaurant')
        self.assertEqual(category['rule_origin'], 'exact_name_rule')
        self.assertEqual(category['status'], 'inferred')
        self.assertEqual(pois[0]['category'], 'restaurant')
        self.assertTrue(any(e['object'] == dict(kind='service', id='beverages') for e in result['edges']))
        self.assertIn('CATEGORY_NAME_RULE_DIFFERS', {i['code'] for i in result['issues']})

    def test_unverified_or_nonreal_building_description_not_promoted_to_official_service(self):
        for patch in (dict(content_origin='generated'), dict(data_mode='simulated'),
                      dict(review_state='identity_mismatch'), dict(content_origin='model_inventory')):
            with self.subTest(patch=patch):
                e = entity('building', 'b', '图书馆', content_origin='official_public_source', function_tags=['study'])
                e.update(patch)
                self.assertEqual(build_semantics([e], {})['edges'], [])


if __name__ == '__main__':
    unittest.main()
