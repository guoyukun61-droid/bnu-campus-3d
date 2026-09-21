"""Bounded correction using existing OSM and GF2 interpretation; no surveyed heights."""
import bpy, json, sys, math, hashlib, struct
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import build_blender_scene as base
from build_reference_v6 import Mesh, facades
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'output/bnu_campus_white.blend'))
data=json.loads((ROOT/'assets/campus_assets_v6.json').read_text(encoding='utf-8'))
old=json.loads((ROOT/'assets/campus_assets_v5.json').read_text(encoding='utf-8'))
lookup={b['osm_id']:b for b in data['buildings']}
previous={b['osm_id']:b for b in old['buildings']}
white=bpy.data.materials['White_Architectural_Clay']
ground=bpy.data.materials['White_Ground_Clay']
mats={k:white for k in ['ref_trim','ref_glass','ref_white','ref_roof']}
def digest(o):
    return hashlib.sha256(repr(([tuple(v.co) for v in o.data.vertices],[tuple(p.vertices) for p in o.data.polygons],list(o.matrix_world))).encode()).hexdigest()
before={o.name:digest(o) for o in bpy.context.scene.objects if o.type=='MESH'}
changed=set()
def replace(id,height,floors,note):
    b=lookup[id]; obj=bpy.data.objects['Building_'+str(id)]
    z=min(v.co.z for v in obj.data.vertices)
    for child in list(obj.children):
        changed.add(child.name);bpy.data.objects.remove(child,do_unlink=True)
    changed.add(obj.name)
    new=base.polygon_mesh('Replacement',b['coords'],z,height,white,white,bevel=0)
    obj.data=new.data;bpy.data.objects.remove(new,do_unlink=True)
    for mod in list(obj.modifiers):obj.modifiers.remove(mod)
    b['height']=height;b['floors']=floors;b['correction_note']=note
    obj['height_m']=height;obj['floors_estimated']=floors;obj['correction_note']=note
    return b,obj,z
for id in [1087856281,1087856282]:
    prior=previous[id]
    b,obj,z=replace(id,prior['height'],prior['floors'],'撤销图示双塔错配；恢复 v5 规则占位高度 13 m，不是实测楼高，待楼层资料校核。')
    mesh=Mesh('Reference_Detail_'+str(id),mats)
    facades(mesh,b['coords'],z,b['height'],b['floors'],'ref_white');mesh.finish(obj)
    b['reference_observation']['note']=b['correction_note']
b,obj,z=replace(172257584,9,2,'沿用 OSM 外轮廓，区分主馆与低附馆；屋顶分区参考 GF2，18 m / 9 m 为待核实表现高度，非测量。')
# A lower stepped footprint remains below a raised western hall; no invented courtyard.
hall=[[-207.38,-250.37],[-207.71,-315.28],[-140.72,-315.62],[-140.39,-252.74],[-148.03,-252.71],[-147.97,-241.54],[-158.21,-241.49],[-158.18,-235.95],[-191.2,-235.77],[-191.24,-241.72],[-201.63,-241.67],[-201.68,-250.4]]
high=base.polygon_mesh('Reference_Tower_GymHall',hall,z+9,9,white,white,bevel=0);high.parent=obj
mesh=Mesh('Reference_Detail_172257584',mats)
# Restrained roof panel and real depth from ribs, not a giant rectangle across the annex.
mesh.box(-173,-278,z+18.03,28,22,.18,'ref_roof')
for x in range(-202,-144,7):mesh.box(x,-284,z+18,.22,57,.25,'ref_trim')
for y in range(-310,-270,7):mesh.box(-106.9,y,z,.4,.55,9,'ref_trim')
mesh.finish(obj)
b['height']=18;b['floors']=2;obj['height_m']=18
b['reference_observation']['note']=b['correction_note']

