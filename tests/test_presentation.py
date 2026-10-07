"""No network or live submissions: public contract, privacy, recovery and audit."""
import copy
import http.client
import json
import struct
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
from backend.agent.presentation import public_address, category_info, public_hours_notes
from backend.agent.public_model import public_glb, strip_extras
from backend.agent.tools import CampusTools
from backend.agent.candidates import recommend_candidates
from backend.agent.model import DeepSeekModel, ModelError
from backend.agent.controller import AgentController
from backend.building_audit import building_audit
from backend.storage import ROOT, write
from app_server import make_app_server
from contribution_server import make_server
from tests.test_agent import catalogue, FakeModel, AT


class PresentationTests(unittest.TestCase):
    def test_category_capabilities(self):
        for category,expected,items in [('sports','sports',False),('gate','campus',False),('service','services',False),('retail','retail',True),('coffee','drinks',True),('canteen','food',True),('unknown','other',False)]:
            with self.subTest(category=category):
                result=category_info({'category':category})
                self.assertEqual(result['display_category'],expected)
                self.assertEqual(result['capabilities']['items'],items)

    def test_clean_address_preserves_source(self):
        c=catalogue();c['pois'][0]['address']='海淀区新街口外大街19号；BD-09 转换 EPSG:32650；轮廓匹配待核'
        before=copy.deepcopy(c)
        result=CampusTools(c).directory()['pois'][0]
        self.assertEqual(result['address'],'海淀区新街口外大街19号')
        self.assertEqual(c,before)
        self.assertEqual(public_address('轮廓包含点，楼高未核实'),'')
        self.assertEqual(public_address('百度地址：立身路19号。尚未可靠关联建筑；独立点位，不吸附最近楼；依据用户百度截图与GF2区域对应'),'立身路19号')

    def test_non_food_has_no_menu(self):
        c=catalogue();c['pois'][0]['category']='sports'
        result=CampusTools(c).execute('get_place',{'poi_id':'p0'}, {})
        card=result['cards'][0]
        self.assertNotIn('menu',card)
        self.assertEqual(card['hours_label'],'开放时间')
        self.assertNotIn('菜单',result['notice'])

    def test_hours_conditions_preserved_but_audit_prose_removed(self):
        self.assertEqual(public_hours_notes('用户补充确认：沿用原ID；休息日08:00开始营业'),'休息日08:00开始营业')

    def test_retail_and_drinks(self):
        for category,label in [('retail','商品'),('drink','饮品')]:
            c=catalogue();c['pois'][0]['category']=category
            card=CampusTools(c).execute('get_place',{'poi_id':'p0'}, {})['cards'][0]
            self.assertEqual(card['collection_label'],label)
            self.assertEqual(card['menu_total'],1)

    def test_recommendation_also_sanitized(self):
        c=catalogue();c['pois'][0]['address']='EPSG:32650 private-local-note'
        cards=recommend_candidates(c,{'budget':20},at=AT)['cards']
        self.assertTrue(cards)
        self.assertNotIn('private-local-note',json.dumps(cards))

    def test_non_restaurant_never_becomes_meal(self):
        c=catalogue()
        for p in c['pois']:p['category']='sports'
        self.assertEqual(recommend_candidates(c,{'budget':20},at=AT)['cards'],[])

    def test_sour_plum_drink_not_a_meal(self):
        c=catalogue();c['items'][0].update(name='酸梅汤',price=4,tags=[])
        cards=recommend_candidates(c,{'budget':20,'taste':['辣']},at=AT)['cards']
        self.assertNotIn('酸梅汤',[x['name'] for x in cards])

    def test_missing_taste_not_rewarded_by_renormalization(self):
        c=catalogue();c['items'][0]['tags']=[]
        c['items']=c['items'][:1]
        cards=recommend_candidates(c,{'budget':20,'taste':['辣']},at=AT)['cards']
        self.assertEqual(cards[0]['score_parts']['taste'],0)

    def test_glb_binary_and_rendering_metadata_preserved(self):
        document={'asset':{'version':'2.0'},'nodes':[{'name':'Building_1','translation':[1,2,3],'extras':{'private':'hidden'}}]}
        js=json.dumps(document).encode();js+=b' '*(-len(js)%4)
        binary=b'ABCD';body=struct.pack('<II',len(js),0x4E4F534A)+js+struct.pack('<II',4,0x004E4942)+binary
        raw=struct.pack('<4sII',b'glTF',2,12+len(body))+body
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'model.glb';path.write_bytes(raw)
            result=public_glb(path)
            self.assertEqual(path.read_bytes(),raw)
        self.assertNotIn(b'hidden',result)
        self.assertEqual(result[-4:],binary)
        size=struct.unpack_from('<I',result,12)[0]
        self.assertEqual(json.loads(result[20:20+size]),strip_extras(document))

    def test_all_buildings_and_pending_evidence(self):
        audit=building_audit()
        self.assertEqual(audit['summary']['total'],234)
        self.assertEqual(audit['summary']['mesh_matched'],234)
        self.assertEqual(len({b['id'] for b in audit['buildings']}),234)
        self.assertEqual(sum(bool(b['south_candidate']) for b in audit['buildings']),28)
        for b in audit['buildings']:
            if b['id'] in ('499437078','499437130','681441380','681441378','681441379'):
                self.assertEqual(b['model_floors'],2)
                self.assertTrue(b['parameter_consistent'])


