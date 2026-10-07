"""Bounded POI audit. AK is read from environment, never saved or printed."""
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent

def legacy_audit():
    key = os.environ.get('BAIDU_MAP_AK', '').strip()
    if not key:
        raise SystemExit('BAIDU_MAP_AK is not configured')
    queries = ['兰蕙餐厅', '兰蕙公寓', '北京师范大学留学生公寓', '北京师范大学新乐群食堂']
    audit = {'retrieved_at': datetime.now(timezone.utc).isoformat(),
             'source': 'Baidu Place API v2', 'crs': 'BD-09 longitude/latitude',
             'geometry_verified': False, 'queries': []}
    for query in queries:
        params = dict(query=query, region='北京', city_limit='true', output='json',
                      scope=1, page_size=20, page_num=0, ak=key)
        try:
            with urlopen('https://api.map.baidu.com/place/v2/search?' + urlencode(params), timeout=25) as response:
                result = json.load(response)
        except Exception as exc:
            # Exception messages can contain the full URL and its secret.
            raise SystemExit('Baidu request failed: ' + type(exc).__name__) from None
        if result.get('status') != 0:
            raise SystemExit('Baidu API status: ' + str(result.get('status')))
        rows = [{k: row[k] for k in ('uid', 'name', 'address', 'location', 'area') if k in row}
                for row in result.get('results', [])]
        audit['queries'].append({'query': query, 'total': result.get('total'), 'results': rows})
        print(json.dumps({'query': query, 'results': rows}, ensure_ascii=False))
    target = ROOT / 'data/baidu_poi_audit_20260921.json'
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Saved private POI audit; no AK stored; no geometry changed.')

if __name__ == '__main__':
    from backend.collector import main
    main()
