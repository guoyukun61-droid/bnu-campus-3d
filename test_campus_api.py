"""API tests use a temporary database, never user records."""
import unittest, tempfile, threading, json, urllib.request, urllib.error
from pathlib import Path
import campus_server as api
class APITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='bnu-api-test-');api.DB=Path(cls.tmp.name)/'test.sqlite3';api.init()
        cls.server=api.ThreadingHTTPServer(('127.0.0.1',0),api.Handler)
        cls.url=f'http://127.0.0.1:{cls.server.server_port}';cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.tmp.cleanup()
    def request(self,path,method='GET',data=None,origin=True):
        headers={'Content-Type':'application/json'}
        if origin:headers['Origin']=self.url
        req=urllib.request.Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,headers=headers,method=method)
        try:
            with urllib.request.urlopen(req) as r:return r.status,json.loads(r.read())
        except urllib.error.HTTPError as e:return e.code,json.loads(e.read())
    def record(self):return dict(name='测试食堂',category='canteen',x=-290,y=-360,source='automated test',status='unverified',tags=[],building_id=None)
    def test_roundtrip_revision_history(self):
        status,r=self.request('/api/places','POST',self.record());self.assertEqual(status,201)
        r['notes']='价格未核实';status,v2=self.request('/api/places/'+r['id'],'PUT',r);self.assertEqual(status,200);self.assertEqual(v2['revision'],2)
        self.assertEqual(self.request('/api/places/'+r['id'],'PUT',r)[0],409)
        self.assertTrue(any(x['id']==r['id'] for x in self.request('/api/places')[1]['records']))
        with api.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM history WHERE id=?',(r['id'],)).fetchone()[0],1)
    def test_reject_foreign_origin(self):self.assertEqual(self.request('/api/places','POST',self.record(),False)[0],403)
    def test_reject_bad_coordinates(self):
        d=self.record();d['x']=99999;self.assertEqual(self.request('/api/places','POST',d)[0],400)
    def test_reject_unknown_building(self):
        d=self.record();d['building_id']=1;self.assertEqual(self.request('/api/places','POST',d)[0],400)
    def test_private_files(self):
        self.assertEqual(self.request('/data/campus_info.sqlite3')[0],403)
        self.assertEqual(self.request('/campus_server.py')[0],403)
    def test_filter(self):self.assertEqual(self.request('/api/places?status=verified')[1]['records'],[])
    def test_multiple_tenants_and_floor(self):
        for name,floor in [('一楼测试店','1楼'),('二楼测试店','2楼')]:
            d=self.record();d.update(name=name,building_id=499437078,floor=floor,unit='A01')
            status,r=self.request('/api/places','POST',d);self.assertEqual(status,201);self.assertEqual(r['floor'],floor)
        status,data=self.request('/api/places?building_id=499437078')
        self.assertEqual(status,200);self.assertEqual(len(data['records']),2)
    def test_reject_invalid_floor(self):
        d=self.record();d['floor']=['1'];self.assertEqual(self.request('/api/places','POST',d)[0],400)
if __name__=='__main__':unittest.main()
