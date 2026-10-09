"""Isolated network tool checks: no live model, account store or source writes."""
import copy
import json
import unittest
from unittest.mock import patch

from backend.agent.controller import AgentController
from backend.agent.tools import CampusTools, TOOLS, bounded_network
from backend.life_relations import build_relation_snapshot


def catalogue(count=4):
    return dict(pois=[dict(id=f'p{i}',name=f'测试餐厅{i}',category='restaurant',
        source='field_observation',status='verified',zone='campus',building_id=1)
        for i in range(count)],shops=[],items=[],locations=[],walking_times=[])


BUILDINGS=[dict(id=1,name='测试楼',function_tags=['dining'])]


def tool(c=None):
    return CampusTools(c if c is not None else catalogue(),buildings=BUILDINGS,areas=[])


def execute(t,**args):
    return t.execute('get_related_places',dict(entity_id='p0',**args),{})


class FakeModel:
    configured=True
    def __init__(self):self.calls=[]
    def complete(self,messages,tools,deadline):
        self.calls.append(copy.deepcopy(messages))
        if len(self.calls)==1:
            return dict(role='assistant',content=None,tool_calls=[dict(id='network-test',
                type='function',function=dict(name='get_related_places',
                arguments=json.dumps({'entity_id':'p0'})))]),{}
        return dict(role='assistant',content='错误的模型自由发挥：保证现在营业且步行可达'),{}


