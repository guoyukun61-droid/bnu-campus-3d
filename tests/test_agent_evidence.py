"""Adversarial answer plans and typed query contracts; no live model/private data."""
import copy
import json
import unittest

from backend.agent.controller import AgentController
from backend.agent.evidence import EvidenceLedger
from backend.agent.tools import CampusTools
from backend.menu_relations import _PHOTO_HASHES


def tool_call(name, **arguments):
    return dict(role='assistant', content=None, tool_calls=[dict(
        id='test-'+name, type='function', function=dict(name=name, arguments=json.dumps(arguments)))])


def plan_for_last_evidence(messages):
    result = json.loads(next(m['content'] for m in reversed(messages) if m['role'] == 'tool'))
    ids = [r['id'] for r in result['answer_evidence'] if r['kind'] == 'fact'][:3]
    return dict(role='assistant', content=json.dumps(dict(style='summary', evidence_ids=ids, follow_up='none')))


class ScriptModel:
    configured = True

    def __init__(self, responses):
        self.responses, self.calls = responses, []

    def complete(self, messages, tools, deadline):
        self.calls.append(copy.deepcopy(messages))
        response = self.responses[min(len(self.calls)-1, len(self.responses)-1)]
        return (response(messages) if callable(response) else response), dict(prompt_tokens=1, completion_tokens=1)


def campus_tools():
    c = dict(pois=[dict(id='p0', name='测试楼层', source='field_observation', status='verified',
                        category='canteen', building_id='b0', floor='2')],
             shops=[dict(id='s0', name='甲窗口', poi_id='p0', source='field_observation', floor='2'),
                    dict(id='s1', name='乙窗口', poi_id='p0', source='field_observation', floor='2')],
             items=[dict(id='a', name='甲窗口面', shop_id='s0', source='menu_photo', price=10),
                    dict(id='b', name='乙窗口饭', shop_id='s1', source='menu_photo', price=12)],
             locations=[], walking_times=[])
    buildings = [dict(id='b0', name='测试楼', description='用于测试的建筑简介',
                      description_status='公开资料摘要', content_origin='official',
                      content_limitations=['该建筑简介没有证明内部商户正在营业。'],
                      source_links=[dict(url='https://example.org/building', title='测试公开来源')])]
    return CampusTools(c, buildings=buildings, areas=[])


