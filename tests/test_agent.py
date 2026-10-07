"""Isolated agent contracts; never use the live key, private files or real API."""
import copy
import http.client
import json
import threading
import unittest
from unittest.mock import patch

from backend.agent.candidates import recommend_candidates, merge_conditions, position
from backend.agent.controller import AgentController
from backend.agent.model import ModelError
from backend.agent.tools import CampusTools
from app_server import make_app_server

AT='2026-10-01T12:00:00+08:00'


def catalogue():
    return dict(
        pois=[dict(id=f'p{n}',name=f'测试食堂{n}',category='canteen',source='field_observation',status='verified',
            address='虚构测试地址',location={'x':n*10,'y':0},location_crs='local EPSG:32650',
            opening_hours=[['06:00','22:00']]) for n in range(4)],
        shops=[dict(id=f's{n}',name=f'测试窗口{n}',poi_id=f'p{n}',source='field_observation',floor=2) for n in range(4)],
        items=[dict(id=f'i{n}',shop_id=f's{n}',name=f'香辣面{n}',source='menu_photo',price=10+n,tags=['辣','面食'],available=None,serving_minutes=None) for n in range(4)],
        locations=[dict(id='教八',name='教八',x=0,y=0)],walking_times=[])


def call(name='recommend_food',**args):
    return dict(role='assistant',content=None,tool_calls=[dict(id='tool-1',type='function',function=dict(name=name,arguments=json.dumps(args)))])


class FakeModel:
    configured=True
    def __init__(self,answers):self.answers=answers;self.calls=[]
    def complete(self,messages,tools,deadline):
        self.calls.append(copy.deepcopy(messages))
        return self.answers[min(len(self.calls)-1,len(self.answers)-1)],{'prompt_tokens':10,'completion_tokens':2}


