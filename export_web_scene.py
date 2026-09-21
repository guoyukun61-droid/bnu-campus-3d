from pathlib import Path
import json
import struct

import bpy


project_dir = Path(__file__).resolve().parent
v5 = Path(bpy.data.filepath).stem.endswith('_v5')
v6 = Path(bpy.data.filepath).stem.endswith('_v6')
suffix = '_v6' if v6 else '_v5' if v5 else ''
output_path = project_dir / "output" / f"bnu_campus_web{suffix}.glb"

bpy.ops.export_scene.gltf(
    filepath=str(output_path),
    export_format="GLB",
    use_selection=False,
    export_cameras=False,
    export_lights=False,
    export_apply=True,
    export_attributes=True,
)

# glTF does not preserve the arbitrary Multiply shader used for wall tint.
# Store the same linear RGBA multiplier explicitly in its standard PBR field.
raw = output_path.read_bytes()
json_length, chunk_type = struct.unpack_from('<II', raw, 12)
assert chunk_type == 0x4E4F534A
gltf = json.loads(raw[20:20 + json_length])
for material in gltf.get('materials', []):
    source = bpy.data.materials.get(material.get('name', ''))
    if source and (source.name.startswith('Campus') or source.name == 'Facade_Unobserved_Neutral'):
        material['pbrMetallicRoughness']['baseColorFactor'] = list(source.diffuse_color)
payload = json.dumps(gltf, separators=(',', ':')).encode('utf-8')
payload += b' ' * ((-len(payload)) % 4)
tail = raw[20 + json_length:]
output_path.write_bytes(struct.pack('<III', 0x46546C67, 2, 20 + len(payload) + len(tail))
                        + struct.pack('<II', len(payload), chunk_type) + payload + tail)

mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
polygon_count = sum(len(obj.data.polygons) for obj in mesh_objects)
metadata = {"version": "20260905-v5" if v5 else "20260905-v4", "mesh_objects": len(mesh_objects), "polygons": polygon_count,
            "windows": len(bpy.data.objects['Facade_Window_Panels'].data.polygons),
            "trees": bpy.data.objects['GF2_NDVI_Trees']['tree_count'],
            "texture_source": "UTM-reprojected GF2 and 25 candidate roof UV alignments; facades unobserved" if v5 else "Image2 window-free brick and stone surfaces; observed GF2 roofs"}
if v6:
    metadata.update(version='20260907-v6-reference-study', texture_source='Manual single-diagram interpretation, not measured reconstruction',
                    reference_buildings=bpy.context.scene['reference_changed_buildings'],
                    reference_panels=bpy.context.scene['reference_panels'])
    metadata['windows'] += bpy.context.scene['reference_panels']
(project_dir / 'output' / f'scene_manifest{suffix}.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
print({"output": str(output_path), "mesh_objects": len(mesh_objects), "polygons": polygon_count})