class AgentNetworkTests(unittest.TestCase):
    def test_schema_is_read_only_and_bounded(self):
        schema=next(s['function']['parameters'] for s in TOOLS
                    if s['function']['name']=='get_related_places')
        self.assertEqual(schema['required'],['entity_id'])
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(schema['properties']['limit']['maximum'],12)
        self.assertEqual(set(schema['properties']['kind']['enum']),{'poi','building','outlet'})
        self.assertNotIn('include_simulated',schema['properties'])

    def test_rejects_bad_parameters_before_catalogue_read(self):
        bad=[{}, {'entity_id':''},{'entity_id':7},{'entity_id':'x'*201},
             {'entity_id':'p0','kind':'service'},{'entity_id':'p0','kind':[]},
             {'entity_id':'p0','mode':'navigate'},{'entity_id':'p0','mode':[]},
             {'entity_id':'p0','limit':True},{'entity_id':'p0','limit':0},
             {'entity_id':'p0','limit':13},{'entity_id':'p0','limit':2.5},
             {'entity_id':'p0','unknown':True},{'entity_id':'\n'},
             {'entity_id':'   '}]
        for args in bad:
            with self.subTest(args=args),patch.object(CampusTools,'snapshot',side_effect=AssertionError('read')):
                with self.assertRaises(ValueError):tool().execute('get_related_places',args,{})

    def test_frozen_turn_captures_catalogue_and_context_before_first_query(self):
        source=catalogue();buildings=copy.deepcopy(BUILDINGS)
        with patch('backend.agent.tools.CatalogAdapter.snapshot',return_value=source) as loader,\
             patch('backend.agent.tools.network_context',return_value=(buildings,[])) as context,\
             patch('backend.life_relations.RelationRepository.load',side_effect=AssertionError('live reread')):
            frozen=CampusTools().frozen()
            source['pois'][1]['name']='后发布的新名称'
            buildings[0]['name']='后发布的新楼名'
            first=execute(frozen,mode='same_type')
            second=execute(frozen,mode='neighbors')
            self.assertEqual(loader.call_count,1);self.assertEqual(context.call_count,1)
        payload=json.dumps([first,second],ensure_ascii=False)
        self.assertIn('测试餐厅1',payload);self.assertIn('测试楼',payload)
        self.assertNotIn('后发布',payload)
        self.assertEqual(first['related_places']['snapshot_id'],second['related_places']['snapshot_id'])

    def test_relation_projection_is_built_once_per_frozen_turn(self):
        frozen=tool().frozen()
        with patch('backend.life_relations.build_relation_snapshot',wraps=build_relation_snapshot) as build:
            execute(frozen);execute(frozen,mode='chain')
            self.assertEqual(build.call_count,1)

    def test_next_turn_can_observe_new_catalogue(self):
        source=catalogue()
        with patch('backend.agent.tools.CatalogAdapter.snapshot',return_value=source),\
             patch('backend.agent.tools.network_context',return_value=(BUILDINGS,[])):
            parent=CampusTools();first=parent.frozen()
            source['pois'][1]['name']='第二轮新名称';second=parent.frozen()
            a=execute(first,mode='same_type')['related_places']
            b=execute(second,mode='same_type')['related_places']
        self.assertNotEqual(a['snapshot_id'],b['snapshot_id'])
        self.assertNotIn('第二轮新名称',json.dumps(a,ensure_ascii=False))
        self.assertIn('第二轮新名称',json.dumps(b,ensure_ascii=False))

    def test_same_type_returns_at_most_twelve_real_places(self):
        c=catalogue(22);c['pois'][1]['source']='simulated'
        c['pois'][2]['content_origin']='inferred'
        c['pois'][3]['status']='historical'
        c['pois'][4]['status']='closed'
        t=tool(c).frozen()
        result=execute(t,mode='same_type',limit=12)
        related=result['related_places'];ids={i['ref']['id'] for i in related['items']}
        self.assertEqual(len(related['items']),12);self.assertEqual(len(result['cards']),12)
        self.assertTrue(related['truncated']);self.assertFalse(ids & {'p1','p2','p3','p4'})
        self.assertTrue(all(i['data_mode']=='real' for i in related['items']))
        self.assertNotIn('conditions',result)

    def test_missing_and_simulated_anchor_not_queryable_even_in_demo_mode(self):
        c=catalogue();c['pois'][0]['source']='simulated'
        for ident in ('p0','missing'):
            with self.subTest(ident=ident),self.assertRaises(KeyError):
                tool(c).execute('get_related_places',{'entity_id':ident},{},mode='demo')

    def test_private_source_fields_do_not_reach_model_dto(self):
        c=catalogue()
        for p in c['pois']:
            p.update(field_evidence={'secret':'PRIVATE-AUDIT-MARKER'},
                     source_file='C:/private/PRIVATE-PHOTO-MARKER.png',
                     personal_notes='PRIVATE-NOTE-MARKER')
        result=execute(tool(c),mode='same_type')
        text=json.dumps(result,ensure_ascii=False)
        for token in ('PRIVATE-AUDIT','PRIVATE-PHOTO','PRIVATE-NOTE','field_evidence','source_file','personal_notes'):
            self.assertNotIn(token,text)
        self.assertIn('basis',text);self.assertIn('limitations',text)
        self.assertIn('同品牌',result['notice']);self.assertIn('不是导航',result['notice'])

    def test_chain_is_short_evidence_not_route(self):
        result=execute(tool(),mode='chain',limit=12)['related_places']
        self.assertTrue(result['items'])
        for row in result['items']:
            path=row['path']
            self.assertTrue(2<=path['hop_count']<=3)
            self.assertFalse(path['is_route'])
            self.assertEqual(len(path['nodes']),len(path['edges'])+1)

    def test_rejects_overlong_or_forged_route_path_without_silent_truncation(self):
        for changes in ({'is_route':True},{'hop_count':4,'edges':[{}]*4,'nodes':[{}]*5},
                        {'nodes':[{}]}):
            path=dict(is_route=False,hop_count=2,edges=[{},{}],nodes=[{},{},{}]);path.update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                bounded_network({'mode':'chain','items':[{'path':path}]},12)

    def test_building_and_outlet_queries_use_typed_ids(self):
        c=catalogue();c['shops']=[dict(id='s0',poi_id='p0',name='测试窗口',source='field_observation')]
        t=tool(c)
        for kind,ident in (('building','1'),('outlet','s0')):
            r=t.execute('get_related_places',{'kind':kind,'entity_id':ident},{})
            self.assertEqual(r['related_places']['anchor']['ref'],{'kind':kind,'id':ident})
            self.assertTrue(all(card['id'].startswith('p') for card in r['cards']))

    def test_non_poi_evidence_is_not_misreported_as_no_results(self):
        model=FakeModel();events=[]
        result=AgentController(model,tool(catalogue(1))).run({'message':'这个地方有哪些关系？'},events.append)
        self.assertEqual(result['cards'],[])
        self.assertIn('已整理相关地点与关系',result['answer'])
        self.assertIn('测试楼',result['answer']);self.assertIn('不是导航',result['answer'])
        self.assertNotIn('没有找到符合',result['answer'])
        self.assertNotIn('错误的模型自由发挥',result['answer'])
        self.assertEqual(result['conditions'],{})
        self.assertNotIn('related_places',result)  # Existing client state contract unchanged.
        tool_message=next(m for m in model.calls[1] if m['role']=='tool')
        self.assertIn('related_places',json.loads(tool_message['content']))
        self.assertIn('探索地点关系与依据',[e.get('text') for e in events])


if __name__=='__main__':unittest.main()
