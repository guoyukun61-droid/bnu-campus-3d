"""Local GIS diagnostic: existing footprints over georeferenced GF2 display."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from shapely.geometry import Polygon
ROOT=Path(__file__).resolve().parent
data=json.loads((ROOT/'assets/campus_assets_white_v5.json').read_text(encoding='utf8'))
report=json.loads((ROOT/'assets/gf2_reanalysis_v5/report.json').read_text(encoding='utf8'))
x0,y0,x1,y1=report['local_extent_m']
plt.rcParams['font.sans-serif']=['Microsoft YaHei']
fig,ax=plt.subplots(figsize=(12,12),dpi=140)
ax.imshow(plt.imread(ROOT/'assets/gf2_reanalysis_v5/truecolor_utm.png'),extent=[x0,x1,y0,y1])
for b in data['buildings']:
    p=Polygon(b['coords']);c=p.centroid
    if -415<c.x<-200 and -460<c.y<-320:
        for part in b.get('parts',[b]):
            ring=part['coords']+[part['coords'][0]]
            ax.plot(*zip(*ring),color='#00ffff',lw=1)
        ax.text(c.x,c.y,str(b['osm_id'])+'\n'+b['name']+'\n'+str(b['floors'])+'F',ha='center',fontsize=8,color='yellow')
ax.set(xlim=(-420,-200),ylim=(-465,-315),xlabel='local X / m',ylabel='local Y / m',title='GF2 2025-06-24 + white_v5 footprints (not surveyed)')
ax.grid(alpha=.3)
fig.tight_layout();fig.savefig(ROOT/'output/snack_footprint_audit_20260924.png')
