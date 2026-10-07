"""Replace only this adapter when switching inference providers. No secret logging."""
import json
import os
import time
import urllib.request
import urllib.error
from typing import Protocol
from ..storage import ROOT, read


def config():
    return read(ROOT/'backend/agent/config.json')


class ModelError(RuntimeError):
    def __init__(self, message, code='MODEL_UNAVAILABLE', retryable=True):
        super().__init__(message)
        self.code=code
        self.retryable=retryable

    def event(self, request_id):
        return dict(type='error', code=self.code, message=str(self), text=str(self),
                    retryable=self.retryable, request_id=request_id)


class Model(Protocol):
    def complete(self, messages, tools, deadline): ...


class DeepSeekModel:
    def __init__(self):
        self.settings=config()
        self.key=os.environ.get('DEEPSEEK_API_KEY','')
        self.connection_status='unverified' if self.key else 'unconfigured'

    @property
    def configured(self):
        return bool(self.key)

    def complete(self, messages, tools, deadline):
        if not self.key: raise ModelError('生活助手暂未启用；你仍可浏览校园地点、查看资料或使用条件筛选。','MODEL_UNCONFIGURED',False)
        remaining=deadline-time.monotonic()
        if remaining<=0: raise ModelError('处理时间较长，请稍后重试；已有结果仍可查看。','MODEL_TIMEOUT')
        payload=dict(model=self.settings['model'],messages=messages,tools=tools,
            stream=False,thinking={'type':'disabled'},max_tokens=self.settings['max_output_tokens'],temperature=self.settings['temperature'])
        req=urllib.request.Request(self.settings['base_url'].rstrip('/')+'/chat/completions',
            data=json.dumps(payload,ensure_ascii=False).encode(),
            headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=min(45,remaining)) as response:
                result=json.load(response)
            message=result['choices'][0]['message']
            self.connection_status='connected'
            return message,result.get('usage',{})
        except urllib.error.HTTPError as e:
            self.connection_status='auth_failed' if e.code==401 else 'unavailable'
            code={401:'MODEL_AUTH',403:'MODEL_AUTH',402:'MODEL_QUOTA',429:'MODEL_BUSY'}.get(e.code,'MODEL_UNAVAILABLE')
            label='生活助手暂时无法连接，请联系管理员；地点浏览与条件筛选仍可使用。' if e.code in (401,402,403) else '生活助手服务繁忙，请稍后重试；已有结果仍可查看。'
            raise ModelError(label,code,e.code not in (401,402,403)) from None
        except TimeoutError:
            self.connection_status='unavailable'
            raise ModelError('等待回答超时，请稍后重试；已有结果仍可查看。','MODEL_TIMEOUT') from None
        except (OSError,ValueError,KeyError,IndexError):
            self.connection_status='unavailable'
            raise ModelError('模型连接或响应异常；原有结果仍可查看。') from None
