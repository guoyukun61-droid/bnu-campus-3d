"""Check implementation consistency only; cannot certify single-image fidelity."""
import hashlib
import json
import math
import struct
from pathlib import Path
import bpy

root=Path(__file__).resolve().parent
old=json.loads((root/'assets/campus_assets_v5.json').read_text(encoding='utf-8'))
new=json.loads((root/'assets/campus_assets_v6.json').read_text(encoding='utf-8'))
old_by_id={b['osm_id']:b for b in old['buildings']}
changed=[b for b in new['buildings']if'reference_observation'in b]
assert len(new['buildings'])==231 and len(changed)==47
for b in new['buildings']:
    assert set(map(tuple,b['coords']))==set(map(tuple,old_by_id[b['osm_id']]['coords']))
    if 'reference_observation' not in b:
        assert b['height']==old_by_id[b['osm_id']]['height']
    obj=bpy.data.objects.get('Building_'+str(b['osm_id']))
    assert obj is not None
    if 'reference_observation'in b:
        assert 'reference_observation'in obj
        assert abs(obj['height_m']-b['height'])<.01
        assert bpy.data.objects.get('Reference_Detail_'+str(b['osm_id']))
mesh_count=0
for obj in bpy.context.scene.objects:
    if obj.type!='MESH':continue
    mesh_count+=1
    assert all(math.isfinite(c)for v in obj.data.vertices for c in v.co),obj.name
    if obj.name.startswith('Reference_'):
        assert all(p.area>1e-7 for p in obj.data.polygons),obj.name
    assert not obj.data.validate(verbose=False),obj.name
assert len(bpy.data.objects['Rooftop_Equipment'].data.polygons)==0
raw=(root/'output/bnu_campus_web_v6.glb').read_bytes()
magic,version,total=struct.unpack_from('<III',raw)
assert magic==0x46546c67 and version==2 and total==len(raw)
length,kind=struct.unpack_from('<II',raw,12)
assert kind==0x4e4f534a
glb=json.loads(raw[20:20+length])
names={n.get('name')for n in glb['nodes']}
assert 'Reference_Tower_Jingshi'in names and'Reference_Tower_Library'in names
assert all('Reference_Detail_'+str(b['osm_id'])in names for b in changed)
assert new['reference_edition']['source_sha256']==hashlib.sha256((root/'assets/reference_campus_diagram_20260907.png').read_bytes()).hexdigest()
triangles=sum(glb['accessors'][p['indices']]['count']//3 for m in glb['meshes']for p in m['primitives'])
report={'passed':True,'scope':'implementation consistency only; no empirical fidelity score',
        'changed_buildings':47,'unchanged_buildings':184,'building_records':231,
        'mesh_objects':mesh_count,'glb_bytes':len(raw),'glb_triangles':triangles,
        'checks':['all footprint coordinate sets retained','unchanged building heights retained',
                  'variant height metadata matches scene','source image hash matches',
                  'finite mesh vertices','valid meshes','positive reference face areas',
                  'GLB header, length and landmark nodes','no random rooftop equipment']}
(root/'output/validation_reference_v6.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
