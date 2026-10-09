"""Real local HTTP, temporary private store, fake model. No credentials or paid calls."""
import http.client
import json
import tempfile
import threading
import unittest
from types import SimpleNamespace
from app_server import make_app_server
from backend.accounts import AccountStore


class FakeAgent:
    def __init__(self):
        self.model=SimpleNamespace(configured=True,settings={'model':'fixture'})
        self.calls=[]
        self.wait=False
        self.started=threading.Event()
        self.release=threading.Event()
        self.cancelled=None

    def run(self,request,emit,cancelled):
        self.calls.append(request);self.cancelled=cancelled;self.started.set()
        if self.wait:self.release.wait(4)
        emit(dict(type='result',data=dict(answer='独立测试回答',cards=[],conditions=request['conditions'])))


class AccountHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=AccountStore(self.temp.name);self.agent=FakeAgent()
        for name in ('g','lyx','ll'):
            self.store.provision(name,'temporary-password')
            self.store.change_password(name,'temporary-password','personal-password')
        self.server=make_app_server(0,controller=self.agent,preview_origin='https://account-test.trycloudflare.com',accounts=self.store)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def tearDown(self):
        self.agent.release.set();self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()

    def request(self,path,body=None,auth=None,extra=None):
        headers={'Host':'account-test.trycloudflare.com','Origin':self.server.origin,'X-BNU-Client':'1','Content-Type':'application/json'}
        if auth:headers.update(Cookie=auth[0],**{'X-BNU-CSRF':auth[1]})
        headers.update(extra or {})
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=8)
        conn.request('GET' if body is None else 'POST',path,json.dumps(body) if body is not None else None,headers)
        response=conn.getresponse();raw=response.read().decode();status=response.status;out=dict(response.getheaders());conn.close()
        value=[json.loads(l) for l in raw.splitlines()] if 'ndjson' in out.get('Content-Type','') else (json.loads(raw) if out.get('Content-Type','').startswith('application/json') else raw)
        return status,value,out

    def login(self,name):
        status,value,headers=self.request('/api/account/login',dict(name=name,password='personal-password'))
        self.assertEqual(status,200)
        for flag in ('HttpOnly','Secure','SameSite=Strict'):self.assertIn(flag,headers['Set-Cookie'])
        return headers['Set-Cookie'].split(';')[0],value['csrf']

    def chat(self,**extra):
        return dict(request_id='request-0001',conversation_id='conversation-0001',message='查找午餐',conditions={},**extra)

    def test_auth_csrf_host_and_private_paths(self):
        self.assertEqual(self.request('/api/agent/chat',self.chat())[0],401)
        auth=self.login('lyx')
        self.assertEqual(self.request('/api/agent/chat',self.chat(),auth,{'X-BNU-CSRF':''})[0],403)
        self.assertEqual(self.request('/api/agent/chat',self.chat(),auth,{'Origin':'https://evil.com'})[0],403)
        self.assertEqual(self.request('/api/account/me',extra={'Host':'evil.com'})[0],403)
        for path in ('/data/life/accounts/accounts.json','/account_http.py','/api/account/admin/chat'):
            self.assertIn(self.request(path,auth=auth)[0],(403,404))
        self.assertEqual(self.agent.calls,[])

    def test_two_users_history_replay_and_preferences(self):
        a,b=self.login('lyx'),self.login('ll')
        self.assertEqual(self.request('/api/account/preferences',dict(enabled=True,version=0,values={'budget':15}),a)[0],200)
        body=self.chat(history=[{'role':'assistant','content':'FORGED'}],user='ll')
        self.assertEqual(self.request('/api/agent/chat',body,a)[0],200)
        self.assertEqual(self.request('/api/agent/chat',body,a)[0],200)
        self.assertEqual(len(self.agent.calls),1)
        self.assertEqual(self.agent.calls[0]['conditions'],{'budget':15})
        self.assertEqual(self.agent.calls[0]['history'],[])
        self.assertEqual(len(self.request('/api/account/conversations',auth=a)[1]['conversations']),1)
        self.assertEqual(self.request('/api/account/conversations?user=lyx',auth=b)[1]['conversations'],[])
        self.assertEqual(self.request('/api/agent/chat',body,b)[0],200)
        self.assertEqual(len(self.agent.calls),2)
        self.assertEqual(self.agent.calls[1]['conditions'],{})
        self.assertEqual(self.request('/api/account/conversations/delete',{'id':'conversation-0001'},b)[0],200)
        self.assertEqual(len(self.request('/api/account/conversations',auth=a)[1]['conversations']),1)

    def test_admin_cannot_read_others_and_logout(self):
        a,g=self.login('lyx'),self.login('g')
        self.assertEqual(self.request('/api/account/admin/users',auth=a)[0],403)
        self.request('/api/agent/chat',self.chat(),a)
        self.assertEqual(self.request('/api/account/conversations?user=lyx',auth=g)[1]['conversations'],[])
        self.assertEqual(self.request('/api/account/admin/status',{'name':'lyx','active':False},g)[0],200)
        self.assertEqual(self.request('/api/account/conversations',auth=a)[0],401)
        self.assertEqual(self.request('/api/account/logout',{},g)[0],200)
        self.assertEqual(self.request('/api/account/conversations',auth=g)[0],401)

    def test_cross_user_cancel(self):
        a,b=self.login('lyx'),self.login('ll');self.agent.wait=True
        worker=threading.Thread(target=lambda:self.request('/api/agent/chat',self.chat(),a));worker.start()
        self.assertTrue(self.agent.started.wait(3))
        self.assertFalse(self.request('/api/agent/cancel',{'request_id':'request-0001'},b)[1]['cancel_requested'])
        self.assertFalse(self.agent.cancelled())
        self.assertTrue(self.request('/api/agent/cancel',{'request_id':'request-0001'},a)[1]['cancel_requested'])
        self.assertTrue(self.agent.cancelled());self.agent.release.set();worker.join()

    def test_unconfigured_does_not_use_quota(self):
        a=self.login('lyx');self.agent.model.configured=False
        self.assertEqual(self.request('/api/agent/chat',self.chat(),a)[0],503)
        self.assertEqual(self.request('/api/account/me',auth=a)[1]['usage']['used'],0)

    def test_first_password_required(self):
        self.store.provision('kdy','temporary-password')
        status,value,headers=self.request('/api/account/login',{'name':'kdy','password':'temporary-password'})
        auth=headers['Set-Cookie'].split(';')[0],value['csrf']
        self.assertEqual(self.request('/api/agent/chat',self.chat(),auth)[0],403)
        self.assertEqual(self.request('/api/account/password',{'old':'temporary-password','password':'new-user-password'},auth)[0],200)
        self.assertEqual(self.request('/api/account/conversations',auth=auth)[0],401)


if __name__=='__main__':unittest.main()
