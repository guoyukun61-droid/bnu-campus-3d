"""Single-diagram interpretation. No claimed photogrammetry or measured heights.
Run Blender -b --python build_reference_v6.py. Original v5 assets stay unchanged.
"""
import json
import math
import sys
import hashlib
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import build_blender_scene as base

base.REANALYSIS = True
base.SUFFIX = '_v6'
base.TEXTURE_PATH = ROOT / 'assets/gf2_reanalysis_v5/truecolor_utm.png'
SOURCE = ROOT / 'assets/reference_campus_diagram_20260907.png'
DATA = ROOT / 'assets/campus_assets_v5.json'

# Explicit visual hypotheses, never based on OSM ID modulo or rooftop color.
# Source regions are [left, top, right, bottom] pixels in the 1680 x 1188 diagram.
GROUPS = [
    ('east_rows', [267944906,267944907,267944908,267944909,267944910,267944911,267944912,267944913,267944914,267944915,267944917,267944918,267944919,267946184,267946186], 'ref_row', 19.8, 6, [1210,562,1665,800], '东侧条形楼群：深色横窗带、红褐端墙；逐栋对应为位置推断'),
    ('small_roofs', [657006457,657006458,657006459,657006460,657006461,657006462,657006463,267948885], 'ref_villa', 7.2, 2, [1075,520,1250,637], '中北部低层组团：红色坡顶、浅色墙；分组对应待核对'),
    ('west_teaching', [172257581,172257585,361446563,499435186,499435187,499435188,540297386,540297387,540297388], 'ref_brick', None, None, [195,595,580,813], '操场西南侧低层楼群：红砖与浅色楼层线；对应及背立面为推断'),
    ('north_teaching', [172257582], 'ref_grid', 30.6, 9, [725,416,857,534], '操场北侧大体量深色格网立面；约九层表现，不是实测'),
    ('science', [172257586], 'ref_white', 30.6, 9, [844,618,956,723], '操场东侧 E 形楼：浅墙、较密竖窗及高低体量'),
    ('west_towers', [294110459,294110460,294110461,499433834], 'ref_tower', 66.0, 20, [420,252,885,616], '西侧塔楼：高层体量、红褐竖向肋、浅色窗带；高度和对应中低置信'),
    ('south_towers', [1087856281,1087856282], 'ref_blue', 57.6, 18, [363,782,513,916], '西南双塔：蓝灰竖向立面；图示塔楼位置与既有轮廓对应待核对'),
    ('library', [267944894], 'ref_white', 18.0, 5, [1100,755,1242,925], '主楼北侧图书馆组团：低裙房和较高浅色塔体，塔体尺寸为图示假设'),
    ('main', [267948584], 'ref_sand', 28.0, 6, [951,866,1145,1002], '主楼：大挑檐、内退入口和两侧支撑；后部形状沿用 OSM，门廊尺寸目估'),
    ('gym', [172257584], 'ref_grid', 16.0, 3, [550,691,695,785], '体育馆：大跨度浅色屋盖、深色竖向玻璃肋；非六层办公楼窗格'),
    ('jingshi', [182114919], 'ref_white', 12.0, 3, [1042,955,1156,1115], '京师大厦组团：低裙房与蓝白折面塔体；塔体范围和层高为示意假设'),
    ('east_teaching', [665146861,319522945], 'ref_blue', 23.8, 7, [1270,828,1464,982], '东南教学楼：蓝色竖窗及浅色边框，局部对应待核对'),
    ('traditional', [499433329], 'ref_white', 10.8, 3, [760,772,884,862], '京师学堂：低层浅墙、深色坡屋顶；背侧及屋顶结构简化'),
]

def srgb(v):
    v /= 255
    return v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4

def materials():
    mats = base.create_materials()
    colors = {'ref_row':(132,83,76),'ref_villa':(204,193,173),'ref_brick':(156,80,68),
              'ref_grid':(101,108,121),'ref_white':(207,209,202),'ref_tower':(148,90,92),
              'ref_blue':(142,161,176),'ref_sand':(198,183,131),'ref_roof':(171,164,151),
              'ref_dark_roof':(77,91,104),'ref_red_roof':(173,80,57),'ref_glass':(42,65,84),
              'ref_cyan':(52,143,177),'ref_trim':(218,214,198),'ref_dark':(47,48,51),
              'ref_track':(190,101,77),'ref_turf':(79,141,75),'ref_line':(235,231,210)}
    for name, c in colors.items():
        mats[name] = base.make_principled_material(name, tuple(srgb(i) for i in c)+(1,), .73)
        mats[name]['source'] = 'manual diagram palette; no facade photograph, unseen surfaces extrapolated'
    return mats

