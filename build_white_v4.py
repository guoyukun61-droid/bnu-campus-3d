"""Add missing geometry from supplied Baidu screenshots + GF2 interpretation.
Existing building meshes are protected. New IDs are local, not real OSM IDs.
"""
import bpy, json, sys, hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import build_blender_scene as base
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'output/bnu_campus_white_v3.blend'))
data=json.loads((ROOT/'assets/campus_assets_white_v3.json').read_text(encoding='utf-8'))
patch=json.loads((ROOT/'assets/missing_blocks_v4.json').read_text(encoding='utf-8'))
white=bpy.data.materials['White_Architectural_Clay']
def digest(o):return hashlib.sha256(repr(([tuple(v.co) for v in o.data.vertices],[tuple(p.vertices) for p in o.data.polygons])).encode()).hexdigest()
before={o.name:digest(o) for o in bpy.context.scene.objects if o.type=='MESH'}
for b in patch['buildings']:
    parent=bpy.data.objects.new('Building_'+str(b['osm_id']),None);bpy.context.collection.objects.link(parent)
    parent['source_id']=b['source_id'];parent['height_status']=patch['height_status']
    for i,part in enumerate(b['parts']):
        z=max(base.terrain_height(data,*p) for p in part['coords'])+.35
        obj=base.polygon_mesh('Added_V4_'+str(b['osm_id'])+'_'+str(i),part['coords'],z,part['height'],white,white,bevel=.10)
        obj.parent=parent;obj['part_name']=part['name']
    # Representative footprint is the main body; all actual parts are preserved below.
    b['coords']=b['parts'][0]['coords'];b['area']=sum(abs(sum(p[0]*q[1]-q[0]*p[1] for p,q in zip(part['coords'],part['coords'][1:]+part['coords'][:1])))/2 for part in b['parts'])
    b['roof_shape']='flat';b['correction_note']=patch['source']+'。'+patch['height_status']+'；内部庭院保持留空，附楼连接处待现场复核。'
    data['buildings'].append(b)
after={o.name:digest(o) for o in bpy.context.scene.objects if o.type=='MESH'}
assert all(after.get(n)==h for n,h in before.items()),'Existing mesh changed'
scene=bpy.context.scene;scene['edition']='white-v4-missing-blocks'
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'output/bnu_campus_white_v4.blend'))
bpy.ops.export_scene.gltf(filepath=str(ROOT/'output/bnu_campus_web_white_v4.glb'),export_format='GLB',export_cameras=False,export_lights=False,export_apply=True)
(ROOT/'assets/campus_assets_white_v4.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
report={'version':'white-v4','added_buildings':2,'added_parts':7,'protected_meshes':len(before),'protected_geometry_check':True,'baidu_reference':'user-supplied screenshots; not downloaded vectors','heights_measured':False,'polygons':sum(len(o.data.polygons) for o in scene.objects if o.type=='MESH'),'trees':900,'windows':None}
(ROOT/'output/scene_manifest_white_v4.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report))
