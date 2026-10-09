"""Same-origin HTTP adapter for the account repository and bounded agent loop."""
import json
import threading
from http.cookies import SimpleCookie
from .accounts import AccountError
from .agent.model import ModelError


class AccountHTTP:
    def __init__(self, store, agent, secure=False):
        self.store, self.agent, self.secure = store, agent, secure
        self.guard = threading.Lock()
        self.active = {}
        self.slots = threading.BoundedSemaphore(2)

    def token(self, handler):
        cookie = SimpleCookie()
        try:
            cookie.load(handler.headers.get('Cookie', ''))
            return cookie['bnu_session'].value if 'bnu_session' in cookie else ''
        except Exception:
            return ''

    def cookie(self, token, expire=False):
        return f'bnu_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={0 if expire else 28800}'+('; Secure' if self.secure else '')

    def dispatch(self, handler, path, data=None):
        if not (path.startswith('/api/account/') or path in ('/api/agent/chat', '/api/agent/cancel')):
            return False
        try:
            token = self.token(handler)
            post = handler.command == 'POST'
            if path == '/api/account/me' and not post:
                try:
                    session = self.store.authenticate(token, ready=False)
                    value = self.store.me(session)
                except AccountError as e:
                    if e.status != 401: raise
                    value = dict(enabled=True, user=None)
                handler.reply(200, value)
                return True
            if path == '/api/account/login' and post:
                token = self.store.login(data.get('name'), data.get('password'))
                handler.account_cookie = self.cookie(token)
                handler.reply(200, self.store.me(self.store.authenticate(token, ready=False)))
                return True
            session = self.store.authenticate(token, csrf=handler.headers.get('X-BNU-CSRF', '') if post else None,
                                              ready=path not in ('/api/account/password', '/api/account/logout'))
            name = session['name']
            value = None
            if path == '/api/account/conversations' and not post:
                value = dict(conversations=self.store.conversations(name))
            elif path == '/api/account/logout' and post:
                self.store.logout(token)
                handler.account_cookie = self.cookie('', True)
                value = dict(ok=True)
            elif path == '/api/account/password' and post:
                self.store.change_password(name, data.get('old'), data.get('password'))
                handler.account_cookie = self.cookie('', True)
                value = dict(ok=True, message='密码已修改，请使用新密码登录。')
            elif path == '/api/account/preferences' and post:
                value = self.store.preferences(name, data)
            elif path == '/api/account/conversations/delete' and post:
                self.store.remove_conversation(name, data.get('id'))
                value = dict(ok=True)
            elif path == '/api/account/admin/users' and not post:
                value = dict(users=self.store.admin_users(name))
            elif path == '/api/account/admin/status' and post:
                self.store.set_active(name, data.get('name'), data.get('active'))
                value = dict(ok=True)
            elif path == '/api/agent/cancel' and post:
                key = name+':'+self.store.identity(data.get('request_id'))
                with self.guard:
                    cancel = self.active.get(key)
                    if cancel: cancel.set()
                value = dict(cancel_requested=bool(cancel))
            elif path == '/api/agent/chat' and post:
                self.chat(handler, name, data)
                return True
            else:
                raise AccountError('接口不存在。', 'NOT_FOUND', 404)
            handler.reply(200, value)
        except AccountError as e:
            handler.reply(e.status, dict(error=str(e), message=str(e), code=e.code,
                                         retryable=e.code in ('REQUEST_ACTIVE', 'LOCAL_BUSY')))
        return True

    def chat(self, handler, name, data):
        if not getattr(self.agent.model, 'configured', True):
            raise AccountError('助手尚未连接模型；地图、菜单与条件筛选仍可用。', 'MODEL_UNCONFIGURED', 503)
        if not self.slots.acquire(False):
            raise AccountError('当前有两轮正在处理，请稍后再试。', 'LOCAL_BUSY', 429)
        key = None
        try:
            started = self.store.begin(name, data)
            if 'replay' in started:
                raw = ''.join(json.dumps(e, ensure_ascii=False)+'\n' for e in started['replay']).encode()
                handler.reply(200, raw, 'application/x-ndjson; charset=utf-8')
                return
            key = started['key']
            cancel = threading.Event()
            with self.guard: self.active[key] = cancel
            events = []
            connected = True
            try:
                handler.response_headers(200, 'application/x-ndjson; charset=utf-8'); handler.end_headers()
            except (BrokenPipeError, ConnectionError, TimeoutError):
                connected = False

            def send(event):
                nonlocal connected
                if not connected: return
                try:
                    handler.wfile.write((json.dumps(event, ensure_ascii=False, allow_nan=False)+'\n').encode())
                    handler.wfile.flush()
                except (BrokenPipeError, ConnectionError, TimeoutError):
                    connected = False

            def emit(event):
                events.append(event)
                # Commit the terminal answer before the browser refreshes history.
                if event.get('type') not in ('result', 'error'): send(event)

            try:
                self.agent.run(started['payload'], emit, cancelled=cancel.is_set)
            except ModelError as e:
                emit(e.event(data['request_id']))
            except ValueError:
                emit(dict(type='error', code='INVALID_INPUT', text='条件格式无效，请调整后重试。', retryable=False))
            except Exception:
                emit(dict(type='error', code='INTERNAL_ERROR', text='本轮未完成；可以浏览地图或稍后开始新一轮。', retryable=False))
            try:
                self.store.finish(key, events)
            except Exception:
                send(dict(type='error', code='STORAGE_UNCONFIRMED', text='记录保存尚未确认，请勿重复发送新请求；联系管理员检查服务磁盘。', retryable=False))
                return
            for event in events:
                if event.get('type') in ('result', 'error'): send(event)
        finally:
            if key:
                with self.guard: self.active.pop(key, None)
            self.slots.release()