class Mesh:
    def __init__(self, name, mats):
        self.name, self.mats = name, list(mats.values())
        self.keys = list(mats)
        self.v, self.f, self.mi = [], [], []
    def box(self,x,y,z,w,d,h,mat):
        n = len(self.f)
        base.append_box(self.v,self.f,x,y,z,w,d,h)
        self.mi.extend([self.keys.index(mat)]*(len(self.f)-n))
    def face(self, coords, mat):
        n=len(self.v);self.v.extend(coords);self.f.append(tuple(range(n,n+len(coords))))
        self.mi.append(self.keys.index(mat))
    def finish(self, parent=None):
        me=bpy.data.meshes.new(self.name+'_Mesh');me.from_pydata(self.v,[],self.f)
        assert not me.validate(verbose=False), self.name
        me.update()
        obj=bpy.data.objects.new(self.name,me);bpy.context.collection.objects.link(obj)
        for m in self.mats: me.materials.append(m)
        for p,i in zip(me.polygons,self.mi):p.material_index=i
        obj['source']='single user diagram; parametric approximation, not measured'
        if parent:obj.parent=parent
        return obj

def clean(data):
    for b in data['buildings']+data['surfaces']:
        coords=[]
        for p in b['coords']:
            if not coords or math.dist(p,coords[-1])>.001:coords.append(p)
        if len(coords)>2 and math.dist(coords[0],coords[-1])<.001:coords.pop()
        if base.polygon_signed_area(coords)<0:coords.reverse()
        b['coords']=coords

