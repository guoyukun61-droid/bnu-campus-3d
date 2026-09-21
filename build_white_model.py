"""Create a texture-free clay edition without altering the reference source."""
import bpy
import json
import struct
from pathlib import Path

root=Path(__file__).resolve().parent
bpy.ops.wm.open_mainfile(filepath=str(root/'output/bnu_campus_gf2_sentinel2_v6.blend'))
def clay(name,value):
    mat=bpy.data.materials.new(name);mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value=(value,value,value,1)
    bsdf.inputs['Roughness'].default_value=.88
    bsdf.inputs['Metallic'].default_value=0
    mat.diffuse_color=(value,value,value,1)
    return mat
white=clay('White_Architectural_Clay',.72)
ground=clay('White_Ground_Clay',.43)
trees=clay('White_Tree_Clay',.58)
for obj in bpy.context.scene.objects:
    if obj.type not in {'MESH','CURVE'}:continue
    mat=ground if obj.name in {'GF2_Satellite_Terrain','Presentation_Base'} else trees if obj.name=='GF2_NDVI_Trees' else white
    obj.data.materials.clear();obj.data.materials.append(mat)
    if obj.type=='MESH':
        for face in obj.data.polygons:face.material_index=0
    obj['display_edition']='texture-free clay; v6 geometry, not surveyed'
for mat in list(bpy.data.materials):
    if mat.users==0:bpy.data.materials.remove(mat)
for im in list(bpy.data.images):
    if im.users==0:bpy.data.images.remove(im)
for obj in bpy.context.scene.objects:
    if obj.type=='LIGHT':obj.data.color=(1,1,1)
world=bpy.context.scene.world
world.node_tree.nodes.get('Background').inputs['Color'].default_value=(.65,.65,.65,1)
scene=bpy.context.scene
scene.render.filepath=str(root/'output/bnu_campus_white.png')
scene['edition']='white-clay-v1-20260918'
bpy.ops.wm.save_as_mainfile(filepath=str(root/'output/bnu_campus_white.blend'))
bpy.ops.render.render(write_still=True)
path=root/'output/bnu_campus_web_white.glb'
bpy.ops.export_scene.gltf(filepath=str(path),export_format='GLB',export_cameras=False,export_lights=False,export_apply=True)
raw=path.read_bytes();size,kind=struct.unpack_from('<II',raw,12)
doc=json.loads(raw[20:20+size]);assert not doc.get('images')and not doc.get('textures')
assert all(not any(n.type=='TEX_IMAGE'for n in m.node_tree.nodes)for m in bpy.data.materials if m.use_nodes)
metadata={'version':'20260918-white-clay','geometry_source':'v6 diagram hypotheses, not measured',
          'polygons':sum(len(o.data.polygons)for o in scene.objects if o.type=='MESH'),
          'windows':len(bpy.data.objects['Facade_Window_Panels'].data.polygons)+scene['reference_panels'],
          'trees':bpy.data.objects['GF2_NDVI_Trees']['tree_count'],
          'glb_bytes':len(raw),'embedded_images':len(doc.get('images',[])),
          'material_count':len(doc['materials']),'validation_passed':True}
(root/'output/scene_manifest_white.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
print(json.dumps(metadata))