class EvidencePlanTests(unittest.TestCase):
    def ledger(self):
        ledger = EvidenceLedger()
        ledger.ingest(dict(cards=[dict(type='food', id='item-1', poi_id='p0', outlet_id='s0',
                                      name='记录面条', price=12, source='menu_photo',
                                      unknown=['实时排队未知', '当前在售待确认'])]))
        return ledger

    def valid_plan(self, ledger, **patch):
        result = dict(style='summary', evidence_ids=[ledger.facts[0]['id']], follow_up='none')
        result.update(patch)
        return json.dumps(result)

    def test_valid_plan_selects_existing_facts_but_cannot_drop_unknowns(self):
        ledger = self.ledger()
        result = ledger.compose(self.valid_plan(ledger), '请查看记录。')
        self.assertEqual(result['answer_mode'], 'evidence_plan')
        self.assertEqual(result['used_evidence_ids'], [ledger.facts[0]['id']])
        self.assertIn('实时排队未知', result['answer'])
        self.assertIn('当前在售待确认', result['answer'])

    def test_forged_id_or_extra_fact_field_never_appears_in_answer(self):
        ledger = self.ledger()
        for plan in (self.valid_plan(ledger, evidence_ids=['伪造全部免费']),
                     self.valid_plan(ledger, answer='伪造全部免费'),
                     '伪造全部免费，保证准时到课',
                     self.valid_plan(ledger, evidence_ids=[])):
            with self.subTest(plan=plan):
                result = ledger.compose(plan, '请查看记录。')
                self.assertEqual(result['answer_mode'], 'evidence_fallback')
                self.assertNotIn('伪造', result['answer'])
                self.assertIn('实时排队未知', result['answer'])

    def test_invalid_style_and_follow_up_fail_closed_without_raising(self):
        ledger = self.ledger()
        for patch in ({'style': 'invent'}, {'style': []}, {'follow_up': 'pay'}, {'follow_up': {}}):
            with self.subTest(patch=patch):
                result = ledger.compose(self.valid_plan(ledger, **patch), '请查看记录。')
                self.assertEqual(result['answer_mode'], 'evidence_fallback')
                self.assertIn('实时排队未知', result['answer'])

    def test_large_plans_and_only_limitations_fall_back_safely(self):
        ledger = self.ledger()
        limitation = next(f['id'] for f in ledger.facts if f['kind'] == 'limitation')
        for plan in ('x'*6001, self.valid_plan(ledger, evidence_ids=[limitation]),
                     self.valid_plan(ledger, evidence_ids=[ledger.facts[0]['id']]*9)):
            result = ledger.compose(plan, '请查看记录。')
            self.assertEqual(result['answer_mode'], 'evidence_fallback')

    def test_duplicate_fact_selection_is_rendered_once(self):
        ledger = self.ledger()
        ident = ledger.facts[0]['id']
        result = ledger.compose(self.valid_plan(ledger, evidence_ids=[ident, ident]), '')
        self.assertEqual(result['used_evidence_ids'], [ident])
        self.assertEqual(result['answer'].count(ledger.facts[0]['text']), 1)

    def test_critical_unknown_after_fact_cap_is_still_preserved(self):
        ledger = EvidenceLedger()
        for n in range(ledger.MAX_FACTS):
            ledger.add('事实 '+str(n))
        ledger.add('饮食安全尚未核实。', kind='limitation')
        self.assertIn('饮食安全尚未核实', ledger.compose(None, '')['answer'])

    def test_clarification_cannot_be_replaced_by_model_plan(self):
        ledger = self.ledger()
        result = ledger.compose(self.valid_plan(ledger), '', clarification='请先提供预算。')
        self.assertEqual(result['answer'], '请先提供预算。')
        self.assertEqual(result['used_evidence_ids'], [])

    def test_menu_uses_its_own_window_unit_source_and_simulation_label(self):
        ledger = EvidenceLedger()
        ledger.ingest(dict(cards=[dict(type='place', id='p0', name='楼层', source='official_menu',
            menu=[dict(name='称重菜', price=8, specification='每100克', outlet_name='乙窗口',
                       outlet_id='s1', source='menu_photo', data_mode='simulated')])]))
        fact = next(f for f in ledger.facts if '称重菜' in f['text'])
        self.assertIn('【模拟菜单】乙窗口', fact['text'])
        self.assertIn('每100克', fact['text'])
        self.assertIn('当前在售待确认', fact['text'])
        self.assertEqual(fact['source'], 'menu_photo')
        self.assertEqual(fact['entity'], {'kind': 'outlet', 'id': 's1'})
        self.assertEqual(fact['data_mode'], 'simulated')