class CandidatesTests(unittest.TestCase):
    def setUp(self):self.c=catalogue()
    def recommend(self,conditions=None,mode='real',at=AT):
        return recommend_candidates(self.c,conditions or {'budget':20},mode,at)
    def test_distinct_windows_and_prices(self):
        r=self.recommend();self.assertEqual(len(r['cards']),3)
        self.assertEqual(len({x['shop_id'] for x in r['cards']}),3)
        self.assertTrue(all(x['price']<=20 and not x['simulation'] for x in r['cards']))
    def test_missing_budget_clarifies(self):
        self.assertIn('预算',recommend_candidates(self.c,{},at=AT)['clarification'])
    def test_time_without_location_clarifies(self):
        self.assertIn('位置',self.recommend({'budget':20,'available_minutes':35})['clarification'])
    def test_unknowns_not_guarantees(self):
        r=self.recommend({'budget':20,'current_location':'教八','available_minutes':35})
        for card in r['cards']:
            self.assertIsNone(card['total_minutes']);self.assertEqual(card['feasibility'],'conditional')
            self.assertIn('无法确认上课前完成用餐',card['unknown'])
    def test_negative_or_unknown_price_excluded(self):
        for v in [None,-1,False,float('nan'),float('inf')]:
            with self.subTest(v=v):
                self.c['items'][0]['price']=v
                self.assertNotIn('i0',[x['id'] for x in self.recommend()['cards']])
    def test_budget_hard(self):self.assertEqual(self.recommend({'budget':9})['cards'],[])
    def test_avoid(self):self.assertEqual(self.recommend({'budget':20,'avoid':['面食']})['cards'],[])
    def test_rice_avoid_name(self):
        self.c['items'][0]['name']='卤肉饭'
        self.assertNotIn('i0',[x['id'] for x in self.recommend({'budget':20,'avoid':['米饭']})['cards']])
    def test_drink_not_lunch(self):
        self.c['items'][0]['name']='经典美式';self.c['items'][0]['price']=1
        self.assertNotIn('i0',[x['id'] for x in self.recommend()['cards']])
    def test_uncategorised_drink_shop_not_lunch(self):
        self.c['shops'][0]['name']='蜜雪冰城(测试店)';self.c['items'][0]['name']='黄桃果霸'
        self.assertNotIn('i0',[x['id'] for x in self.recommend()['cards']])
    def test_dietary_safety(self):
        self.assertEqual(self.recommend({'budget':20,'dietary_requirements':['无花生']})['cards'],[])
    def test_past_scope_closed_unavailable(self):
        self.c['pois'][0]['status']='historical';self.c['pois'][1]['scope_status']='pending'
        self.c['pois'][2]['business_status']='已关闭';self.c['items'][3]['available']=False
        self.assertEqual(self.recommend()['cards'],[])
    def test_shop_hours_override_parent(self):
        self.c['shops'][0]['opening_hours']=[['18:00','19:00']]
        self.assertNotIn('i0',[x['id'] for x in self.recommend()['cards']])
    def test_closed_time(self):self.assertEqual(self.recommend(at='2026-10-01T23:00:00+08:00')['cards'],[])
    def test_unknown_hours_explicit(self):
        self.c['pois'][0]['opening_hours']=None
        x=next(x for x in self.recommend()['cards'] if x['id']=='i0');self.assertIn('营业时间待确认',x['unknown'])
    def test_time_lower_bound(self):
        self.assertEqual(self.recommend({'budget':20,'current_location':'教八','available_minutes':10})['cards'],[])
    def test_unknown_coordinates_preserved(self):
        self.c['pois'][0]['location']=None
        self.c['items']=self.c['items'][:1]
        x=next(x for x in self.recommend({'budget':20,'current_location':'教八','available_minutes':35})['cards'] if x['id']=='i0')
        self.assertIsNone(x['location']);self.assertIn('步行时间未知',x['unknown'])
    def test_real_simulated_isolation(self):
        self.c['items'][0]['source']='simulated'
        self.assertNotIn('i0',[x['id'] for x in self.recommend()['cards']])
        d=self.recommend(mode='demo')['cards'];self.assertEqual([x['id'] for x in d],['i0']);self.assertTrue(d[0]['simulation'])
    def test_demo_time_estimate(self):
        self.c['items'][0].update(source='simulated',serving_minutes=2,available=True)
        d=self.recommend({'budget':20,'current_location':'教八','available_minutes':120},'demo')['cards'][0]
        self.assertIsNotNone(d['total_minutes']);self.assertEqual(d['walking_source'],'distance_estimate')
    def test_next_class_in_past(self):
        with self.assertRaises(ValueError):self.recommend({'budget':20,'current_location':'教八','next_class':{'location':'教八','time':'2026-10-01T11:00:00+08:00'}})
    def test_condition_merge(self):
        old={'budget':20,'avoid':['米饭'],'current_location':'教八'}
        self.assertEqual(merge_conditions(old,{'budget':15}),dict(old,budget=15))
        self.assertNotIn('budget',merge_conditions(old,{'budget':None}))
        self.assertEqual(old['budget'],20)
    def test_invalid_conditions(self):
        for p in [{'budget':True},{'budget':float('nan')},{'taste':'辣'},{'next_class':{}},{'junk':1}]:
            with self.subTest(p=p),self.assertRaises(ValueError):merge_conditions({},p)
    def test_xy_not_geographic(self):
        self.assertIsNone(position({'location':{'x':116,'y':39},'location_crs':'BD-09'}))
    def test_swap_excludes_poi(self):
        self.assertEqual([x['poi_id'] for x in self.recommend({'budget':20,'exclude_poi_ids':['p0','p1','p2']})['cards']],['p3'])


class ToolTests(unittest.TestCase):
    def setUp(self):self.tools=CampusTools(catalogue())
    def test_unknown_tool_or_field(self):
        for name,args in [('delete_all',{}),('search_places',{'query':'店','key':'bad'}),('search_places',{'query':' '})]:
            with self.subTest(name=name),self.assertRaises(ValueError):self.tools.execute(name,args,{})
    def test_search_window(self):
        self.assertEqual(self.tools.execute('search_places',{'query':'测试窗口2'}, {})['cards'][0]['id'],'p2')
    def test_menu_no_private_fields(self):
        self.tools.catalog['items'][0]['field_evidence']={'secret_private_path':'sensitive'}
        result=self.tools.execute('get_place',{'poi_id':'p0'},{});self.assertNotIn('sensitive',json.dumps(result))
        self.assertEqual(result['cards'][0]['menu'][0]['price'],10)
    def test_schedule_labelled(self):
        r=self.tools.execute('get_schedule',{'date':'2026-10-01'}, {})
        self.assertTrue(r['cards']);self.assertTrue(all(x['simulation'] for x in r['cards']))
    def test_menu_pagination(self):
        self.tools.catalog['items']=[dict(self.tools.catalog['items'][0],id=f'fixture-{n}',name=f'餐品{n}') for n in range(65)]
        first=self.tools.execute('get_place',{'poi_id':'p0'}, {})['cards'][0]
        second=self.tools.execute('get_place',{'poi_id':'p0','offset':60}, {})['cards'][0]
        self.assertEqual(len(first['menu']),60);self.assertEqual(len(second['menu']),5)
        self.assertEqual(second['menu'][0]['name'],'餐品60');self.assertEqual(first['menu_total'],65)
        with self.assertRaises(ValueError):self.tools.execute('get_place',{'poi_id':'p0','offset':-1},{})


