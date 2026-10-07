"""Isolated HTTP checks; no tunnel, secrets or live model calls."""
import http.client
import json
import threading
import unittest
from unittest.mock import patch
from app_server import make_app_server


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.server=make_app_server(0,preview_origin='https://campus-test.trycloudflare.com')
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def request(self,path,body=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        h={'Host':'campus-test.trycloudflare.com','Origin':self.server.origin,'X-BNU-Client':'1','Content-Type':'application/json'}
        h.update(headers or {})
        conn.request('GET' if body is None else 'POST',path,None if body is None else json.dumps(body),h)
        response=conn.getresponse();raw=response.read();status=response.status;conn.close()
        return status,raw

    def test_user_page_and_status(self):
        self.assertEqual(self.request('/explore/')[0],200)
        status,raw=self.request('/api/agent/status');data=json.loads(raw)
        self.assertEqual(status,200);self.assertFalse(data['configured']);self.assertFalse(data['local_only']);self.assertTrue(data['preview'])

    def test_private_paths_never_served(self):
        for path in ('/data/life/catalog.json','/.env','/.git/config','/admin/','/api/contribute/submissions','/../app_server.py'):
            self.assertEqual(self.request(path)[0],404,path)

    def test_exact_host_and_origin(self):
        self.assertEqual(self.request('/explore/',headers={'Host':'evil.trycloudflare.com'})[0],403)
        self.assertEqual(self.request('/api/app/candidates',{},headers={'Origin':'https://evil.trycloudflare.com'})[0],403)
        self.assertEqual(self.request('/api/app/candidates',{},headers={'X-BNU-Client':''})[0],403)

    def test_no_model_even_with_environment_key(self):
        with patch('backend.agent.model.DeepSeekModel.complete',side_effect=AssertionError('Must never call model')):
            status,raw=self.request('/api/agent/chat',{'message':'hello','request_id':'test-preview'})
        self.assertEqual(status,503);self.assertEqual(json.loads(raw)['code'],'MODEL_UNCONFIGURED')
        self.assertEqual(self.request('/api/agent/cancel',{'request_id':'other'})[0],403)

    def test_conditions_still_work_without_model(self):
        catalog={'pois':[],'shops':[],'items':[],'locations':[]}
        with patch('backend.agent.tools.CampusTools.snapshot',return_value=catalog):
            status,raw=self.request('/api/app/candidates',{'conditions':{'budget':20}})
        self.assertEqual(status,200);self.assertEqual(json.loads(raw)['cards'],[])

    def test_post_limit(self):
        for _ in range(30):self.assertEqual(self.request('/api/agent/chat',{})[0],503)
        self.assertEqual(self.request('/api/agent/chat',{})[0],429)

    def test_expiration(self):
        import time
        future=time.monotonic()+7201
        with patch('app_server.time.monotonic',return_value=future):
            self.assertEqual(self.request('/explore/')[0],410)

    def test_origin_validation(self):
        for origin in ('http://campus-test.trycloudflare.com','https://*.trycloudflare.com','https://campus-test.trycloudflare.com.evil','https://campus-test.trycloudflare.com/path'):
            with self.assertRaises(ValueError):make_app_server(0,preview_origin=origin)


if __name__=='__main__':unittest.main()