class TypedEntityEvidenceTests(unittest.TestCase):
    def test_public_building_urls_survive_while_private_fields_do_not(self):
        tools = campus_tools()
        tools._buildings[0].update(source_file='C:/private/photo.png', personal_notes='PRIVATE-NOTE')
        tools._buildings[0]['source_links'] += ['file:///private/photo.png', 'https://name:secret@example.org/']
        result = tools.execute('get_entity', {'kind': 'building', 'entity_id': 'b0'}, {})
        entity = result['entities'][0]
        self.assertEqual(entity['source_urls'], ['https://example.org/building'])
        self.assertNotIn('PRIVATE-NOTE', json.dumps(result))
        self.assertNotIn('C:/private', json.dumps(result))
        self.assertNotIn('secret@', json.dumps(result))

    def test_building_content_limitations_are_mandatory_answer_evidence(self):
        result = campus_tools().execute('get_entity', {'kind': 'building', 'entity_id': 'b0'}, {})
        ledger = EvidenceLedger()
        ledger.ingest(result)
        answer = ledger.compose(None, '')['answer']
        self.assertIn('该建筑简介没有证明内部商户正在营业', answer)

    def test_independent_window_menu_is_not_sibling_menu(self):
        tools = campus_tools()
        result = tools.execute('get_entity', {'kind': 'outlet', 'entity_id': 's0'}, {})
        self.assertEqual([i['id'] for i in result['cards'][0]['menu']], ['a'])
        self.assertEqual(result['cards'][0]['outlet_id'], 's0')
        self.assertEqual(result['entities'][0]['ref'], {'kind': 'outlet', 'id': 's0'})
        self.assertEqual(result['cards'][0]['hours'], '尚未录入')
        self.assertIn('当前在售', result['notice'])
        ledger = EvidenceLedger()
        ledger.ingest(result)
        self.assertNotIn('甲窗口，位置记录：甲窗口', ledger.compose(None, '')['answer'])

    def test_window_pagination_happens_after_membership_filter(self):
        tools = campus_tools()
        tools.catalog['items'] = [dict(id='other-'+str(n), name='其他菜', shop_id='s1', source='menu_photo', price=5)
                                  for n in range(65)] + [
            dict(id='own-'+str(n), name='本窗口菜', shop_id='s0', source='menu_photo', price=10)
            for n in range(62)]
        card = tools.execute('get_entity', {'kind': 'outlet', 'entity_id': 's0', 'offset': 60}, {})['cards'][0]
        self.assertEqual(card['menu_total'], 62)
        self.assertEqual([i['id'] for i in card['menu']], ['own-60', 'own-61'])

    def test_confirmed_derived_window_does_not_inherit_floor_hours(self):
        tools = campus_tools()
        c = tools.catalog
        c['pois'][0].update(id='canteen-3', floor='3', opening_hours=[['06:00', '22:00']])
        c['shops'] = [dict(id='menu-collection-xinlequn-3', name='三层集合', poi_id='canteen-3',
                           floor='3', source='menu_photo', entity_type='floor_menu_collection',
                           independent_merchant=False, opening_hours=[['06:00', '22:00']])]
        c['items'] = [dict(id='first', name='甲饭', shop_id=c['shops'][0]['id'], price=10,
                           source='menu_photo', source_photo_sha256=_PHOTO_HASHES['458']),
                      dict(id='second', name='乙饭', shop_id=c['shops'][0]['id'], price=11,
                           source='menu_photo', source_photo_sha256=_PHOTO_HASHES['459'])]
        result = tools.execute('get_entity', {'kind': 'outlet', 'entity_id': 'outlet-xinlequn-3-001'}, {})
        self.assertEqual([i['id'] for i in result['cards'][0]['menu']], ['first'])
        self.assertEqual(result['cards'][0]['hours'], '尚未录入')
        self.assertIsNone(result['entities'][0]['opening_hours'])

    def test_real_window_details_exclude_simulated_sibling_items(self):
        tools = campus_tools()
        tools.catalog['items'] += [dict(id='sim', name='模拟菜不应出现', shop_id='s0', source='simulated', price=1),
                                   dict(id='infer', name='推测菜不应出现', shop_id='s0', source='inferred', price=1)]
        result = tools.execute('get_entity', {'kind': 'outlet', 'entity_id': 's0'}, {})
        self.assertEqual([i['id'] for i in result['cards'][0]['menu']], ['a'])


class ScopedRecommendationTests(unittest.TestCase):
    def tools(self):
        tools = campus_tools()
        tools._buildings.append(dict(id='b1', name='其他楼'))
        for n in range(4):
            ident = 'outside-'+str(n)
            tools.catalog['pois'].append(dict(id=ident, name='其他楼餐厅'+str(n), category='canteen',
                source='field_observation', status='verified', building_id='b1'))
            tools.catalog['shops'].append(dict(id='s-'+ident, poi_id=ident, name='其他窗口', source='field_observation'))
            tools.catalog['items'].append(dict(id='i-'+ident, shop_id='s-'+ident, name='其他楼便宜面', price=1, source='menu_photo'))
        return tools

    def test_building_scope_filters_before_ranking_and_does_not_persist_conditions(self):
        result = self.tools().execute('recommend_food', {'budget': 20, 'within': {'kind': 'building', 'id': 'b0'}}, {})
        self.assertEqual({c['poi_id'] for c in result['cards']}, {'p0'})
        self.assertEqual(result['scope']['id'], 'b0')
        self.assertEqual(result['conditions'], {'budget': 20})
        self.assertIn('不自动扩大', result['notice'])

    def test_empty_scope_candidates_never_expand_to_other_buildings(self):
        result = self.tools().execute('recommend_food', {'budget': 2, 'within': {'kind': 'building', 'id': 'b0'}}, {})
        self.assertEqual(result['cards'], [])
        self.assertEqual(result['scope']['id'], 'b0')
        self.assertEqual(result['conditions'], {'budget': 2})

    def test_reference_area_is_not_same_building_recommendation_scope(self):
        tools = self.tools()
        for p in tools.catalog['pois'][1:]:
            p.pop('building_id')
            p['map_reference'] = dict(building_id='b0', precision='reference_only')
        result = tools.execute('recommend_food', {'budget': 20, 'within': {'kind': 'building', 'id': 'b0'}}, {})
        self.assertEqual({c['poi_id'] for c in result['cards']}, {'p0'})

    def test_forged_scope_facts_and_wrong_types_are_rejected(self):
        for within in ({'kind': 'building', 'id': 'b0', 'name': '假楼'}, {'kind': 'outlet', 'id': 's0'},
                       {'kind': 'building', 'id': 'missing'}, {'kind': 'building', 'id': 'b0', 'x': 1}):
            with self.subTest(within=within), self.assertRaises(ValueError):
                self.tools().execute('recommend_food', {'budget': 20, 'within': within}, {})


