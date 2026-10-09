"""HTTP conditional caching: public render bytes only, no paid requests."""
import hashlib
import http.client
import threading
import time
import unittest
from unittest.mock import patch
from app_server import make_app_server
from backend.agent.public_model import public_glb
from backend.storage import ROOT


class AssetCacheTests(unittest.TestCase):
    def setUp(self):
        self.server=make_app_server(0,preview_origin='https://cache-test.trycloudflare.com')
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def get(self,path='/map/campus.glb',tag=None,host='cache-test.trycloudflare.com'):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        headers={'Host':host}
        if tag is not None:headers['If-None-Match']=tag
        c.request('GET',path,headers=headers)
        r=c.getresponse();result=(r.status,dict(r.getheaders()),r.read());c.close()
        return result

    def test_model_saved_then_revalidated_without_body(self):
        status,h,raw=self.get()
        self.assertEqual(status,200)
        self.assertEqual(raw,public_glb(ROOT/'output/bnu_campus_web_white_v7.glb'))
        self.assertEqual(h['ETag'],'"'+hashlib.sha256(raw).hexdigest()+'"')
        self.assertEqual(h['Cache-Control'],'public, no-cache, must-revalidate')
        status,h2,body=self.get(tag=h['ETag'])
        self.assertEqual((status,body),(304,b''));self.assertEqual(h2['ETag'],h['ETag'])
        self.assertNotIn('Set-Cookie',h2)

    def test_changed_served_bytes_invalidate_same_url(self):
        with patch('app_server.public_glb',return_value=b'old-public-model'):
            _,h,_=self.get()
        with patch('app_server.public_glb',return_value=b'new-public-model'):
            s,h2,b=self.get(tag=h['ETag'])
        self.assertEqual((s,b),(200,b'new-public-model'));self.assertNotEqual(h['ETag'],h2['ETag'])

    def test_weak_list_and_wildcard_validators(self):
        with patch('app_server.public_glb',return_value=b'model'):
            _,h,_=self.get()
            for tag in ('W/'+h['ETag'],'"other", W/'+h['ETag'],'*'):
                self.assertEqual(self.get(tag=tag)[0],304)
            self.assertEqual(self.get(tag='"wrong"')[0],200)

    def test_texture_revalidates(self):
        path='/explore/art/atelier-plaster-v1.png'
        s,h,b=self.get(path);self.assertEqual(s,200);self.assertTrue(b.startswith(b'\x89PNG'))
        self.assertEqual(self.get(path,h['ETag'])[0],304)

    def test_other_responses_never_become_cached(self):
        for path in ('/api/account/me','/api/agent/status','/explore/','/explore/main.js',
                     '/api/account/conversations','/data/life/accounts/accounts.json',
                     '/data/life/official_sources/verified-20261008.json','/missing.png'):
            _,h,_=self.get(path,tag='*')
            self.assertEqual(h['Cache-Control'],'no-store',path)
            self.assertNotIn('ETag',h,path)

    def test_expiry_and_host_are_checked_before_cache(self):
        s,h,_=self.get(tag='*',host='wrong.example')
        self.assertEqual(s,403);self.assertEqual(h['Cache-Control'],'no-store')
        with patch('app_server.time.monotonic',return_value=time.monotonic()+7201):
            s,h,_=self.get(tag='*')
        self.assertEqual(s,410);self.assertEqual(h['Cache-Control'],'no-store')


if __name__=='__main__':unittest.main()
