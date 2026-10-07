"""Read-only Blender inspection; stdout is geometry diagnostics, never business data."""
import bpy, json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'output/bnu_campus_white_v6.blend'))
for name in ('Building_267948584','Reference_Detail_267948584'):
    o=bpy.data.objects[name]
    print(name, 'modifiers', [(m.name,m.type) for m in o.modifiers])
    print('vertices',len(o.data.vertices),'polygons',len(o.data.polygons))
    if name.startswith('Building'):
        print('VERTICES',json.dumps([list(v.co) for v in o.data.vertices]))
        print('FACES',json.dumps([list(p.vertices) for p in o.data.polygons]))
    print('bounds',json.dumps([list(v) for v in o.bound_box]))