class ControllerEvidenceTests(unittest.TestCase):
    def run_agent(self, responses, message='测试查询'):
        model, events = ScriptModel(responses), []
        result = AgentController(model, campus_tools()).run({'message': message}, events.append)
        return result, model, events

    def test_complete_non_poi_relation_bundle_reaches_final_event(self):
        result, model, events = self.run_agent([
            tool_call('get_related_places', kind='poi', entity_id='p0'), plan_for_last_evidence])
        self.assertTrue(result['relations'])
        relation = result['relations'][0]
        self.assertTrue(any(row['ref']['kind'] != 'poi' for row in relation['items']))
        self.assertTrue(all('path' in row for row in relation['items']))
        self.assertEqual(events[-1]['data']['relations'], result['relations'])
        self.assertEqual(result['contract_version'], 'agent-answer.v2')
        self.assertIn('不是导航', result['answer'])
        self.assertTrue(any(action['entity']['kind'] == 'building' for action in result['map_actions']))
        self.assertIn('answer_evidence', json.loads(next(m['content'] for m in model.calls[1] if m['role'] == 'tool')))

    def test_two_windows_on_one_floor_keep_both_result_menus(self):
        result, _, _ = self.run_agent([
            tool_call('get_entity', kind='outlet', entity_id='s0'),
            tool_call('get_entity', kind='outlet', entity_id='s1'), plan_for_last_evidence],
            message='比较甲乙两个窗口')
        self.assertEqual({card.get('outlet_id') for card in result['cards']}, {'s0', 's1'})
        self.assertEqual({item['id'] for card in result['cards'] for item in card.get('menu', [])}, {'a', 'b'})
        self.assertEqual({e['ref']['id'] for e in result['entities']}, {'s0', 's1'})

    def test_free_prose_never_becomes_a_campus_fact(self):
        result, _, _ = self.run_agent([tool_call('get_entity', kind='outlet', entity_id='s0'),
                                      dict(content='这家全部免费，保证不迟到')])
        self.assertNotIn('全部免费', result['answer'])
        self.assertNotIn('保证不迟到', result['answer'])
        self.assertEqual(result['answer_mode'], 'evidence_fallback')
        self.assertTrue(result['evidence'])

    def test_revised_recommendation_cannot_select_a_superseded_candidate(self):
        captured = {}

        def narrow_budget(messages):
            result = json.loads(next(m['content'] for m in reversed(messages) if m['role'] == 'tool'))
            captured['old_id'] = next(f['id'] for f in result['answer_evidence']
                                      if '乙窗口饭的记录价格' in f['text'])
            return tool_call('recommend_food', budget=10)

        def stale_plan(messages):
            return dict(content=json.dumps(dict(style='summary', evidence_ids=[captured['old_id']], follow_up='none')))

        result, _, _ = self.run_agent([tool_call('recommend_food', budget=20), narrow_budget, stale_plan])
        self.assertEqual(result['conditions']['budget'], 10)
        self.assertTrue(all(card['price'] <= 10 for card in result['cards']))
        self.assertNotIn(captured['old_id'], result['used_evidence_ids'])
        self.assertNotIn('乙窗口饭的记录价格为12元', result['answer'])


if __name__ == '__main__':
    unittest.main()
