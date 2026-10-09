"""Account context reconstruction stays inside an isolated temporary repository."""
import hashlib
import json
import tempfile
import unittest

from backend.accounts import AccountStore, AccountError


class AccountsContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = AccountStore(self.temp.name)
        self.store.provision('g', 'fixture-only-password')
        self.store.provision('lyx', 'fixture-only-password')

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def payload(self, ident='request01', **kwargs):
        return dict(request_id=ident, conversation_id='conversation01', message='测试查询', conditions={}, **kwargs)

    def finish(self, started, cards=None):
        self.store.finish(started['key'], [dict(type='result', data=dict(
            answer='测试回答', cards=cards or [], conditions=started['payload']['conditions']))])

    def test_invalid_context_reserves_no_quota_and_creates_no_chat(self):
        for context in ({'selected': {'kind': 'poi', 'id': 'p0', 'name': '伪造'}},
                        {'selected': {'kind': 'poi', 'id': 'x\n'}}, {'location': 'fake'}):
            with self.assertRaises(ValueError):
                self.store.begin('lyx', self.payload(context=context))
        with self.store.transaction() as data:
            self.assertEqual(self.store.usage(data, 'lyx')['used'], 0)
            self.assertEqual(data['conversations'], {})
            self.assertEqual(data['requests'], {})

    def test_legacy_digest_and_empty_context_retries_remain_compatible(self):
        request = self.payload()
        started = self.store.begin('lyx', request)
        old_clean = dict(request, mode='real')
        expected = hashlib.sha256(json.dumps(old_clean, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        with self.store.transaction() as data:
            self.assertEqual(data['requests'][started['key']]['digest'], expected)
        self.finish(started)
        for context in ({}, {'selected': None}, None):
            self.assertIn('replay', self.store.begin('lyx', self.payload(context=context)))

    def test_nonempty_context_is_bound_to_request_digest(self):
        context = {'selected': {'kind': 'building', 'id': 'b0'}}
        request = self.payload(context=context)
        started = self.store.begin('lyx', request)
        self.assertEqual(started['payload']['context'], context)
        self.assertEqual(started['payload']['conditions'], {})
        self.finish(started)
        self.assertIn('replay', self.store.begin('lyx', request))
        for changed in (None, {'selected': {'kind': 'building', 'id': 'other'}}):
            with self.assertRaises(AccountError) as raised:
                self.store.begin('lyx', self.payload(context=changed))
            self.assertEqual(raised.exception.code, 'CONFLICT')

    def test_last_success_survives_error_and_ignores_client_history(self):
        first = self.store.begin('lyx', self.payload())
        self.finish(first, [dict(type='food', id='item-1', outlet_id='window-1', poi_id='floor-1')])
        failed = self.store.begin('lyx', self.payload('request02'))
        self.store.finish(failed['key'], [dict(type='error', code='MODEL_TIMEOUT', text='测试中断')])
        next_turn = self.store.begin('lyx', self.payload('request03',
            history=[dict(role='assistant', content='OTHER ACCOUNT SECRET')],
            previous_entities=[dict(kind='poi', id='other-user-poi')],
            previous_poi_ids=['other-user-poi']))
        self.assertEqual(next_turn['payload']['previous_entities'], [
            {'kind': 'outlet', 'id': 'window-1'}, {'kind': 'poi', 'id': 'floor-1'}])
        self.assertEqual(next_turn['payload']['previous_poi_ids'], ['floor-1'])
        self.assertNotIn('OTHER ACCOUNT', json.dumps(next_turn['payload']))
        other = self.store.begin('g', self.payload())
        self.assertEqual(other['payload']['previous_entities'], [])
        self.assertEqual(other['payload']['history'], [])

    def test_latest_success_without_cards_clears_previous_reference(self):
        first = self.store.begin('lyx', self.payload())
        self.finish(first, [dict(type='food', id='item-only')])
        second = self.store.begin('lyx', self.payload('request02'))
        self.assertEqual(second['payload']['previous_entities'], [])
        self.finish(second, [dict(type='place', id='old-place')])
        third = self.store.begin('lyx', self.payload('request03'))
        self.finish(third)
        fourth = self.store.begin('lyx', self.payload('request04'))
        self.assertEqual(fourth['payload']['previous_entities'], [])

    def test_context_does_not_add_persistent_conversation_fields(self):
        started = self.store.begin('lyx', self.payload(context={'selected': {'kind': 'outlet', 'id': 's0'}}))
        self.finish(started)
        conversation = self.store.conversations('lyx')[0]
        self.assertNotIn('context', conversation)
        self.assertNotIn('previous_entities', conversation)
        self.assertEqual(conversation['conditions'], {})

    def test_non_card_entities_survive_via_same_conversation_receipt(self):
        first = self.store.begin('lyx', self.payload())
        refs = [dict(kind='building', id='b0', name='old name'), dict(kind='outlet', id='s0')]
        self.store.finish(first['key'], [dict(type='result', data=dict(
            answer='测试关系', cards=[], conditions={}, context={'previous_entities': refs}))])
        second = self.store.begin('lyx', self.payload('request02'))
        self.assertEqual(second['payload']['previous_entities'], [
            {'kind': 'building', 'id': 'b0'}, {'kind': 'outlet', 'id': 's0'}])
        self.assertNotIn('old name', json.dumps(second['payload']['previous_entities']))
        with self.store.transaction() as data:
            self.assertNotIn('previous_entities', data['conversations']['lyx:conversation01'])

    def test_entities_result_fallback_when_context_field_is_absent(self):
        first = self.store.begin('lyx', self.payload())
        self.store.finish(first['key'], [dict(type='result', data=dict(answer='建筑', cards=[], conditions={},
            entities=[dict(ref={'kind': 'building', 'id': 'b0'}, name='测试楼')]))])
        second = self.store.begin('lyx', self.payload('request02'))
        self.assertEqual(second['payload']['previous_entities'], [{'kind': 'building', 'id': 'b0'}])

    def test_receipt_owner_and_conversation_must_both_match(self):
        first = self.store.begin('lyx', self.payload())
        self.store.finish(first['key'], [dict(type='result', data=dict(answer='关系', cards=[], conditions={},
            context={'previous_entities': [{'kind': 'building', 'id': 'secret-building'}]}))])
        with self.store.transaction() as data:
            receipt = data['requests'][first['key']]
            messages = data['conversations']['lyx:conversation01']['messages']
            receipt['owner'] = 'g'
            self.assertEqual(self.store._previous_entities(data, 'lyx', 'lyx:conversation01', messages), [])
            receipt['owner'] = 'lyx'
            receipt['conversation'] = 'lyx:other-conversation'
            self.assertEqual(self.store._previous_entities(data, 'lyx', 'lyx:conversation01', messages), [])

    def test_missing_receipt_keeps_legacy_card_reference(self):
        first = self.store.begin('lyx', self.payload())
        self.finish(first, [dict(type='food', id='item-1', outlet_id='s0', poi_id='p0')])
        with self.store.transaction() as data:
            # Model a legacy record that never had a persisted matching receipt.
            data['conversations']['lyx:conversation01']['messages'][0]['request_id'] = 'legacy-missing'
        second = self.store.begin('lyx', self.payload('request02'))
        self.assertEqual(second['payload']['previous_entities'], [
            {'kind': 'outlet', 'id': 's0'}, {'kind': 'poi', 'id': 'p0'}])


if __name__ == '__main__':
    unittest.main()
