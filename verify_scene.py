"""Run with Blender -b output/bnu_campus_gf2_sentinel2.blend --python verify_scene.py."""
import json
import math
import struct
from pathlib import Path

import bpy

root = Path(__file__).resolve().parent
v5 = Path(bpy.data.filepath).stem.endswith('_v5')
suffix = '_v5' if v5 else ''
assets = json.loads((root / f'assets/campus_assets{suffix}.json').read_text(encoding='utf-8'))
by_id = {str(b['osm_id']): b for b in assets['buildings']}
x0, y0, x1, y1 = assets['coordinate_system']['extent_m']
buildings = [o for o in bpy.data.objects if o.type == 'MESH' and o.name.startswith('Building_')]
assert len(buildings) == len(assets['buildings']) == 231
max_uv_error = 0.0
for obj in buildings:
    mesh = obj.data
    assert mesh.polygons[1].normal.z > .99, obj.name + ': roof facing down'
    roof = mesh.uv_layers['Roof_Geo_UV']
    wall = mesh.uv_layers['Facade_UV']
    observation = by_id[obj.name.replace('Building_', '')].get('gf2_observation', {})
    offset = observation.get('roof_sampling_offset') or {}
    dx, dy = offset.get('dx_m',0), offset.get('dy_m',0)
    for face in mesh.polygons:
        for loop in face.loop_indices:
            co = mesh.vertices[mesh.loops[loop].vertex_index].co
            uv = roof.data[loop].uv
            max_uv_error = max(max_uv_error, abs(uv.x - (co.x+dx-x0)/(x1-x0)), abs(uv.y-(co.y+dy-y0)/(y1-y0)))
            assert all(math.isfinite(v) for v in wall.data[loop].uv)
    for face in mesh.polygons[2:]:
        uvs = [wall.data[i].uv for i in face.loop_indices]
        width = max(v.x for v in uvs) - min(v.x for v in uvs)
        height = max(v.y for v in uvs) - min(v.y for v in uvs)
        assert width > 0 and height > 0, obj.name + ': collapsed facade UV'
assert max_uv_error < 1e-6
for name in ['Facade_Window_Panels', 'Facade_Window_Frames', 'Roof_Parapets']:
    mesh = bpy.data.objects[name].data
    duplicate_keys = set()
    for face in mesh.polygons:
        key = tuple(sorted(tuple(round(v, 5) for v in mesh.vertices[i].co) for i in face.vertices))
        assert key not in duplicate_keys, name + ': duplicate coplanar face'
        duplicate_keys.add(key)
        assert face.area > 1e-6, name + ': zero area'
    copy = mesh.copy()
    assert not copy.validate(), name + ': invalid mesh'
    bpy.data.meshes.remove(copy)

raw = (root / f'output/bnu_campus_web{suffix}.glb').read_bytes()
magic, version, length = struct.unpack_from('<III', raw)
assert magic == 0x46546C67 and version == 2 and length == len(raw)
json_length = struct.unpack_from('<I', raw, 12)[0]
gltf = json.loads(raw[20:20+json_length])
walls = [m for m in gltf['materials'] if m['name'].startswith('Campus') or m['name']=='Facade_Unobserved_Neutral']
assert len(walls) == (1 if v5 else 4)
for mat in walls:
    pbr = mat['pbrMetallicRoughness']
    assert pbr['baseColorTexture']['texCoord'] == 1
    assert all(abs(a-b) < 1e-6 for a,b in zip(pbr['baseColorFactor'], bpy.data.materials[mat['name']].diffuse_color))
image_names = [i['name'] for i in gltf['images']]
assert ('image2_brick_surface_v4' in image_names) == (not v5)
assert 'image2_stone_surface_v4' in image_names
assert all('facade_' not in name for name in image_names)
if v5:
    assert 'truecolor_utm' in image_names
    original = json.loads((root/'assets/campus_assets.json').read_text(encoding='utf-8'))
    assert [b['coords'] for b in original['buildings']] == [b['coords'] for b in assets['buildings']]
    assert sum(bool(b['gf2_observation']['roof_sampling_offset']) for b in assets['buildings']) == 25
    assert not bpy.data.objects['Rooftop_Equipment'].data.polygons
triangles = sum(gltf['accessors'][p['indices']]['count']//3 for m in gltf['meshes'] for p in m['primitives'])
report = dict(passed=True, version='v5' if v5 else 'v4', buildings=len(buildings), max_roof_uv_error=max_uv_error,
              windows=len(bpy.data.objects['Facade_Window_Panels'].data.polygons),
              frame_faces=len(bpy.data.objects['Facade_Window_Frames'].data.polygons),
              embedded_images=image_names, glb_bytes=len(raw), glb_triangles=triangles,
              checks=['upward roofs', 'geographic UV accuracy', 'noncollapsed wall UVs',
                      'no duplicate detail faces', 'valid detail meshes', 'GLB tint parity', 'new embedded textures'])
(root / f'output/validation_20260905{suffix}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
