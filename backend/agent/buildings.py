"""Public building identities, never raw geometry provenance or inferred floor counts."""
from backend.storage import ROOT, read

def building_directory():
    data=read(ROOT/'assets/campus_assets_white_v6.json')
    result=[]
    for b in data['buildings']:
        name=str(b.get('name') or '').strip()
        result.append({'id':str(b['osm_id']),'name':name or '未命名建筑',
            'description':f'{name}的建筑位置。选择美食、饮品等分类可查看已关联的店铺。' if name else '这栋建筑的名称与介绍尚待补充。',
            'source':'既有校园建筑目录','description_status':'仅有基础名录，详细介绍待补充'})
    return {'buildings':result,'model':'white_v7','shop_mode':'category_only'}
