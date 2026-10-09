"""Private account repository. No model secrets, static routes or legacy data migration."""
import copy
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from .storage import read, write, ROOT, now
from .agent.candidates import merge_conditions
from .agent.context import validate_context, previous_entities_from_cards

USERS = ('g', 'kdy', 'lyx', 'ljz', 'll')
ITERATIONS = 600_000


class AccountError(Exception):
    def __init__(self, message, code='INVALID_INPUT', status=400):
        super().__init__(message)
        self.code, self.status = code, status


def password_hash(password, *, temporary=False):
    minimum = 6 if temporary else 12
    if not isinstance(password, str) or not minimum <= len(password) <= 128:
        raise AccountError(f'密码须为 {minimum}–128 个字符。')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return dict(salt=salt, digest=digest, iterations=ITERATIONS)


def verify(password, saved):
    if not isinstance(password, str) or len(password) > 128:
        return False
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(saved['salt']), saved['iterations']).hex()
    return hmac.compare_digest(digest, saved['digest'])


def lock_file(handle, blocking=True):
    handle.seek(0)
    if os.name == 'nt':
        import msvcrt
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))


def unlock_file(handle):
    handle.seek(0)
    if os.name == 'nt':
        import msvcrt
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle, fcntl.LOCK_UN)


class AccountStore:
    def __init__(self, root=None):
        self.root = Path(root or ROOT / 'data/life/accounts')
        self.path = self.root / 'accounts.json'
        self.guard = threading.RLock()
        self.sessions, self.attempts = {}, []
        self.lease = None
        # Equal work for unknown accounts; no plaintext dummy credential is kept.
        self.dummy = dict(salt='00'*16, digest='00'*32, iterations=ITERATIONS)

    @contextmanager
    def transaction(self):
        with self.guard:
            self.root.mkdir(parents=True, exist_ok=True)
            with (self.root / 'write.lock').open('a+b') as handle:
                if handle.tell() == 0:
                    handle.write(b'0'); handle.flush()
                lock_file(handle)
                try:
                    data = read(self.path, dict(users={}, conversations={}, requests={}, usage={}))
                    yield data
                    write(self.path, data)
                finally:
                    unlock_file(handle)

    def start(self):
        """Only one account HTTP service may own this store; setup CLI uses transactions."""
        self.root.mkdir(parents=True, exist_ok=True)
        handle = (self.root / 'server.lock').open('a+b')
        if handle.tell() == 0:
            handle.write(b'0'); handle.flush()
        try:
            lock_file(handle, False)
        except OSError:
            handle.close()
            raise RuntimeError('另一个账号服务正在使用此目录；未启动第二个服务。') from None
        self.lease = handle
        with self.transaction() as data:
            for key, receipt in data['requests'].items():
                if receipt['state'] == 'pending':
                    self._finish(data, key, [dict(type='error', code='INTERRUPTED', text='服务重启中断了本轮；没有自动重新调用模型。', retryable=False)])

    def close(self):
        if self.lease:
            unlock_file(self.lease); self.lease.close(); self.lease = None

    def provision(self, name, password, reset=False, *, temporary=False):
        if name not in USERS:
            raise AccountError('仅支持预先约定的五个账号。')
        encoded = password_hash(password, temporary=temporary)
        with self.transaction() as data:
            old = data['users'].get(name)
            if old and not reset:
                raise AccountError('账号已存在；需显式选择重置，原聊天不会删除。', 'CONFLICT', 409)
            data['users'][name] = dict(old or {}, password=encoded, active=True, must_change=True,
                                      revision=(old or {}).get('revision', 0)+1,
                                      preferences=(old or {}).get('preferences', dict(enabled=False, version=0)))

    def login(self, name, password):
        name = name if isinstance(name, str) else ''
        with self.guard:
            t = time.monotonic()
            self.attempts = [(at, n) for at, n in self.attempts if t-at < 300]
            if len(self.attempts) >= 30 or sum(n == name for _, n in self.attempts) >= 8:
                raise AccountError('登录尝试过多，请五分钟后再试。', 'LOGIN_LIMIT', 429)
            self.attempts.append((t, name))
            with self.transaction() as data:
                user = data['users'].get(name)
                valid = verify(password, user['password'] if user else self.dummy)
                if not valid or not user or not user['active']:
                    raise AccountError('账号或密码不正确，或账号尚未启用。', 'LOGIN_FAILED', 401)
                token = secrets.token_urlsafe(32)
                self.sessions[hashlib.sha256(token.encode()).hexdigest()] = dict(
                    name=name, revision=user['revision'], expires=time.time()+8*3600, csrf=secrets.token_urlsafe(32))
                # Bound memory, never evict a credential into a log.
                self.sessions = {k: v for k, v in self.sessions.items() if v['expires'] > time.time()}
                return token

    def authenticate(self, token, csrf=None, ready=True):
        with self.guard:
            session = self.sessions.get(hashlib.sha256(token.encode()).hexdigest())
            if not session or session['expires'] <= time.time():
                raise AccountError('请登录后使用个人对话。', 'AUTH_REQUIRED', 401)
            with self.transaction() as data:
                user = data['users'].get(session['name'])
                if not user or not user['active'] or user['revision'] != session['revision']:
                    raise AccountError('登录已失效，请重新登录。', 'AUTH_REQUIRED', 401)
                if csrf is not None and not hmac.compare_digest(session['csrf'], csrf):
                    raise AccountError('页面验证失效，请刷新后重试。', 'CSRF', 403)
                if ready and user['must_change']:
                    raise AccountError('首次登录请先修改临时密码。', 'PASSWORD_CHANGE_REQUIRED', 403)
                return copy.deepcopy(session)

    def logout(self, token):
        with self.guard:
            self.sessions.pop(hashlib.sha256(token.encode()).hexdigest(), None)

    def change_password(self, name, old, new):
        encoded = password_hash(new)
        with self.transaction() as data:
            user = data['users'][name]
            if not verify(old, user['password']):
                raise AccountError('原密码不正确。', 'PASSWORD_INVALID', 403)
            if verify(new, user['password']):
                raise AccountError('新密码不能与临时密码相同。')
            user.update(password=encoded, must_change=False, revision=user['revision']+1)

    @staticmethod
    def day():
        return datetime.now(timezone(timedelta(hours=8))).date().isoformat()

    def usage(self, data, name):
        counts = data['usage'].get(self.day(), {})
        return dict(date=self.day(), used=counts.get(name, 0), limit=20, team_used=sum(counts.values()), team_limit=50)

    def me(self, session):
        with self.transaction() as data:
            u = data['users'][session['name']]
            return dict(enabled=True, user=session['name'], admin=session['name']=='g',
                        must_change=u['must_change'], csrf=session['csrf'],
                        preferences=u['preferences'], usage=self.usage(data, session['name']))

    def preferences(self, name, value):
        if not isinstance(value.get('enabled'), bool) or type(value.get('version')) is not int:
            raise AccountError('偏好版本或启用状态无效。')
        patch = value.get('values', {})
        if not isinstance(patch, dict) or set(patch)-{'budget', 'taste', 'avoid'}:
            raise AccountError('仅支持预算、口味和忌口。')
        if 'budget' in patch and patch['budget'] is not None:
            budget = patch['budget']
            if isinstance(budget, bool) or not isinstance(budget, (float, int)) or not math.isfinite(budget) or not 0 < budget <= 10000:
                raise AccountError('预算须在 0–10000 元之间。')
        for key in ('taste', 'avoid'):
            if key in patch and (not isinstance(patch[key], list) or len(patch[key]) > 10 or any(not isinstance(x, str) or not 0 < len(x) <= 40 for x in patch[key])):
                raise AccountError('口味、忌口最多各 10 项，每项不超过 40 字。')
        clean = merge_conditions({}, patch)
        with self.transaction() as data:
            u = data['users'][name]
            if u['preferences']['version'] != value['version']:
                raise AccountError('偏好已在另一页面修改，请刷新再编辑。', 'CONFLICT', 409)
            u['preferences'] = dict(enabled=value['enabled'], values=clean, version=value['version']+1,
                                    updated_at=now(), source='user_confirmed')
            return u['preferences']

    def admin_users(self, actor):
        if actor != 'g':
            raise AccountError('仅管理员可以管理账号。', 'FORBIDDEN', 403)
        with self.transaction() as data:
            return [dict(name=n, active=u['active'], initialized=True, must_change=u['must_change'], usage=self.usage(data, n)) for n, u in data['users'].items()]

    def set_active(self, actor, target, active):
        if actor != 'g' or target == 'g':
            raise AccountError('无权执行此账号操作。', 'FORBIDDEN', 403)
        if type(active) is not bool:
            raise AccountError('状态无效。')
        with self.transaction() as data:
            if target not in data['users']:
                raise AccountError('账号不存在。', 'NOT_FOUND', 404)
            u = data['users'][target]
            u.update(active=active, revision=u['revision']+1)

    def conversations(self, name):
        with self.transaction() as data:
            return sorted((copy.deepcopy(c) for c in data['conversations'].values() if c['owner']==name),
                          key=lambda c:c['updated_at'], reverse=True)

    @staticmethod
    def identity(value):
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}', value):
            raise AccountError('对话或请求 ID 无效。')
        return value

    def remove_conversation(self, name, ident):
        key = name+':'+self.identity(ident)
        with self.transaction() as data:
            if any(r['conversation']==key and r['state']=='pending' for r in data['requests'].values()):
                raise AccountError('请等本轮处理结束再删除。', 'REQUEST_ACTIVE', 409)
            data['conversations'].pop(key, None)
            # Keep only request tombstones; deleted text must not be replayed.
            for r in data['requests'].values():
                if r['conversation']==key:
                    r['events'] = [dict(type='error', code='DELETED', text='此对话已删除，请开始新对话。', retryable=False)]
                    r.pop('payload', None)

    @staticmethod
    def _previous_entities(data, name, ckey, messages):
        """Recover the latest successful turn, including newer non-card results.

        Receipts are existing account-owned containers, not a new history store.
        Old/deleted receipts or older result shapes safely fall back to cards.
        """
        for index in range(len(messages)-1, -1, -1):
            message = messages[index]
            if message.get('role') != 'assistant' or message.get('error'):
                continue
            fallback = previous_entities_from_cards(message.get('cards', []))
            previous = messages[index-1] if index else {}
            ident = previous.get('request_id') if previous.get('role') == 'user' else None
            receipt = data['requests'].get(name+':'+ident) if isinstance(ident, str) else None
            if (not receipt or receipt.get('owner') != name or receipt.get('conversation') != ckey
                    or receipt.get('state') != 'done'):
                return fallback
            terminal = next((e for e in reversed(receipt.get('events', []))
                             if e.get('type') in ('result', 'error')), {})
            result = terminal.get('data') if terminal.get('type') == 'result' else None
            if not isinstance(result, dict):
                return fallback
            context = result.get('context')
            refs = context.get('previous_entities') if isinstance(context, dict) else None
            if isinstance(refs, list):
                # Ignore server display metadata; only IDs are re-resolved next turn.
                cards = [dict(ref={k: ref.get(k) for k in ('kind', 'id')})
                         for ref in refs[:12] if isinstance(ref, dict)]
                return previous_entities_from_cards(cards)
            entities = result.get('entities')
            if isinstance(entities, list):
                references = previous_entities_from_cards([dict(ref=e.get('ref'))
                    for e in entities[:12] if isinstance(e, dict)])
                if references:
                    return previous_entities_from_cards(message.get('cards', []) + [dict(ref=r) for r in references])
            return fallback
        return []

    def begin(self, name, request):
        ident, cid = self.identity(request.get('request_id')), self.identity(request.get('conversation_id'))
        text, mode = request.get('message'), request.get('mode', 'real')
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000 or mode not in ('real', 'demo'):
            raise AccountError('请输入 1–2000 字的问题。')
        patch = request.get('conditions', {})
        merge_conditions({}, patch)  # Validate before reserving quota.
        context = validate_context(request.get('context'))
        clean = dict(request_id=ident, conversation_id=cid, message=text.strip(), conditions=patch, mode=mode)
        # Empty context preserves digests for requests saved before this feature.
        if context['selected'] is not None:
            clean['context'] = context
        digest = hashlib.sha256(json.dumps(clean, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        key, ckey = name+':'+ident, name+':'+cid
        with self.transaction() as data:
            receipt = data['requests'].get(key)
            if receipt:
                if receipt['digest'] != digest:
                    raise AccountError('重复请求与原内容不一致。', 'CONFLICT', 409)
                if receipt['state']=='pending':
                    raise AccountError('这条请求仍在处理，请稍后重试读取结果。', 'REQUEST_ACTIVE', 409)
                return dict(replay=copy.deepcopy(receipt['events']), key=key)
            if any(r['owner']==name and r['state']=='pending' for r in data['requests'].values()):
                raise AccountError('你还有一轮正在处理，请先等待或停止。', 'REQUEST_ACTIVE', 409)
            usage = self.usage(data, name)
            if usage['used'] >= 20 or usage['team_used'] >= 50:
                raise AccountError('今日试用额度已用完；明天上海时间零点恢复。地图和条件筛选仍可用。', 'QUOTA_EXCEEDED', 429)
            if ckey not in data['conversations'] and sum(c['owner']==name for c in data['conversations'].values())>=100:
                raise AccountError('最多保留 100 个对话，请先删除不需要的记录。', 'HISTORY_LIMIT', 409)
            conv = data['conversations'].setdefault(ckey, dict(id=cid, owner=name, title=text[:24], messages=[], conditions={}, overrides={}, mode=mode, updated_at=now()))
            if len(conv['messages']) >= 200:
                raise AccountError('本对话已到 100 轮，请开启新对话。', 'HISTORY_LIMIT', 409)
            pref = data['users'][name]['preferences']
            conditions = pref.get('values', {}) if pref.get('enabled') else {}
            overrides = dict(conv.get('overrides', {}), **patch)
            conditions = merge_conditions(conditions, overrides)
            previous_entities = self._previous_entities(data, name, ckey, conv['messages'])
            previous = [ref['id'] for ref in previous_entities if ref['kind'] == 'poi'][:3]
            payload = dict(clean, conditions=conditions, history=[dict(role=m['role'], content=m['content']) for m in conv['messages'] if not m.get('error')][-12:],
                           previous_poi_ids=previous, context=context, previous_entities=previous_entities)
            data['requests'][key] = dict(owner=name, conversation=ckey, digest=digest, state='pending', payload=payload, overrides=overrides, events=[])
            counts = data['usage'].setdefault(self.day(), {})
            counts[name] = counts.get(name, 0)+1
            conv['messages'].append(dict(role='user', content=text.strip(), request_id=ident))
            conv['updated_at'] = now()
            return dict(payload=payload, key=key)

    def _finish(self, data, key, events):
        receipt = data['requests'][key]
        if receipt['state'] != 'pending':
            return
        conv = data['conversations'][receipt['conversation']]
        terminal = next((e for e in reversed(events) if e.get('type') in ('result', 'error')), None)
        if terminal is None:
            terminal = dict(type='error', code='INTERRUPTED', text='未收到完成结果，请开始新一轮。', retryable=False)
            events.append(terminal)
        result = terminal.get('data', {})
        error = terminal['type']=='error'
        conv['messages'].append(dict(role='assistant', content=terminal.get('text', '本轮未完成') if error else result.get('answer', ''),
                                     cards=result.get('cards', []), error=error, failure=terminal if error else None))
        # Only changed conditions become conversation overrides; defaults remain editable.
        overrides = receipt['overrides']
        before = receipt['payload']['conditions']
        after = result.get('conditions', before)
        for field in set(before)|set(after):
            if before.get(field) != after.get(field):
                overrides[field] = after.get(field)
        conv.update(conditions=after, overrides=overrides, mode=receipt['payload']['mode'], updated_at=now())
        receipt.update(state='done', events=copy.deepcopy(events))
        receipt.pop('payload', None)
        receipt.pop('overrides', None)

    def finish(self, key, events):
        with self.transaction() as data:
            self._finish(data, key, events)
