"""Restore two existing sports polygons; preserve every white_v4 mesh."""
import bpy
import json
import sys
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import build_blender_scene as base

targets=[ROOT/'output/bnu_campus_white_v5.blend',ROOT/'output/bnu_campus_web_white_v5.glb',ROOT/'assets/campus_assets_white_v5.json',ROOT/'output/scene_manifest_white_v5.json']
if any(p.exists() for p in targets):raise RuntimeError('Version output already exists; do not overwrite')
data=json.loads((ROOT/'assets/campus_assets_white_v4.json').read_text(encoding='utf-8'))
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'output/bnu_campus_white_v4.blend'))
def digest(obj):
    return hashlib.sha256(repr(([tuple(v.co) for v in obj.data.vertices],[tuple(p.vertices) for p in obj.data.polygons],tuple(tuple(r) for r in obj.matrix_world))).encode()).hexdigest()
before={o.name:digest(o) for o in bpy.context.scene.objects if o.type=='MESH'}
material=base.make_principled_material('V5_Existing_Sports_Footprint',(.08,.30,.28,1),.95)
added=[]
for ident in (267948582,267948583):
    s=next(s for s in data['surfaces'] if s['osm_id']==ident)
    coords=s['coords']
    assert all(abs(x)<452 and abs(y)<601 for x,y in coords)
    assert len(coords)>=3
    area=abs(sum(p[0]*q[1]-q[0]*p[1] for p,q in zip(coords,coords[1:]+coords[:1])))/2
    assert area>1
    z=max(base.terrain_height(data,x,y) for x,y in coords)+.42
    obj=base.polygon_mesh('Surface_V5_Restored_'+str(ident),coords,z,.10,material,material,bevel=0)
    obj['source']='existing white_v4 OSM footprint; display restored, not a new survey'
    obj['name_status']='existing name; current sport/count/lines unverified'
    s['display_note']='恢复已有轮廓；场地划线、当前用途和数量待现场核验；未从百度提取矢量'
    added.append(dict(osm_id=ident,name=s['name'] or '东操场东侧未命名运动场地',area_m2=round(area,2),coords=coords,mesh=obj.name))
after={o.name:digest(o) for o in bpy.context.scene.objects if o.type=='MESH'}
assert all(after.get(n)==h for n,h in before.items()),'Existing mesh or transform changed'
scene=bpy.context.scene;scene['edition']='white-v5-existing-sports-restored'
bpy.ops.wm.save_as_mainfile(filepath=str(targets[0]))
bpy.ops.export_scene.gltf(filepath=str(targets[1]),export_format='GLB',export_cameras=False,export_lights=False,export_apply=True)
targets[2].write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
report=dict(version='white-v5',coordinate_frame='white_v4 / local EPSG:32650',added_surfaces=added,added_buildings=0,protected_meshes=len(before),protected_geometry_check=True,heights_measured=False,polygons=sum(len(o.data.polygons) for o in scene.objects if o.type=='MESH'),trees=900,windows=None,limitations=['No new court markings or floor counts inferred','South-campus ownership and snack-street POIs remain under review'])
targets[3].write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
