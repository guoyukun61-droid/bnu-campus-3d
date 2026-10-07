"""Read-only audit: evidence confidence and actual mesh consistency are separate."""
import itertools
import json
import re
import struct
from collections import Counter
from .storage import ROOT, read
from .agent.presentation import public_address


def glb_document(path):
    raw=path.read_bytes()
    size,kind=struct.unpack_from('<II',raw,12)
    if raw[:4]!=b'glTF' or kind!=0x4E4F534A:raise ValueError('Invalid GLB')
    return json.loads(raw[20:20+size])


def matrix(node):
    if 'matrix' in node:
        m=node['matrix'];return [[m[c*4+r] for c in range(4)] for r in range(4)]
    x,y,z,w=node.get('rotation',[0,0,0,1]);s=node.get('scale',[1,1,1]);t=node.get('translation',[0,0,0])
    r=[[1-2*y*y-2*z*z,2*x*y-2*z*w,2*x*z+2*y*w],
       [2*x*y+2*z*w,1-2*x*x-2*z*z,2*y*z-2*x*w],
       [2*x*z-2*y*w,2*y*z+2*x*w,1-2*x*x-2*y*y]]
    return [[r[i][j]*s[j] for j in range(3)]+[t[i]] for i in range(3)]+[[0,0,0,1]]


def mesh_bounds(doc):
    result={}
    identity=matrix({})
    def visit(index,parent,building=None):
        node=doc['nodes'][index];local=matrix(node)
        world=[[sum(parent[r][k]*local[k][c] for k in range(4)) for c in range(4)] for r in range(4)]
        match=re.match(r'^Building_(\d+)(?:_|$)',node.get('name',''))
        if match:building=match.group(1)
        if building and 'mesh' in node:
            for primitive in doc['meshes'][node['mesh']]['primitives']:
                accessor=doc['accessors'][primitive['attributes']['POSITION']]
                if not {'min','max'}<=accessor.keys():continue
                points=itertools.product(*zip(accessor['min'],accessor['max']))
                for point in points:
                    p=list(point)+[1];v=[sum(world[r][c]*p[c] for c in range(4)) for r in range(3)]
                    if building not in result:result[building]=[v[:],v[:]]
                    result[building]=[[min(result[building][0][i],v[i]) for i in range(3)],[max(result[building][1][i],v[i]) for i in range(3)]]
        for child in node.get('children',[]):visit(child,world,building)
    for index in doc['scenes'][doc.get('scene',0)]['nodes']:visit(index,identity)
    return result


def building_audit(catalog=None):
    assets=read(ROOT/'assets/campus_assets_white_v6.json')
    earlier=read(ROOT/'data/life/map-audit/2026-09-24.json',{})
    south={str(b['building_id']):b for b in earlier.get('south_candidates',[])}
    document=glb_document(ROOT/'output/bnu_campus_web_white_v6.glb')
    bounds=mesh_bounds(document)
    sports=[dict(s,current_mesh_present=any(n.get('name')=='Surface_V5_Restored_'+str(s['osm_id']) for n in document['nodes'])) for s in earlier.get('sports',[])]
    rows=[]
    for b in assets['buildings']:
        ident=str(b['osm_id']);actual=bounds.get(ident)
        height=round(actual[1][1]-actual[0][1],3) if actual else None
        evidence={k:b[k] for k in ('correction_note','floor_status','height_status','geometry_status','identity_status','reference_observation','gf2_observation') if k in b}
        # Bounds include roof details, so mismatch is a review trigger, not proof of incorrect height.
        aligned=height is not None and abs(height-b['height'])<=.75
        status='待补实测或逐栋证据'
        text=json.dumps(evidence,ensure_ascii=False)
        if any(s in text for s in ('同组占位','错配','待现场核对','对应待复核')):status='身份或高度依据待核'
        elif b.get('correction_note'):status='已有修订，精度待核'
        if not actual:status='模型对象未匹配'
        if ident in south:status='南苑归属待核' if not south[ident].get('outside_display_m2') else '南苑归属及显示范围待核'
        rows.append(dict(id=ident,name=b.get('name') or b.get('audit_label') or '未命名建筑',
                         model_floors=b.get('floors'),model_height=b.get('height'),mesh_height=height,
                         mesh_present=bool(actual),parameter_consistent=aligned,status=status,evidence=evidence,
                         south_candidate=south.get(ident),bounds=actual))
    pois=[]
    for p in (catalog or {}).get('pois',[]):
        raw=p.get('address','');clean=public_address(raw)
        if raw!=clean or p.get('field_evidence'):
            pois.append(dict(id=p['id'],name=p.get('name'),raw_address=raw,public_address=clean,
                             building_id=p.get('building_id'),field_evidence=p.get('field_evidence',{})))
    return dict(model_version='white_v6',coordinate_frame='white_v4 / local EPSG:32650',
                summary=dict(total=len(rows),mesh_matched=sum(r['mesh_present'] for r in rows),
                             parameters_consistent=sum(r['parameter_consistent'] for r in rows),
                             correction_records=sum(bool(b.get('correction_note')) for b in assets['buildings']),
                             statuses=dict(Counter(r['status'] for r in rows))),
                buildings=rows,pois=pois,sports=sports,height_evidence=earlier.get('height_evidence'),
                notice='模型参数一致不代表实测准确。屋顶、台基可能影响包围盒高度；不凭差值自动改楼。GF2屋顶色不作立面依据。')
