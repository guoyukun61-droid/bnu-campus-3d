"""Source-aware campus corrections. User observations are not surveyed heights."""
import bpy, json, sys, math, hashlib, struct
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import build_blender_scene as base
from build_reference_v6 import Mesh, facades, sports
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'output/bnu_campus_white_v2.blend'))
data=json.loads((ROOT/'assets/campus_assets_white_v2.json').read_text(encoding='utf-8'))
white=bpy.data.materials['White_Architectural_Clay']
def mat(name,color):
    m=base.make_principled_material(name,(*color,1),.94);return m
road=mat('V3_Road_Graphite',(.16,.18,.19));track=mat('V3_Track_Rubber',(.37,.12,.09))
turf=mat('V3_Sports_Turf',(.08,.23,.15));court=mat('V3_Court_Surface',(.07,.22,.24))
line=mat('V3_Sports_White_Line',(.85,.85,.8))
def digest(o):return hashlib.sha256(repr(([tuple(v.co) for v in o.data.vertices],[tuple(p.vertices) for p in o.data.polygons])).encode()).hexdigest()
before={o.name:digest(o) for o in bpy.context.scene.objects if o.type=='MESH'}
allowed=set();changes=[]
for id in [540297386,540297387,540297388,1381082299]:
    b=next(b for b in data['buildings'] if b['osm_id']==id);obj=bpy.data.objects['Building_'+str(id)]
    z=min(v.co.z for v in obj.data.vertices);old=b['height'];kiosk=id==1381082299
    h,floors=(3.8,1) if kiosk else (41.4,12)
    note='一层依据用户现场反馈及 OSM bungalow；3.8 m 为表现层高估计。' if kiosk else '高层依据用户现场反馈；暂按邻近学4楼 OSM 12层作同组占位，41.4 m 未实测，逐栋层数待核。'
    for child in list(obj.children):allowed.add(child.name);bpy.data.objects.remove(child,do_unlink=True)
    if kiosk:
        # Legacy detail meshes batch many buildings: adjust only kiosk-local vertices.
        xs=[p[0] for p in b['coords']];ys=[p[1] for p in b['coords']]
        for other in bpy.context.scene.objects:
            if other.type!='MESH' or other.name not in {'Facade_Window_Panels','Facade_Frames','Roof_Parapets','Rooftop_Equipment','Facade_Bands'}:continue
            for v in other.data.vertices:
                if min(xs)-1<v.co.x<max(xs)+1 and min(ys)-1<v.co.y<max(ys)+1 and z-.1<=v.co.z<=z+old+3:
                    allowed.add(other.name);v.co.z=z+(v.co.z-z)*h/old
    new=base.polygon_mesh('NewVolume',b['coords'],z,h,white,white,bevel=0)
    obj.data=new.data;bpy.data.objects.remove(new,do_unlink=True);allowed.add(obj.name)
    for modifier in list(obj.modifiers):obj.modifiers.remove(modifier)
    if not kiosk:
        detail=Mesh('Reference_Detail_'+str(id),{k:white for k in ['ref_trim','ref_glass','ref_white']})
        facades(detail,b['coords'],z,h,floors,'ref_white');detail.finish(obj)
    b.update(height=h,floors=floors,correction_note=note)
    if b.get('reference_observation'):b['reference_observation']['note']=note
    obj['height_m']=h;obj['floors_estimated']=floors;obj['correction_note']=note
    changes.append({'osm_id':id,'name':b['name'],'old_height':old,'height':h,'note':note})
# Retain the already documented 12-storey Xue4 and all main/teaching geometry.
for b in data['buildings']:
    if b['osm_id']==540297385:b['correction_note']='保留原 OSM building:levels=12；41.4 m 为按层数换算，不是实测。'
old_sports=bpy.data.objects.get('Reference_Sports_Geometry')
allowed.add(old_sports.name);bpy.data.objects.remove(old_sports,do_unlink=True)
sports(data,{'ref_track':track,'ref_turf':turf,'ref_line':line})
# Fix capsule winding from legacy helper, whose top-facing rings were reversed.
obj=bpy.data.objects['Reference_Sports_Geometry']
for p in obj.data.polygons:
    if p.normal.z<-.5:p.flip()
obj.data.update()
for id in [179354665,179354666]:
    o=bpy.data.objects['Surface_Corrected_'+str(id)];o.data.materials.clear();o.data.materials.append(court)
    for p in o.data.polygons:p.material_index=0
    o=bpy.data.objects['Surface_Court_Lines_'+str(id)];o.data.materials.clear();o.data.materials.append(line)
    for p in o.data.polygons:p.material_index=0
    s=next(s for s in data['surfaces'] if s['osm_id']==id)
    s['sport_status']='旧 OSM 标注西侧 tennis、东侧 basketball；用户称南侧篮球场，西侧现用途待核，暂不覆盖历史分类。'
# Existing builder omitted vehicular campus roads in white mode; render existing lines.
roads=Mesh('Path_V3_Road_Network',{'road':road})
road_count=0
for r in data['roads']:
    if r['kind'] not in {'service','residential','tertiary','secondary','primary','trunk','unclassified','living_street'}:continue
    width=r['width'];width=max(12,width) if r['kind']=='trunk' else width
    for a,b in zip(r['coords'],r['coords'][1:]):
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        if length<.1:continue
        # Liang-Barsky clip to model bounds without moving valid road centerlines.
        lo,hi=0.,1.
        for p,q in [(-dx,a[0]+452),(dx,452-a[0]),(-dy,a[1]+601),(dy,601-a[1])]:
            if p==0:
                if q<0:hi=-1;break
            elif p<0:lo=max(lo,q/p)
            else:hi=min(hi,q/p)
        if lo>=hi:continue
        xa,ya=a[0]+lo*dx,a[1]+lo*dy;xb,yb=a[0]+hi*dx,a[1]+hi*dy
        nx,ny=-dy/length*width/2,dx/length*width/2
        pts=[(xa-nx,ya-ny),(xb-nx,yb-ny),(xb+nx,yb+ny),(xa+nx,ya+ny)]
        roads.face([(x,y,base.terrain_height(data,x,y)+.32) for x,y in pts],'road');road_count+=1
roads.finish()
after={o.name:digest(o) for o in bpy.context.scene.objects if o.type=='MESH'}
assert all(after.get(n)==h for n,h in before.items() if n not in allowed)
assert after['Building_267948584']==before['Building_267948584']
scene=bpy.context.scene;scene['edition']='white-v3-user-grounded-20260920'
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'output/bnu_campus_white_v3.blend'))
path=ROOT/'output/bnu_campus_web_white_v3.glb'
bpy.ops.export_scene.gltf(filepath=str(path),export_format='GLB',export_cameras=False,export_lights=False,export_apply=True)
report={'version':'white-v3','changes':changes,'road_segments':road_count,'protected_geometry_check':True,'baidu_3d_verified':False,'sports_materials':'schematic rubber/turf paint; not photo textures','polygons':sum(len(o.data.polygons) for o in scene.objects if o.type=='MESH'),'trees':900,'windows':None,'limitations':['User-confirmed high-rise classification; Xue1-3 exact floor counts unknown','2011 imagery is historical, not present-day business evidence','Road topology/accessibility not routing-validated']}
(ROOT/'assets/campus_assets_white_v3.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
(ROOT/'output/scene_manifest_white_v3.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