class ErrorTests(unittest.TestCase):
    def test_unconfigured_not_retryable(self):
        with patch.dict('os.environ',{'DEEPSEEK_API_KEY':''}):model=DeepSeekModel()
        with self.assertRaises(ModelError) as error:model.complete([],[],999999999)
        event=error.exception.event('test-request')
        self.assertEqual(event['code'],'MODEL_UNCONFIGURED');self.assertFalse(event['retryable'])

    def test_upstream_errors_redacted(self):
        for status,code,retryable in [(401,'MODEL_AUTH',False),(402,'MODEL_QUOTA',False),(429,'MODEL_BUSY',True),(500,'MODEL_UNAVAILABLE',True)]:
            model=DeepSeekModel();model.key='fixture-not-a-real-key'
            with patch('urllib.request.urlopen',side_effect=urllib.error.HTTPError('test',status,'sensitive-body',{},None)):
                with self.assertRaises(ModelError) as error:model.complete([],[],999999999)
            self.assertEqual(error.exception.code,code);self.assertEqual(error.exception.retryable,retryable)
            self.assertNotIn('sensitive',str(error.exception));self.assertNotIn('key',str(error.exception))

    def test_cancel_after_model_prevents_result(self):
        flag=threading.Event()
        class Model:
            def complete(self,*args):flag.set();return {'content':'done'},{}
        events=[]
        with self.assertRaises(ModelError) as error:AgentController(Model(),CampusTools(catalogue())).run({'message':'hi'},events.append,flag.is_set)
        self.assertEqual(error.exception.code,'CANCELLED')
        self.assertFalse(any(e['type']=='result' for e in events))


class AdminBoundaryTests(unittest.TestCase):
    def test_member_cannot_read_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            write(Path(directory)/'catalog.json',dict(schema_version=1,pois=[],shops=[],items=[],locations=[]))
            server=make_server(0,Path(directory),local_team=True,admin_port=0)
            threads=[threading.Thread(target=s.serve_forever,daemon=True) for s in (server,server.admin_server)]
            for t in threads:t.start()
            try:
                for target,expected in [(server,403),(server.admin_server,200)]:
                    port=target.server_port;conn=http.client.HTTPConnection('127.0.0.1',port)
                    conn.request('POST','/api/contribute/login',json.dumps({'name':'g'}),{'Origin':target.expected_origin,'Content-Type':'application/json'})
                    response=conn.getresponse();cookie=response.getheader('Set-Cookie').split(';')[0];response.read()
                    for path in ['/audit/','/audit.js','/api/contribute/building-audit']:
                        conn.request('GET',path,headers={'Cookie':cookie});response=conn.getresponse();self.assertEqual(response.status,expected);response.read()
                    conn.close()
            finally:
                server.shutdown();server.admin_server.shutdown();server.server_close()
                for t in threads:t.join()


class HTTPRecoveryTests(unittest.TestCase):
    def test_cancel_and_cached_replay_do_not_repeat_model(self):
        entered=threading.Event();release=threading.Event()
        class SlowModel:
            calls=0
            def complete(self,*args):
                self.calls+=1;entered.set();release.wait(4);return {'content':'done'},{}
        model=SlowModel();server=make_app_server(0,AgentController(model,CampusTools(catalogue())))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(path,body,origin=None):
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            try:
                conn.request('POST',path,json.dumps(body),{'Origin':origin or server.origin,'X-BNU-Client':'1','Content-Type':'application/json'})
                response=conn.getresponse();return response.status,response.read()
            finally:conn.close()
        result=[];body={'message':'你好','request_id':'cancel-fixture-1'}
        client=threading.Thread(target=lambda:result.append(request('/api/agent/chat',body)))
        try:
            client.start();self.assertTrue(entered.wait(2))
            self.assertEqual(request('/api/agent/cancel',body,'https://invalid.example')[0],403)
            cancelled=request('/api/agent/cancel',body)
            self.assertTrue(json.loads(cancelled[1])['cancel_requested'])
            release.set();client.join(5)
            events=[json.loads(line) for line in result[0][1].splitlines()]
            self.assertEqual(events[-1]['code'],'CANCELLED')
            self.assertEqual(events[-1]['request_id'],body['request_id'])
            self.assertEqual(request('/api/agent/chat',body),result[0]);self.assertEqual(model.calls,1)
        finally:
            release.set();client.join(5);server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