# Existing OSM explicitly distinguishes western tennis and eastern basketball.
court_counts={179354665:4,179354666:6}
report_courts=[]
for id,count in court_counts.items():
    surface=next(s for s in data['surfaces'] if s['osm_id']==id)
    coords=surface['coords']; x0=min(p[0] for p in coords);x1=max(p[0] for p in coords)
    y0=min(p[1] for p in coords);y1=max(p[1] for p in coords)
    zz=max(base.terrain_height(data,*p) for p in coords)+.42
    slab=base.polygon_mesh('Surface_Corrected_'+str(id),coords,zz,.10,ground,ground,bevel=0)
    mesh=Mesh('Surface_Court_Lines_'+str(id),{'line':white})
    def line(xa,ya,xb,yb):
        dx,dy=xb-xa,yb-ya;l=math.hypot(dx,dy);nx,ny=-dy/l*.065,dx/l*.065
        mesh.face([(xa-nx,ya-ny,zz+.16),(xb-nx,yb-ny,zz+.16),(xb+nx,yb+ny,zz+.16),(xa+nx,ya+ny,zz+.16)],'line')
    def rectangle(cx,cy,w,h):
        for a,c in [((-w/2,-h/2),(w/2,-h/2)),((w/2,-h/2),(w/2,h/2)),((w/2,h/2),(-w/2,h/2)),((-w/2,h/2),(-w/2,-h/2))]:line(cx+a[0],cy+a[1],cx+c[0],cy+c[1])
    for n in range(count):
        cx=x0+(n+.5)*(x1-x0)/count;cy=(y0+y1)/2
        basketball=id==179354666;w,h=(15,28) if basketball else (10.97,23.77)
        rectangle(cx,cy,w,h);line(cx-w/2,cy,cx+w/2,cy)
        if basketball:
            for i in range(48):
                a=i*math.tau/48;c=(i+1)*math.tau/48
                line(cx+1.8*math.cos(a),cy+1.8*math.sin(a),cx+1.8*math.cos(c),cy+1.8*math.sin(c))
            for sign in [-1,1]:
                rectangle(cx,cy+sign*(14-2.9),4.9,5.8)
                mesh.box(cx,cy+sign*14.7,zz+.1,.15,.15,3.1,'line')
                mesh.box(cx,cy+sign*13.8,zz+2.9,1.8,.12,1.05,'line')
        else:
            rectangle(cx,cy,8.23,23.77);rectangle(cx,cy,8.23,12.8)
            line(cx,cy-6.4,cx,cy+6.4)
            for xx in [cx-6,cx+6]:mesh.box(xx,cy,zz+.1,.1,.1,1.05,'line')
            mesh.box(cx,cy,zz+.98,12,.06,.06,'line')
    mesh.finish()
    report_courts.append({'osm_id':id,'sport':'basketball' if id==179354666 else 'tennis','schematic_courts':count,'boundary_source':'existing OSM','count_source':'GF2 visual interpretation; approximate; not surveyed'})
    surface['correction_note']=report_courts[-1]
after={o.name:digest(o) for o in bpy.context.scene.objects if o.type=='MESH'}
unchanged=[name for name in before if name not in changed]
assert all(after.get(name)==before[name] for name in unchanged)
assert len([o for o in bpy.context.scene.objects if o.name.startswith('Building_')])==231
for o in bpy.context.scene.objects:
    if o.type=='MESH':assert all(math.isfinite(c) for v in o.data.vertices for c in v.co)
scene=bpy.context.scene;scene['edition']='white-v2-local-correction-20260920'
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'output/bnu_campus_white_v2.blend'))
path=ROOT/'output/bnu_campus_web_white_v2.glb'
bpy.ops.export_scene.gltf(filepath=str(path),export_format='GLB',export_cameras=False,export_lights=False,export_apply=True)
raw=path.read_bytes();size=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+size]);assert not doc.get('images')
report={'version':'20260920-white-v2','changed_buildings':[1087856281,1087856282,172257584],'unchanged_meshes':len(unchanged),'unaffected_geometry_hash_check':True,'courts':report_courts,'height_caveat':'2 mismatched towers reverted to unverified v5 defaults; gym heights estimated; other western towers unchanged pending evidence','glb_bytes':len(raw),'embedded_images':0,'validation_passed':True,'polygons':sum(len(o.data.polygons) for o in scene.objects if o.type=='MESH'),'trees':900,'windows':scene.get('reference_panels',0)}
(ROOT/'output/scene_manifest_white_v2.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
(ROOT/'assets/campus_assets_white_v2.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
