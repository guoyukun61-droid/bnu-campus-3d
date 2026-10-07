import copy
import hashlib
import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from backend.storage import write, now, read
from backend.adapters import CatalogAdapter
from backend.contribution import ContributionStore, Conflict, digest
from contribution_server import make_server


class ContributionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.life=Path(self.temp.name)
        self.catalog=dict(schema_version=1,pois=[dict(id='p',name='虚构测试店',source='test',status='verified',zone='campus',location=None)],
                          shops=[dict(id='s',name='虚构测试店',poi_id='p',source='test')],items=[],locations=[])
        write(self.life/'catalog.json',self.catalog)
        self.adapter=CatalogAdapter(self.life)
        self.store=ContributionStore(self.life/'contributions',self.adapter)
        self.user=dict(id='a',name='虚构队员A',role='member');self.other=dict(id='b',name='虚构队员B',role='member');self.admin=dict(id='owner',name='虚构审核员',role='admin')
        write(self.store.directory/'members.json',[dict(**u,active=True,token_hash=hashlib.sha256(('test-'+u['id']).encode()).hexdigest()) for u in (self.user,self.other,self.admin)])

    def tearDown(self):self.temp.cleanup()

    def data(self,key='request-0001'):
        return dict(kind='items',patch=dict(name='虚构测试面',shop_id='s',price=18,tags=['辣'],available=True),evidence='隔离测试，非真实现场采集',observed_at=now(),request_id=key)

    def approve(self,record):return self.store.review(self.admin,dict(id=record['id'],revision=record['revision'],action='approved'))

    def test_publish_idempotency_and_restart(self):
        data=self.data();r=self.store.submit(self.user,data)
        self.assertEqual(self.adapter.snapshot()['items'],[])
        self.assertEqual(self.store.submit(self.user,data)['id'],r['id'])
        result=self.approve(r);self.approve(r)
        item=self.adapter.snapshot()['items'][0]
        self.assertEqual(item['price'],18);self.assertEqual(item['price_source'],'field_observation')
        self.assertIn('price',item['field_evidence'])
        restarted=ContributionStore(self.store.directory,self.adapter)
        self.assertEqual(restarted.records(self.user)[0]['status'],'approved')
        self.assertEqual(restarted.state()['version'],1)

    def test_permissions_and_visibility(self):
        r=self.store.submit(self.user,self.data())
        self.assertEqual(self.store.records(self.other),[])
        with self.assertRaises(PermissionError):self.store.review(self.other,dict(id=r['id'],revision=1,action='approved'))
        self.assertEqual(len(self.store.records(self.admin)),1)

    def test_partial_update_preserves_official_values_and_evidence(self):
        catalog=copy.deepcopy(self.catalog)
        official=dict(source='official',observed_at='2026-09-01T10:00:00+08:00',evidence='隔离测试学校资料')
        catalog['pois'][0].update(address='原地址',opening_hours=[['09:00','20:00']],hours_source='official',field_evidence={'opening_hours':official})
        write(self.life/'catalog.json',catalog)
        base=self.adapter.snapshot()['pois'][0]
        data=dict(kind='pois',entity_id='p',base_revision=digest(base),patch={'location_description':'仅补入口朝向'},evidence='隔离测试现场观察',observed_at=now(),request_id='partial-request-1')
        record=self.store.submit(self.user,data)
        self.assertNotIn('location_description',self.adapter.snapshot()['pois'][0])
        self.approve(record)
        updated=self.adapter.snapshot()['pois'][0]
        self.assertEqual(updated['name'],base['name'])
        self.assertEqual(updated['address'],'原地址')
        self.assertEqual(updated['opening_hours'],[['09:00','20:00']])
        self.assertEqual(updated['hours_source'],'official')
        self.assertEqual(updated['field_evidence']['opening_hours'],official)
        self.assertNotIn('building_floors',updated)
        self.assertEqual(updated['location_description'],'仅补入口朝向')

    def test_partial_existing_price_update_needs_no_name_or_parent(self):
        initial=self.store.submit(self.user,self.data());self.approve(initial)
        base=self.adapter.snapshot()['items'][0]
        data=dict(kind='items',entity_id=base['id'],base_revision=digest(base),patch={'price':0},evidence='隔离测试价格观察',observed_at=now(),request_id='price-only-request')
        self.approve(self.store.submit(self.user,data))
        current=self.adapter.snapshot()['items'][0]
        self.assertEqual(current['price'],0)
        self.assertEqual(current['name'],base['name'])
        self.assertEqual(current['shop_id'],base['shop_id'])

    def test_conflicting_reviews_preserve_values(self):
        base=self.adapter.snapshot()['pois'][0]
        a=dict(kind='pois',entity_id='p',base_revision=digest(base),patch={'name':'测试修订A'},evidence='隔离测试证据',observed_at=now(),request_id='request-a')
        b=copy.deepcopy(a);b.update(request_id='request-b',patch={'name':'测试修订B'})
        r1=self.store.submit(self.user,a);r2=self.store.submit(self.other,b)
        self.approve(r1)
        with self.assertRaises(Conflict):self.approve(r2)
        self.assertEqual(self.adapter.snapshot()['pois'][0]['name'],'测试修订A')

    def test_return_draft_and_repeated_request_mismatch(self):
        data=self.data();data['draft']=True
        r=self.store.submit(self.user,data)
        altered=copy.deepcopy(data);altered['patch']['price']=20
        with self.assertRaises(Conflict):self.store.submit(self.user,altered)
        data.update(request_id='new-request-1',submission_id=r['id'],revision=1,draft=False)
        r=self.store.submit(self.user,data)
        returned=self.store.review(self.admin,dict(id=r['id'],revision=r['revision'],action='needs_info',note='补规格'))
        self.assertEqual(returned['status'],'needs_info')

    def test_images_and_revocation(self):
        with self.assertRaises(ValueError):self.store.upload(self.user,b'<svg/>','image/svg+xml')
        with self.assertRaises(ValueError):self.store.upload(self.user,b'<html>','image/png')
        import io
        from PIL import Image
        buffer=io.BytesIO();Image.new('RGB',(2,2)).save(buffer,format='PNG')
        image=self.store.upload(self.user,buffer.getvalue(),'image/png')
        with self.assertRaises(ValueError):self.store.upload(self.user,b'\xff\xd8\xfftest\xff\xd9','image/jpeg')
        with self.assertRaises(PermissionError):self.store.attachment(self.other,image['id'])
        self.assertEqual(self.store.attachment(self.admin,image['id'])[1],'image/jpeg')
        self.assertTrue(self.store.active(self.user));users=read(self.store.directory/'members.json');users[0]['active']=False;write(self.store.directory/'members.json',users)
        self.assertFalse(self.store.active(self.user))

    def test_pending_scope_new_place(self):
        data=self.data();data.update(kind='pois',patch={'name':'虚构新增店'})
        self.approve(self.store.submit(self.user,data))
        self.assertEqual(self.adapter.snapshot()['pois'][-1]['scope_status'],'pending')

    def test_concurrent_retry_and_receipt_after_edit(self):
        from concurrent.futures import ThreadPoolExecutor
        data=self.data();data['draft']=True
        with ThreadPoolExecutor(max_workers=4) as pool:
            rows=list(pool.map(lambda _:self.store.submit(self.user,data),range(8)))
        self.assertEqual(len({r['id'] for r in rows}),1)
        revised=copy.deepcopy(data);revised.update(request_id='next-request-1',submission_id=rows[0]['id'],revision=1,draft=False)
        self.store.submit(self.user,revised)
        self.store.submit(self.user,data)
        self.assertEqual(len(self.store.records(self.user)),1)
        self.assertEqual(self.store.records(self.user)[0]['status'],'submitted')

    def test_recommendation_reads_approved_item_with_evidence(self):
        from backend.recommendation import recommend
        catalog=copy.deepcopy(self.catalog)
        catalog['pois'][0].update(location={'x':0,'y':0},opening_hours=[['00:00','23:59']],hours_source='test',access_scope='public')
        catalog['locations']=[dict(id='start',name='虚构起点',source='test',x=0,y=0)]
        write(self.life/'catalog.json',catalog)
        data=self.data();data['patch']['serving_minutes']=3
        self.approve(self.store.submit(self.user,data))
        request=dict(current_time=now()[:10]+'T11:00:00+08:00',current_location='start',budget=20,available_minutes=90,max_queue_minutes=60,mode='demo')
        result=recommend(self.adapter.snapshot(),request)
        row=result['recommendations'][0]
        self.assertEqual(row['sources']['price'],'field_observation')
        self.assertIn('price',row['field_evidence']['item'])
        self.assertTrue(row['simulation'])
        self.assertIn('记录价格',row['reason'][0])
        self.assertFalse(recommend(self.adapter.snapshot(),dict(request,mode='verified'))['recommendations'])

    def test_invalid_input_and_unknown_parent(self):
        for change in ({'price':float('nan')},{'price':-1},{'shop_id':'missing'},{'source':'simulated'}):
            data=self.data();data['patch'].update(change)
            with self.assertRaises(ValueError):self.store.submit(self.user,data)
        data=self.data();data.update(kind='pois',patch={'name':'测试','coordinates':{'lng':116.3,'lat':39.9,'crs':'GCJ02'}})
        with self.assertRaises(ValueError):self.store.submit(self.user,data)

    def test_map_point_review_and_draft(self):
        base=self.adapter.snapshot()['pois'][0]
        point=dict(x=0,y=0,building_id=None,model='white_v4',crs='local EPSG:32650')
        data=dict(kind='pois',entity_id='p',base_revision=digest(base),patch=dict(map_point=point,building_floors=2,floor_evidence='estimated',location_description='小吃街现场位置待核'),evidence='隔离测试，不是真实测量',observed_at=now(),request_id='map-request-1',draft=True)
        row=self.store.submit(self.user,data)
        restarted=ContributionStore(self.store.directory,self.adapter)
        self.assertEqual(restarted.records(self.user)[0]['patch']['map_point'],point)
        self.assertIsNone(self.adapter.snapshot()['pois'][0]['location'])
        data.update(draft=False,submission_id=row['id'],revision=1,request_id='map-request-2')
        row=self.store.submit(self.user,data);self.approve(row)
        poi=self.adapter.snapshot()['pois'][0]
        self.assertEqual(poi['location'],dict(x=0,y=0))
        self.assertEqual(poi['building_floors'],2)
        self.assertEqual(poi['floor_evidence'],'estimated')
        self.assertIn('map_point',poi['field_evidence'])

    def test_invalid_map_data(self):
        point=dict(x=0,y=0,building_id=None,model='white_v4',crs='local EPSG:32650')
        for change in ({'x':float('nan')},{'x':500},{'y':True},{'crs':'BD09'},{'model':'old'},{'building_id':-999},{'building_id':True}):
            data=self.data();data.update(kind='pois',patch=dict(name='测试地图',map_point=dict(point,**change)))
            with self.assertRaises(ValueError):self.store.submit(self.user,data)
        for patch in ({'building_floors':2},{'building_floors':2.5,'floor_evidence':'observed'},{'building_floors':True,'floor_evidence':'observed'},{'map_point':point,'coordinates':dict(lng=116,lat=40,crs='WGS84')}):
            data=self.data();data.update(kind='pois',patch=dict(name='测试地图',**patch))
            with self.assertRaises(ValueError):self.store.submit(self.user,data)

    def test_http_boundary_csrf_and_sessions(self):
        server=make_server(0,self.life);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=server.expected_origin
        def request(path, data=None, headers=None):
            h=headers or {};raw=json.dumps(data).encode() if data is not None else None
            if data is not None:h={'Content-Type':'application/json','Origin':base,**h}
            return urllib.request.urlopen(urllib.request.Request(base+path,data=raw,headers=h))
        try:
            with self.assertRaises(RuntimeError):make_server(0,self.life)
            with request('/') as response:self.assertEqual(response.status,200)
            with self.assertRaises(urllib.error.HTTPError):request('/data/life/catalog.json')
            with self.assertRaises(urllib.error.HTTPError):request('/map/')
            with request('/api/contribute/login',{'token':'test-a'}) as response:
                cookie=response.headers['Set-Cookie'].split(';')[0];auth=json.load(response)
            for path in ('/map/','/map/map.js','/map/GLTFLoader.js','/map/three.core.min.js','/map/buildings.json'):
                with request(path,headers={'Cookie':cookie}) as response:self.assertEqual(response.status,200)
            with request('/map/buildings.json',headers={'Cookie':cookie}) as response:
                buildings=json.load(response)
                self.assertEqual(buildings['model_version'],'white_v6')
                added=next(b for b in buildings['buildings'] if b['osm_id']==900000000003)
                self.assertIsNone(added['floors'])
                self.assertIn('待核',added['name'])
            for path in ('/index.html','/api/places','/map/../data/life/catalog.json','/output/bnu_campus_web_white_v4.glb'):
                with self.assertRaises(urllib.error.HTTPError) as denied:request(path,headers={'Cookie':cookie})
                self.assertEqual(denied.exception.code,404)
            with self.assertRaises(urllib.error.HTTPError) as error:request('/api/contribute/submissions',self.data(),{'Cookie':cookie})
            self.assertEqual(error.exception.code,403)
            with request('/api/contribute/submissions',self.data(),{'Cookie':cookie,'X-CSRF-Token':auth['csrf']}) as response:self.assertEqual(response.status,200)
            with self.assertRaises(urllib.error.HTTPError):request('/api/contribute/export',headers={'Cookie':cookie})
            with self.assertRaises(urllib.error.HTTPError):request('/api/contribute/submissions',self.data('request-other'),{'Cookie':cookie,'X-CSRF-Token':auth['csrf'],'Origin':'https://evil.example'})
        finally:server.shutdown();server.server_close();thread.join()

    def test_new_model_building_submission_and_multipart_wing(self):
        for index,(x,y,bid) in enumerate([(-328,-350,900000000003),(-375,-330,900000000001)]):
            data=dict(kind='pois',patch=dict(name='隔离测试建筑'+str(index),category='building',map_point=dict(x=x,y=y,building_id=bid,model='white_v4',crs='local EPSG:32650')),evidence='隔离测试，不是真实采集',observed_at=now(),request_id='model-v6-test-'+str(index))
            row=self.store.submit(self.user,data);self.approve(row)
            p=next(p for p in self.adapter.snapshot()['pois'] if p.get('building_id')==bid)
            self.assertEqual(p['location'],{'x':x,'y':y})

    def test_passwordless_public_cannot_review_or_read_other_submissions(self):
        public=make_server(0,self.life,origin='https://team.example',team_mode=True,admin_port=0)
        # A zero port is useful only for this isolated test; the production CLI uses 8792.
        admin=public.admin_server
        workers=[threading.Thread(target=s.serve_forever,daemon=True) for s in (public,admin)]
        for worker in workers:worker.start()
        def invoke(server,path,data=None,cookie=None,csrf=None):
            is_admin=server is admin
            origin='http://127.0.0.1:'+str(admin.server_port) if is_admin else 'https://team.example'
            raw=json.dumps(data).encode() if data is not None else None
            headers={'Host':origin.split('://')[1]}
            if data is not None:headers.update(Origin=origin,**{'Content-Type':'application/json'})
            if cookie:headers['Cookie']=cookie
            if csrf:headers['X-CSRF-Token']=csrf
            url='http://127.0.0.1:'+str(server.server_port)+path
            return urllib.request.urlopen(urllib.request.Request(url,data=raw,headers=headers))
        try:
            with invoke(public,'/api/contribute/login',{'name':'g'}) as response:
                public_cookie=response.headers['Set-Cookie'].split(';')[0];public_auth=json.load(response)
            self.assertEqual(public_auth['user']['role'],'member')
            with invoke(public,'/api/contribute/submissions',self.data(),public_cookie,public_auth['csrf']) as response:own=json.load(response)
            with invoke(public,'/api/contribute/login',{'name':'g'}) as response:
                second_cookie=response.headers['Set-Cookie'].split(';')[0];second_auth=json.load(response)
            with invoke(public,'/api/contribute/submissions',cookie=second_cookie) as response:self.assertEqual(json.load(response),[])
            with self.assertRaises(urllib.error.HTTPError) as error:
                invoke(public,'/api/contribute/review',{'id':own['id'],'revision':1,'action':'approved'},public_cookie,public_auth['csrf'])
            self.assertEqual(error.exception.code,403)
            with invoke(admin,'/api/contribute/login',{'name':'g'}) as response:
                admin_cookie=response.headers['Set-Cookie'].split(';')[0];admin_auth=json.load(response)
            self.assertEqual(admin_auth['user']['role'],'admin')
            with self.assertRaises(urllib.error.HTTPError) as error:invoke(public,'/api/contribute/export',cookie=admin_cookie)
            self.assertEqual(error.exception.code,403)
            with invoke(admin,'/api/contribute/review',{'id':own['id'],'revision':1,'action':'approved'},admin_cookie,admin_auth['csrf']) as response:
                self.assertEqual(json.load(response)['status'],'approved')
            self.assertEqual(self.adapter.snapshot()['items'][0]['name'],'虚构测试面')
        finally:
            public.shutdown();admin.shutdown();public.server_close()
            for worker in workers:worker.join()

if __name__=='__main__':unittest.main()
