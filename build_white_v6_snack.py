"""Bounded, source-labelled snack-street patch; preserve unrelated geometry."""
import bpy
import bmesh
import hashlib
import json
import math
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import build_blender_scene as base
from build_reference_v6 import Mesh, facades

targets=[ROOT/'output/bnu_campus_white_v6.blend',ROOT/'output/bnu_campus_web_white_v6.glb',ROOT/'assets/campus_assets_white_v6.json',ROOT/'output/scene_manifest_white_v6.json']
if any(p.exists() for p in targets):raise RuntimeError('Version output exists; refuse to overwrite')
data=json.loads((ROOT/'assets/campus_assets_white_v5.json').read_text(encoding='utf8'))
patch=json.loads((ROOT/'assets/snack_blocks_v6.json').read_text(encoding='utf8'))
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'output/bnu_campus_white_v5.blend'))

def digest(obj):
    return hashlib.sha256(repr(([tuple(v.co) for v in obj.data.vertices],[tuple(p.vertices) for p in obj.data.polygons],tuple(tuple(r) for r in obj.matrix_world))).encode()).hexdigest()

def contains(coords,x,y,margin=1.5):
    # Polygon containment plus a small facade buffer; only dedicated facade meshes use it.
    inside=False
    for a,b in zip(coords,coords[1:]+coords[:1]):
        dx,dy=b[0]-a[0],b[1]-a[1];den=dx*dx+dy*dy
        t=max(0,min(1,((x-a[0])*dx+(y-a[1])*dy)/den)) if den else 0
        if math.hypot(x-a[0]-t*dx,y-a[1]-t*dy)<=margin:return True
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:inside=not inside
    return inside

before={o.name:digest(o) for o in bpy.context.scene.objects if o.type=='MESH'}
lookup={b['osm_id']:b for b in data['buildings']}
white=bpy.data.materials['White_Architectural_Clay']
allowed=set();changes=[];regions=[]
for change in patch['changes']:
    b=lookup[change['osm_id']];o=bpy.data.objects['Building_'+str(b['osm_id'])]
    assert o.type=='MESH' and not o.children,'Unexpected building structure'
    z=min(v.co.z for v in o.data.vertices);old=b['height']
    regions.append((b['coords'],z,old))
    for v in o.data.vertices:v.co.z=z+(v.co.z-z)*change['height']/old
    allowed.add(o.name)
    changes.append(dict(osm_id=b['osm_id'],old_height=old,old_floors=b['floors'],height=change['height'],floors=change['floors']))
    b.update(height=change['height'],floors=change['floors'],audit_label=change['audit_label'],floor_status='用户片区两层反馈；逐体块对应待复核',height_status=patch['height_policy'],identity_status=change['identity_status'])
    b['correction_note']='2026-09-24逐栋核对：'+b['floor_status']+'；'+b['height_status']+'；'+b['identity_status']
    o['height_m']=b['height'];o['floors_estimated']=b['floors'];o['correction_note']=b['correction_note']

# Remove only old placeholder facade faces in the five target footprints, then draw
# two-storey schematic facade rows. No unrelated vertex is moved or removed.
detail_names={'Facade_Window_Panels','Facade_Frames','Roof_Parapets','Rooftop_Equipment','Facade_Bands'}
detail_audit=[]
for o in bpy.context.scene.objects:
    if o.type!='MESH' or o.name not in detail_names:continue
    selected=[]
    for p in o.data.polygons:
        c=p.center
        if any(z-.2<=c.z<=z+h+3 and contains(coords,c.x,c.y) for coords,z,h in regions):selected.append(p.index)
    if not selected:continue
    original_vertices=[tuple(v.co) for v in o.data.vertices]
    keep_faces=[tuple(p.vertices) for p in o.data.polygons if p.index not in set(selected)]
    bm=bmesh.new();bm.from_mesh(o.data);bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm,geom=[bm.faces[i] for i in selected],context='FACES_ONLY')
    bm.to_mesh(o.data);bm.free();o.data.update()
    assert original_vertices==[tuple(v.co) for v in o.data.vertices]
    assert keep_faces==[tuple(p.vertices) for p in o.data.polygons]
    allowed.add(o.name);detail_audit.append(dict(mesh=o.name,removed_target_faces=len(selected),outside_faces_preserved=True))
for change,(coords,z,old) in zip(patch['changes'],regions):
    o=bpy.data.objects['Building_'+str(change['osm_id'])]
    detail=Mesh('Snack_V6_Detail_'+str(change['osm_id']),{k:white for k in ['ref_trim','ref_glass','ref_white']})
    facades(detail,coords,z,change['height'],2,'ref_white');detail.finish(o)

for info in patch['retained']:
    b=lookup[info['osm_id']]
    b.update({k:v for k,v in info.items() if k not in {'osm_id','height','floors'}})
    b['correction_note']='校方餐饮指南确认一至四层；保留四层和13 m表现高度，非实测。'+info['geometry_status']

for entry in patch['added']:
    b=dict(entry);coords=b['coords']
    b['area']=abs(sum(p[0]*q[1]-q[0]*p[1] for p,q in zip(coords,coords[1:]+coords[:1])))/2
    b['roof_shape']='flat';b['audit_label']=b['name'];b['floor_status']='未知，未推断';b['correction_note']=b['geometry_status']+'；'+b['height_status']
    z=max(base.terrain_height(data,*p) for p in coords)+.35
    o=base.polygon_mesh('Building_'+str(b['osm_id']),coords,z,b['height'],white,white,bevel=.08)
    o['source_id']=b['source_id'];o['correction_note']=b['correction_note'];data['buildings'].append(b)

after={o.name:digest(o) for o in bpy.context.scene.objects if o.type=='MESH'}
protected=[n for n in before if n not in allowed]
assert all(after.get(n)==before[n] for n in protected),'Unrelated geometry changed'
assert all(math.isfinite(c) for o in bpy.context.scene.objects if o.type=='MESH' for v in o.data.vertices for c in v.co)
scene=bpy.context.scene;scene['edition']='white-v6-snack-local-audit'
bpy.ops.wm.save_as_mainfile(filepath=str(targets[0]))
bpy.ops.export_scene.gltf(filepath=str(targets[1]),export_format='GLB',export_cameras=False,export_lights=False,export_apply=True)
targets[2].write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
report=dict(version='white-v6',coordinate_frame=patch['coordinate_frame'],changes=changes,added_buildings=patch['added'],protected_meshes=len(protected),protected_geometry_check=True,detail_audit=detail_audit,heights_measured=False,polygons=sum(len(o.data.polygons) for o in scene.objects if o.type=='MESH'),trees=900,windows=None,limitations=['Low-rise user report is area-level, not a measured per-building survey','New north block identity and floor count unknown','Xinlequn northern footprint discrepancy remains unmeasured'])
targets[3].write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(report,ensure_ascii=False))
