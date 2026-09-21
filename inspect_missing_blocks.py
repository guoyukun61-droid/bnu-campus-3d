import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
ROOT=Path(__file__).resolve().parent
d=json.loads((ROOT/'assets/campus_assets_white_v3.json').read_text(encoding='utf-8'))
img=mpimg.imread(ROOT/'assets/gf2_reanalysis_v5/truecolor_utm.png')
x0,y0,x1,y1=d['coordinate_system']['extent_m']
fig,axs=plt.subplots(1,2,figsize=(14,8))
for ax,limits,title in zip(axs,[(-420,-300,-420,-310),(235,385,-180,-40)],['Lanhui / GF2 + existing outlines','International dorms / GF2 + existing outlines']):
    ax.imshow(img,extent=(x0,x1,y0,y1),origin='upper');ax.set_xlim(limits[:2]);ax.set_ylim(limits[2:]);ax.set_title(title)
    for b in d['buildings']:
        xs,ys=zip(*b['coords']);cx=sum(xs)/len(xs);cy=sum(ys)/len(ys)
        if limits[0]-30<cx<limits[1]+30 and limits[2]-30<cy<limits[3]+30:
            ax.plot([*xs,xs[0]],[*ys,ys[0]],color='yellow',lw=1);ax.text(cx,cy,str(b['osm_id']),color='yellow',fontsize=6)
    ax.grid(alpha=.4);ax.set_xlabel('local east / m');ax.set_ylabel('local north / m')
fig.tight_layout();fig.savefig(ROOT/'output/missing_blocks_gf2.png',dpi=150)
