"""Manual browser QA, isolated from all real submissions. Ctrl+C exits the server."""
import sys
import tempfile
import threading
import argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.storage import write
from contribution_server import make_server

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8793);args=parser.parse_args()
    life=Path(tempfile.mkdtemp(prefix='bnu-map-qa-'))
    write(life/'catalog.json',dict(schema_version=1,pois=[dict(id='qa-place',name='隔离测试地点（非真实采集）',source='test',status='verified',zone='campus',location=None)],shops=[],items=[],locations=[]))
    server=make_server(0,life,origin='https://qa.example',team_mode=True,admin_port=args.port)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    print(f'Isolated QA: http://127.0.0.1:{args.port}/',flush=True)
    server.admin_server.serve_forever()
