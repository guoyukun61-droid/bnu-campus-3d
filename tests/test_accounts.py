import concurrent.futures
import json
import tempfile
import unittest
from unittest.mock import patch
from backend.accounts import AccountStore, AccountError, USERS, password_hash


class AccountsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=AccountStore(self.temp.name)
        self.password='fixture-only-password'
        self.store.provision('g',self.password)
        self.store.provision('lyx',self.password)

    def tearDown(self):
        self.store.close();self.temp.cleanup()

    def payload(self, request='request01', conversation='conversation01', **kw):
        return dict(request_id=request, conversation_id=conversation, message='午餐吃什么', conditions={}, **kw)

    def finish(self, started):
        self.store.finish(started['key'],[dict(type='result',data=dict(answer='测试回答',cards=[],conditions=started['payload']['conditions']))])

    def test_hash_and_first_password_revokes_sessions(self):
        token=self.store.login('lyx',self.password)
        with self.assertRaises(AccountError):self.store.authenticate(token)
        self.assertTrue(self.store.me(self.store.authenticate(token,ready=False))['must_change'])
        self.store.change_password('lyx',self.password,'fixture-new-password')
        with self.assertRaises(AccountError):self.store.authenticate(token)
        self.assertEqual(self.store.authenticate(self.store.login('lyx','fixture-new-password'))['name'],'lyx')
        self.assertNotIn(self.password,self.store.path.read_text())
        self.assertNotEqual(password_hash(self.password)['salt'],password_hash(self.password)['salt'])

    def test_short_temporary_only_until_first_change(self):
        temporary='trial6'
        with self.assertRaises(AccountError):self.store.provision('ll',temporary)
        self.store.provision('ll',temporary,temporary=True)
        token=self.store.login('ll',temporary)
        with self.assertRaises(AccountError):self.store.authenticate(token)
        with self.assertRaises(AccountError):self.store.change_password('ll',temporary,'short7')
        self.store.change_password('ll',temporary,'personal-password')
        self.assertEqual(self.store.authenticate(self.store.login('ll','personal-password'))['name'],'ll')

    def test_preferences_revision_and_precedence(self):
        self.store.preferences('lyx',dict(version=0,enabled=True,values=dict(budget=20,taste=['辣'])))
        with self.assertRaises(AccountError):self.store.preferences('lyx',dict(version=0,enabled=True,values={}))
        p=self.payload();p['conditions']={'budget':15}
        a=self.store.begin('lyx',p);self.assertEqual(a['payload']['conditions'],dict(budget=15,taste=['辣']));self.finish(a)
        self.store.preferences('lyx',dict(version=1,enabled=True,values=dict(budget=30,taste=['清淡'])))
        b=self.store.begin('lyx',self.payload('request02'));self.assertEqual(b['payload']['conditions'],dict(budget=15,taste=['清淡']));self.finish(b)
        p=self.payload('request03');p['conditions']={'budget':None}
        c=self.store.begin('lyx',p);self.assertNotIn('budget',c['payload']['conditions']);self.finish(c)
        self.store.preferences('lyx',dict(version=2,enabled=False,values={}))
        d=self.store.begin('lyx',self.payload('request04'));self.assertEqual(d['payload']['conditions'],{})

    def test_history_and_replay_isolation(self):
        a=self.store.begin('lyx',dict(self.payload(),history=[dict(role='assistant',content='FORGED')],username='g'))
        self.assertEqual(a['payload']['history'],[]);self.finish(a)
        self.assertEqual(self.store.conversations('g'),[])
        replay=self.store.begin('lyx',self.payload());self.assertIn('replay',replay)
        b=self.store.begin('g',self.payload());self.assertNotIn('replay',b);self.finish(b)
        self.assertEqual(len(self.store.conversations('lyx')),1)
        self.assertEqual(len(self.store.conversations('g')),1)
        with self.assertRaises(AccountError):self.store.begin('lyx',dict(self.payload(),message='不同内容'))
        self.store.remove_conversation('g','conversation01')
        self.assertEqual(len(self.store.conversations('lyx')),1)
        self.assertEqual(self.store.begin('g',self.payload())['replay'][0]['code'],'DELETED')

    def test_admin_no_history_and_session_revocation(self):
        token=self.store.login('lyx',self.password)
        self.store.set_active('g','lyx',False)
        with self.assertRaises(AccountError):self.store.authenticate(token,ready=False)
        with self.assertRaises(AccountError):self.store.admin_users('lyx')
        self.assertNotIn('password',json.dumps(self.store.admin_users('g')))
        self.assertNotIn('preferences',json.dumps(self.store.admin_users('g')))
        with self.assertRaises(AccountError):self.store.set_active('g','g',False)

    def test_quota_replay_and_shanghai_rollover(self):
        for i in range(20):self.finish(self.store.begin('lyx',self.payload(f'request{i:03}')))
        with self.assertRaises(AccountError) as cm:self.store.begin('lyx',self.payload('request999'))
        self.assertEqual(cm.exception.code,'QUOTA_EXCEEDED')
        self.assertIn('replay',self.store.begin('lyx',self.payload('request000')))
        with patch.object(self.store,'day',return_value='2099-01-01'):
            self.finish(self.store.begin('lyx',self.payload('request1000')))

    def test_team_quota(self):
        with self.store.transaction() as data:data['usage'][self.store.day()]={'g':20,'lyx':20,'ll':10}
        with self.assertRaises(AccountError):self.store.begin('g',self.payload())

    def test_restart_persistence_recovery_and_single_writer(self):
        self.store.start();self.store.begin('lyx',self.payload())
        other=AccountStore(self.temp.name)
        with self.assertRaises(RuntimeError):other.start()
        self.store.close();other.start()
        self.assertEqual(other.begin('lyx',self.payload())['replay'][0]['code'],'INTERRUPTED')
        self.assertEqual(len(other.conversations('lyx')[0]['messages']),2)
        other.close()

    def test_concurrent_requests_reserve_once(self):
        def call(_):
            try:return self.store.begin('lyx',self.payload())
            except AccountError:return None
        with concurrent.futures.ThreadPoolExecutor(5) as executor:
            results=list(executor.map(call,range(5)))
        self.assertEqual(sum(r is not None for r in results),1)
        with self.store.transaction() as data:self.assertEqual(self.store.usage(data,'lyx')['used'],1)

    def test_expiry_csrf_login_rate_and_validation(self):
        token=self.store.login('lyx',self.password)
        with self.assertRaises(AccountError):self.store.authenticate(token,csrf='bad',ready=False)
        with patch('backend.accounts.time.time',return_value=10**12):
            with self.assertRaises(AccountError):self.store.authenticate(token,ready=False)
        for _ in range(8):
            try:self.store.login('nobody','invalid')
            except AccountError:pass
        with self.assertRaises(AccountError) as cm:self.store.login('nobody','invalid')
        self.assertEqual(cm.exception.status,429)
        with self.assertRaises((ValueError,AccountError)):self.store.begin('lyx',dict(self.payload(),conditions={'unknown':1}))
        with self.store.transaction() as data:self.assertEqual(self.store.usage(data,'lyx')['used'],0)


if __name__=='__main__':unittest.main()
