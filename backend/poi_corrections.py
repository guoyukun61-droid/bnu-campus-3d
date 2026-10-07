"""User-confirmed labels and invalidated positions; keep raw source and old values."""
import copy
import json
from .storage import ROOT, read, write, now
from .adapters import CatalogAdapter
from .contribution import digest, overlay
from .import_field_batch import DIRECTORY

BATCH='poi-corrections-20261002'
AED='baidu-ed209310ccb7ad6f0bf5eb8a'
JIEDIAN='baidu-fd4578cac9c9ce26f50e772e'


def corrected_state(original,catalog,at):
    if any(a.get('batch')==BATCH for a in original.get('audit',[])):
        raise ValueError('This correction is already applied')
    by_id={p['id']:p for p in catalog['pois']}
    if 'AED' not in by_id[AED]['name'] or '街电' not in by_id[JIEDIAN]['name']:
        raise ValueError('Target identity changed; review before applying')
    result=copy.deepcopy(original)
    changes={
        AED:dict(name='邱季端体育场',category='sports',
                 original_name=by_id[AED]['name'],
                 location_description='地图场所名称按用户2026-10-02说明修正；原百度记录是AED设备点，不表示本次核验了AED设备位置、场地边界或建筑身份。'),
        JIEDIAN:dict(location=None,map_point=None,location_crs=None,building_id=None,
                     building_link_status='unlinked',zone='unknown',location_source='user_reported_incorrect_20261002',
                     location_description='用户确认原地图位置错误，新位置待点选；资料地址为学院南路16号、北师大南门斜对面。未自动采用餐厅坐标。')
    }
    for ident,patch in changes.items():
        target=result.setdefault('published',{}).setdefault('pois',{}).setdefault(ident,{})
        for field,value in patch.items():
            target[field]=value
            target.setdefault('field_evidence',{})[field]=dict(
                source='user_correction_20261002',reported_at=at,observed_at=None,reviewed_at=at,
                batch=BATCH,previous_value=copy.deepcopy(by_id[ident].get(field)),
                evidence='用户明确更正地图场所名称' if ident==AED else '用户明确指出位置错误，尚未提供新坐标')
        target['updated_at']=at
    result['version']+=1
    result['audit'].append(dict(action='poi_name_and_invalid_location_correction',batch=BATCH,actor='g',at=at,ids=[AED,JIEDIAN]))
    overlay(catalog,result)
    return result


def prepare():
    original=read(ROOT/'data/life/contributions/state.json')
    catalog=CatalogAdapter(ROOT/'data/life',ROOT/'data/campus_info.sqlite3').snapshot()
    at=now();result=corrected_state(original,catalog,at)
    stage=DIRECTORY/(BATCH+'-'+at.replace(':','-'))
    report=dict(batch=BATCH,stage=str(stage),original_digest=digest(original),result_digest=digest(result),
                approved=[],conflicts=[],drafts=[],hours=[],menu_counts={'imported':0},corrected_ids=[AED,JIEDIAN])
    write(stage/'result-state.json',result)
    write(stage/'report.json',report)
    write(stage/'before-pois.json',[p for p in catalog['pois'] if p['id'] in (AED,JIEDIAN)])
    print(json.dumps(dict(stage=str(stage),corrected_ids=report['corrected_ids']),ensure_ascii=False))


if __name__=='__main__':prepare()
