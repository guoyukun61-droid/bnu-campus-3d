"""Public building identities, never raw geometry provenance or inferred floor counts."""
from backend.storage import ROOT, read
from backend.campus_content import enrich_buildings

def building_directory():
    data=read(ROOT/'assets/campus_assets_white_v6.json')
    result=[]
    for b in enrich_buildings(data['buildings']):
        name=str(b.get('name') or '').strip()
        result.append({'id':str(b['osm_id']),'name':name or '未命名建筑',
            'description':b['description'],
            'source':{'official_public_source':'学校官网用途短摘要','inferred':'推测介绍，待核实'}.get(b.get('content_origin'),'既有校园建筑目录'),
            'description_status':b['description_status']})
    # Preserve the legacy five-field whitelist. Full evidence is in /api/app/v2/.
    return {'buildings':result,'model':'white_v7','shop_mode':'category_only'}
