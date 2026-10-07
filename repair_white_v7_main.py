"""Fix self-intersecting rear footprint; preserve other evaluated meshes exactly."""
import bpy, json, hashlib, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from backend.main_geometry import clip_north
from backend.glb_patch import patch_meshes
from build_reference_v6 import Mesh, facades

def digest(o):
    deps=bpy.context.evaluated_depsgraph_get()
    evaluated=o.evaluated_get(deps);m=evaluated.to_mesh()
    result=hashlib.sha256(repr(([tuple(v.co) for v in m.vertices],[tuple(p.vertices) for p in m.polygons],list(o.matrix_world))).encode()).hexdigest()
    evaluated.to_mesh_clear()
    return result

bpy.ops.wm.open_mainfile(filepath=str(ROOT/'output/bnu_campus_white_v6.blend'))
targets={'Building_267948584','Reference_Detail_267948584'}
before={o.name:digest(o) for o in bpy.context.scene.objects if o.type=='MESH' and o.name not in targets}
data=json.loads((ROOT/'assets/campus_assets_white_v6.json').read_text(encoding='utf-8'))
b=next(b for b in data['buildings'] if b['osm_id']==267948584)
coords=clip_north(b['coords']);n=len(coords)
body=bpy.data.objects['Building_267948584'];z=min(v.co.z for v in body.data.vertices)
verts=[(x,y,z+h) for h in (0,22) for x,y in coords]
faces=[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
mesh=bpy.data.meshes.new('Main_Rear_Clipped_V7');mesh.from_pydata(verts,[],faces)
for mat in body.data.materials:mesh.materials.append(mat)
assert not mesh.validate();mesh.update();body.data=mesh
# Preserve the original 12 boxes (72 faces), rebuild only facade panels tied to invalid edges.
detail=bpy.data.objects['Reference_Detail_267948584'];old=detail.data
assert len(old.polygons)>72 and all(len(p.vertices)==4 for p in list(old.polygons)[:72])
white=old.materials[0]
m=Mesh('Main_Detail_V7',{key:white for key in ('ref_sand','ref_roof','ref_trim','ref_dark','ref_glass')})
for p in list(old.polygons)[:72]:m.face([tuple(old.vertices[i].co) for i in p.vertices],'ref_sand')
facades(m,coords,z,22,6,'ref_sand')
new=bpy.data.meshes.new('Main_Detail_V7');new.from_pydata(m.v,[],m.f);new.materials.append(white)
assert not new.validate();new.update();detail.data=new
after={o.name:digest(o) for o in bpy.context.scene.objects if o.type=='MESH' and o.name not in targets}
assert before==after,'Unrelated evaluated geometry changed'
bpy.context.scene['edition']='white-v7-main-topology-repair'
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'output/bnu_campus_white_v7.blend'))
bpy.ops.export_scene.gltf(filepath=str(ROOT/'output/bnu_campus_web_white_v7.glb'),export_format='GLB',export_cameras=False,export_lights=False,export_apply=True)
out=ROOT/'output/bnu_campus_web_white_v7.glb'
out.write_bytes(patch_meshes((ROOT/'output/bnu_campus_web_white_v6.glb').read_bytes(),out.read_bytes(),targets))
report={'model':'white_v7','target_id':267948584,'cause':'Vertex filtering created self-intersecting rear footprint; clipping requires edge intersections','crs':'EPSG:32650 local meters','boundary_y':-253,'rear_coords':coords,'height_unchanged':22,'protected_evaluated_meshes':len(before),'protected_meshes_equal':before==after,'original_model_sha256':hashlib.sha256((ROOT/'output/bnu_campus_web_white_v6.glb').read_bytes()).hexdigest(),'portico_boxes_preserved':12,'measured_geometry':False}
(ROOT/'output/main-repair-v7.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report))