def prep():
    data=json.loads(DATA.read_text(encoding='utf-8'));lookup={b['osm_id']:b for b in data['buildings']}
    for group,ids,style,height,floors,region,note in GROUPS:
        for id in ids:
            b=lookup[id]
            b['reference_observation']={'group':group,'style':style,'source_region_px':region,
                'note':note,'source':'reference_campus_diagram_20260907.png','confidence':'visual hypothesis; not field verified',
                'original_height':b['height'],'original_floors':b['floors'],
                'roof_material':'ref_red_roof' if style=='ref_villa' else 'ref_dark_roof' if style in ('ref_row','ref_grid') else 'ref_roof',
                'unseen_faces':'extrapolated from style; no observed texture',
                'temporal_status':'diagram date unknown; not forced to agree with GF2 2025-06-24'}
            if height is not None:b['height']=height;b['floors']=floors
    clean(data)
    data['reference_edition']={'version':'v6-diagram-study','source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'changed_buildings':sum('reference_observation'in b for b in data['buildings']),
        'method':'manual grouped visual interpretation + existing geospatial footprints; no inverse-camera solve',
        'limitations':['Single rendered diagram, not a photograph','No measured heights or accuracy percentage','Hidden faces extrapolated','OSM and diagram may differ in date and shape']}
    (ROOT/'assets/campus_assets_v6.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    return data

def facades(mesh,coords,z,h,floors,style):
    count=0
    for a,b in zip(coords,coords[1:]+coords[:1]):
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        if length<2:continue
        ux,uy=dx/length,dy/length;nx,ny=uy,-ux
        def face(s,t,lo,hi,mat,offset=.10):
            mesh.face([(a[0]+ux*s+nx*offset,a[1]+uy*s+ny*offset,lo),
                       (a[0]+ux*t+nx*offset,a[1]+uy*t+ny*offset,lo),
                       (a[0]+ux*t+nx*offset,a[1]+uy*t+ny*offset,hi),
                       (a[0]+ux*s+nx*offset,a[1]+uy*s+ny*offset,hi)],mat)
        fh=h/floors
        face(-.18,length+.18,z+h,z+h+.5,'ref_trim',.16)
        banded=style in ('ref_row','ref_blue','ref_tower','ref_grid')
        for fl in range(floors):
            lo=z+fl*fh
            if banded:
                face(.65,length-.65,lo+fh*.22,lo+fh*.83,'ref_cyan' if style=='ref_blue' else 'ref_glass')
                face(0,length,lo+fh*.89,lo+fh*.96,'ref_trim',.15)
                count+=1
            else:
                cols=max(1,int((length-1.4)/3.2));cell=(length-1.4)/cols
                for j in range(cols):
                    s=.7+j*cell+cell*.17;t=s+cell*.66
                    face(s-.08,t+.08,lo+fh*.25-.08,lo+fh*.79+.08,'ref_trim',.115)
                    face(s,t,lo+fh*.25,lo+fh*.79,'ref_glass',.14);count+=1
                if style=='ref_brick':face(0,length,lo+fh*.93,lo+fh*.99,'ref_trim',.16)
        if banded:
            spacing=2.8 if style in ('ref_blue','ref_grid') else 5.4
            for j in range(1,max(2,int(length/spacing))):
                s=j*length/max(2,int(length/spacing))
                face(s-.15,s+.15,z+.3,z+h,'ref_trim' if style in ('ref_blue','ref_grid') else style,.17)
    return count

def gable(mesh,coords,z,rise,mat):
    # A simple ridge over an axis-aligned bound; this is explicitly a roof hypothesis.
    xs=[p[0]for p in coords];ys=[p[1]for p in coords]
    x0,x1=min(xs)-.5,max(xs)+.5;y0,y1=min(ys)-.5,max(ys)+.5
    if x1-x0>=y1-y0:
        ym=(y0+y1)/2
        mesh.face([(x0,y0,z),(x1,y0,z),(x1,ym,z+rise),(x0,ym,z+rise)],mat)
        mesh.face([(x0,ym,z+rise),(x1,ym,z+rise),(x1,y1,z),(x0,y1,z)],mat)
        mesh.face([(x0,y1,z),(x0,y0,z),(x0,ym,z+rise)],mat)
        mesh.face([(x1,y0,z),(x1,y1,z),(x1,ym,z+rise)],mat)
    else:
        xm=(x0+x1)/2
        mesh.face([(x0,y0,z),(xm,y0,z+rise),(xm,y1,z+rise),(x0,y1,z)],mat)
        mesh.face([(xm,y0,z+rise),(x1,y0,z),(x1,y1,z),(xm,y1,z+rise)],mat)
        mesh.face([(x0,y0,z),(x1,y0,z),(xm,y0,z+rise)],mat)
        mesh.face([(x1,y1,z),(x0,y1,z),(xm,y1,z+rise)],mat)

def landmark(b,obj,mats,z):
    id=b['osm_id'];mesh=Mesh('Reference_Detail_'+str(id),mats);count=0
    if id==267948584:
        # Remove the full-height solid entrance block; replace it with an open portico.
        rear=[p for p in b['coords'] if p[1]>-253]
        new=base.polygon_mesh('Main_Rear_Temporary',rear,z,22,mats['ref_sand'],mats['ref_roof'])
        obj.data=new.data;bpy.data.objects.remove(new,do_unlink=True)
        mesh.box(210,-280,z+25,104,70,3.2,'ref_sand')
        mesh.box(210,-277,z+28.2,80,43,.7,'ref_roof')
        # Clearly visible deep shaded portal, flanked by substantial piers.
        for x in (170,250):mesh.box(x,-280,z,9,62,25,'ref_sand')
        for x in (182,239):mesh.box(x,-264,z,3.5,28,25,'ref_trim')
        mesh.box(210,-251,z,65,1,22,'ref_dark')
        for step in range(5):mesh.box(210,-316+step*1.1,z+step*.23,84,2.4,.23,'ref_trim')
        count+=facades(mesh,rear,z,22,6,'ref_sand')
    elif id==182114919:
        count+=facades(mesh,b['coords'],z,12,3,'ref_white')
        tower=[[299,-434],[328,-434],[340,-423],[340,-405],[331,-396],[301,-400]]
        new=base.polygon_mesh('Reference_Tower_Jingshi',tower,z+12,36,mats['ref_blue'],mats['ref_roof'])
        new.parent=obj;new['source']='diagram silhouette hypothesis; hidden faces extrapolated'
        count+=facades(mesh,tower,z+12,36,12,'ref_blue')
        mesh.box(316,-415,z+48,20,18,3,'ref_white')
        b['height']=51;b['floors']=15
    elif id==267944894:
        count+=facades(mesh,b['coords'],z,18,5,'ref_brick')
        tower=[[190,-160],[224,-158],[222,-128],[188,-130]]
        new=base.polygon_mesh('Reference_Tower_Library',tower,z+18,36,mats['ref_white'],mats['ref_roof']);new.parent=obj
        count+=facades(mesh,tower,z+18,36,11,'ref_blue')
        b['height']=54;b['floors']=16
    elif id==172257584:
        count+=facades(mesh,b['coords'],z,16,2,'ref_grid')
        mesh.box(-162,-279,z+16,104,76,1.8,'ref_trim')
        mesh.box(-162,-279,z+17.8,91,61,.5,'ref_roof')
        for x in range(-202,-111,6):mesh.box(x,-279,z+18.3,.25,61,.22,'ref_trim')
        b['height']=18.5
    else:
        ref=b['reference_observation'];style=ref['style']
        count+=facades(mesh,b['coords'],z,b['height'],b['floors'],style)
        if style=='ref_villa' or id==499433329:gable(mesh,b['coords'],z+b['height']+.15,2.1,'ref_red_roof'if style=='ref_villa'else'ref_dark_roof')
        if style=='ref_tower':
            cx,cy=base.polygon_centroid(b['coords']);mesh.box(cx,cy,z+b['height'],12,10,2.6,'ref_trim')
    mesh.finish(obj)
    obj['height_m']=b['height'];obj['floors_estimated']=b['floors']
    return count

def sports(data,mats):
    mesh=Mesh('Reference_Sports_Geometry',mats)
    def ring(cx,cy,z,r0,r1,half,mat):
        def capsule(r):
            return [(cx+r*math.cos(t),cy+(half if math.sin(t)>=0 else -half)+r*math.sin(t),z)for t in [i*2*math.pi/128 for i in range(128)]]
        a,c=capsule(r0),capsule(r1)
        for i in range(128):j=(i+1)%128;mesh.face([a[i],c[i],c[j],a[j]],mat)
    for cx,cy in [(-285,-83),(-171,-84)]:
        z=base.terrain_height(data,cx,cy)+.55
        ring(cx,cy,z,35,47,40,'ref_track')
        for r in (35,37,39,41,43,45,47):ring(cx,cy,z+.025,r,r+.17,40,'ref_line')
        # Footprint-scale schematic football markings, not a sports-facility survey.
        mesh.box(cx,cy,z,65,102,.08,'ref_turf')
        for x in (cx-31,cx+31):mesh.box(x,cy,z+.09,.16,98,.025,'ref_line')
        for y in (cy-49,cy,cy+49):mesh.box(cx,y,z+.09,62,.16,.025,'ref_line')
        ring(cx,cy,z+.13,8.8,9.0,0,'ref_line')
        for sy in (-1,1):
            yy=cy+sy*40
            for x in (cx-17,cx+17):mesh.box(x,yy,z+.09,.16,18,.025,'ref_line')
            mesh.box(cx,cy+sy*31,z+.09,34,.16,.025,'ref_line')
    mesh.finish()

def main():
    before=hashlib.sha256(DATA.read_bytes()).hexdigest()
    data=prep();base.reset_scene();base.UV_EXTENT=tuple(data['coordinate_system']['extent_m']);mats=materials()
    base.make_base(data,mats);base.make_terrain_mesh(data,mats['ground'])
    objects=base.build_buildings(data,mats);details=base.build_building_details(data,mats)
    panels=0
    for b in data['buildings']:
        if 'reference_observation'not in b:continue
        cx,cy=base.polygon_centroid(b['coords']);z=base.terrain_height(data,cx,cy)+.25
        panels+=landmark(b,bpy.data.objects['Building_'+str(b['osm_id'])],mats,z)
    base.build_roads(data,mats);base.build_surfaces(data,mats);base.build_trees(data,mats);sports(data,mats)
    base.setup_lighting()
    cam=base.add_camera('Reference_Hero_Camera',(1300,-1500,1250),(-15,-40,15),1480)
    bpy.context.scene.camera=cam;base.setup_scene()
    bpy.context.scene.render.resolution_x=1680;bpy.context.scene.render.resolution_y=1188
    bpy.context.scene.render.filepath=str(ROOT/'output/bnu_campus_reference_v6.png')
    for im in bpy.data.images:
        if im.source=='FILE'and im.has_data:im.pack()
    bpy.context.scene['reference_panels']=panels
    bpy.context.scene['reference_changed_buildings']=data['reference_edition']['changed_buildings']
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'output/bnu_campus_gf2_sentinel2_v6.blend'))
    bpy.ops.render.render(write_still=True)
    (ROOT/'assets/campus_assets_v6.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    # Structural validation is separate from real-world fidelity, which is unmeasured.
    assert len(objects)==231
    assert hashlib.sha256(DATA.read_bytes()).hexdigest()==before
    assert not bpy.data.objects['Rooftop_Equipment'].data.polygons
    assert bpy.data.objects['Reference_Detail_267948584']
    report={**data['reference_edition'],'geometry_checks_passed':True,'reference_facade_panels':panels,
            'untouched_v5_sha256':before,'source_objects':len(objects),'limitations':data['reference_edition']['limitations']}
    (ROOT/'output/reference_report_v6.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
