"""Manual, loopback-only UI fixture. No provider/key/account store is used.

Run with python -m tests.run_agent_preview. Output identifies the isolated fixture.
It reads the public catalogue through the same read-only adapter as the app.
"""
import json

from app_server import make_app_server
from backend.agent.controller import AgentController
from backend.agent.tools import CampusTools


class FixtureModel:
    configured = True
    connection_status = 'unverified'
    settings = {'model': 'isolated-ui-fixture-not-real-ai'}

    def complete(self, messages, tools, deadline):
        last_user = max(i for i, m in enumerate(messages) if m['role'] == 'user')
        tool_results = [json.loads(m['content']) for m in messages[last_user+1:] if m['role'] == 'tool']
        message = messages[last_user]['content']
        if not tool_results:
            system = messages[0]['content']
            marker = '地图选择与上轮对象（仅引用，不代表用户当前位置）：'
            context = json.loads(system.split(marker)[1].split('\n')[0])
            selected = context.get('selected')
            if selected:
                name = 'get_related_places' if '关系' in message or '相关' in message else 'get_entity'
                args = {'kind':selected['kind'],'entity_id':selected['id']}
                if name == 'get_related_places':args.update(mode='neighbors',limit=6)
            else:
                name,args = 'search_places',{'query':'新三'}
            return {'role':'assistant','content':None,'tool_calls':[{'id':'isolated-fixture-call','type':'function','function':{'name':name,'arguments':json.dumps(args,ensure_ascii=False)}}]},{}
        facts = tool_results[-1].get('answer_evidence',[])
        chosen = [f['id'] for f in facts if f['kind']=='fact'][:4]
        return {'role':'assistant','content':json.dumps({'style':'guide','evidence_ids':chosen,'follow_up':'locate'})},{}


if __name__ == '__main__':
    server = make_app_server(0, AgentController(FixtureModel(),CampusTools()))
    print(f'ISOLATED FIXTURE ONLY (NOT REAL AI): http://127.0.0.1:{server.server_port}/explore/',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