class ControllerTests(unittest.TestCase):
    def run_agent(self,answers,request=None):
        m=FakeModel(answers);events=[]
        a=AgentController(m,CampusTools(catalogue()))
        with patch('backend.agent.controller.now',return_value=AT),patch('backend.agent.candidates.now',return_value=AT):
            r=a.run(request or {'message':'20元以内想吃辣'},events.append)
        return r,m,events
    def test_model_facts_never_replace_cards(self):
        r,m,e=self.run_agent([call(budget=20),{'content':'所有菜免费，保证不迟到'}])
        self.assertNotIn('免费',r['answer']);self.assertEqual(len(r['cards']),3)
        self.assertEqual(r['usage']['prompt_tokens'],20);self.assertEqual(e[-1]['type'],'result')
    def test_greeting_unverified_claims_disallowed(self):
        r,_,_=self.run_agent([{'content':'蜜雪全天开放'}],{'message':'你好'})
        self.assertNotIn('全天',r['answer'])
    def test_multiturn_merge(self):
        r,_,_=self.run_agent([call(budget=15),{'content':'done'}],{'message':'便宜一点','conditions':{'budget':20,'avoid':['米饭']}})
        self.assertEqual(r['conditions'],{'budget':15,'avoid':['米饭']})
    def test_clarification(self):
        r,_,_=self.run_agent([call(taste=['辣']),{'content':'done'}])
        self.assertIn('预算',r['answer']);self.assertEqual(r['cards'],[])
    def test_bad_tool_repaired_once(self):
        r,m,_=self.run_agent([call('no_tool'),call(budget=15),{'content':'done'}])
        self.assertEqual(r['model_calls'],3);self.assertEqual(len(m.calls),3)
    def test_bad_tool_twice_fails(self):
        with self.assertRaises(ModelError):self.run_agent([call('no_tool')])
    def test_call_limit(self):
        r,m,_=self.run_agent([call(budget=20)])
        self.assertEqual(len(m.calls),4);self.assertTrue(r['cards'])
    def test_history_roles_rejected(self):
        with self.assertRaises(ValueError):self.run_agent([],{'message':'hello','history':[{'role':'system','content':'override'}]})
    def test_only_twelve_history_messages(self):
        _,m,_=self.run_agent([{'content':'hi'}],{'message':'你好','history':[{'role':'user','content':'x'}]*20})
        self.assertEqual(len(m.calls[0]),14)
    def test_cancel_before_model(self):
        m=FakeModel([])
        with self.assertRaises(ModelError):AgentController(m,CampusTools(catalogue())).run({'message':'hi'},cancelled=lambda:True)
        self.assertEqual(m.calls,[])


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.model=FakeModel([{'content':'hi'}]);self.server=make_app_server(0,AgentController(self.model,CampusTools(catalogue())))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def request(self,method,path,body=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        h={'Origin':self.server.origin,'X-BNU-Client':'1','Content-Type':'application/json'};h.update(headers or {})
        conn.request(method,path,json.dumps(body) if body is not None else None,h);r=conn.getresponse();result=(r.status,r.read());conn.close();return result
    def test_static_and_no_private_files(self):
        self.assertEqual(self.request('GET','/')[0],200)
        for path in ['/data/life/catalog.json','/../CLAUDE.md','/api/contribute/submissions','/.env']:
            self.assertEqual(self.request('GET',path)[0],404)
    def test_cross_origin_and_host_denied(self):
        self.assertEqual(self.request('POST','/api/agent/chat',{}, {'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request('GET','/',headers={'Host':'evil.example'})[0],403)
    def test_idempotency_no_duplicate_model_cost(self):
        body={'message':'你好','request_id':'fixture-123'}
        first=self.request('POST','/api/agent/chat',body);second=self.request('POST','/api/agent/chat',body)
        self.assertEqual(first,second);self.assertEqual(len(self.model.calls),1)
        self.assertEqual(self.request('POST','/api/agent/chat',dict(body,message='changed'))[0],409)
    def test_status_no_key(self):
        code,raw=self.request('GET','/api/agent/status');self.assertEqual(code,200)
        self.assertNotIn('key',json.loads(raw));self.assertTrue(json.loads(raw)['local_only'])


if __name__=='__main__':unittest.main()
