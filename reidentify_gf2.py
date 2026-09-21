"""Re-read original GF2 bands; never synthesize satellite evidence.

Outputs are versioned analytical rasters, per-OSM-footprint observations and
source-preserving display products. Threshold labels are not trained land-cover truth.
"""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import json
import math

import cv2
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import reproject, Resampling, transform_bounds
from rasterio.windows import from_bounds as window_from_bounds
from rasterio.features import rasterize
from pyproj import Transformer
from shapely.geometry import Polygon, mapping
from scipy.ndimage import maximum_filter, gaussian_filter, distance_transform_edt

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'assets/gf2_reanalysis_v5'
OUT.mkdir(parents=True, exist_ok=True)
DATA = json.loads((ROOT/'assets/campus_assets.json').read_text(encoding='utf-8'))
SOURCE = Path(DATA['gf2']['source'])
CS = DATA['coordinate_system']
X0,Y0 = CS['origin_utm']
EXTENT = CS['extent_m']
WEST,SOUTH,EAST,NORTH = [v+o for v,o in zip(EXTENT,[X0,Y0,X0,Y0])]
W,H = math.ceil((EAST-WEST)/.8), math.ceil((NORTH-SOUTH)/.8)
AFFINE = from_bounds(WEST,SOUTH,EAST,NORTH,W,H)
LOCAL = from_bounds(*EXTENT,W,H)


def save_json(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def save_raster(name, array, dtype=None):
    if array.ndim == 2:
        array = array[None]
    array = array.astype(dtype or array.dtype)
    with rasterio.open(OUT/name,'w',driver='GTiff',height=H,width=W,count=len(array),
                       dtype=array.dtype,crs='EPSG:32650',transform=AFFINE,
                       compress='deflate',tiled=True) as dst:
        dst.write(array)


def save_png(name, rgb):
    with rasterio.open(OUT/name,'w',driver='PNG',height=rgb.shape[0],width=rgb.shape[1],
                       count=3,dtype='uint8') as dst:
        dst.write(np.moveaxis(rgb.astype('uint8'),-1,0))


def source_inventory():
    inventory=[]
    for file in sorted(SOURCE.parent.glob('*.tif')):
        with rasterio.open(file) as src:
            sb = transform_bounds('EPSG:32650',src.crs,WEST,SOUTH,EAST,NORTH)
            intersects = sb[0]<src.bounds.right and sb[2]>src.bounds.left and sb[1]<src.bounds.top and sb[3]>src.bounds.bottom
            coverage=0.0
            if intersects:
                win=window_from_bounds(*sb,transform=src.transform).round_offsets().round_lengths()
                sample=src.read(1,window=win,out_shape=(100,100),boundless=True,fill_value=0)
                coverage=float((sample>0).mean())
            inventory.append(dict(file=file.name,crs=str(src.crs),bounds=list(src.bounds),
                         shape=[src.count,src.height,src.width],resolution=list(src.res),
                         bands=list(src.descriptions),timestamp=src.tags().get('TIFFTAG_DATETIME'),
                         campus_valid_fraction_sampled=coverage,selected=file==SOURCE))
    return inventory


def reread():
    dst=np.zeros((4,H,W),dtype=np.float32)
    with rasterio.open(SOURCE) as src:
        assert src.count==4 and 'Blue' in src.descriptions[0] and 'NIR' in src.descriptions[3]
        sb=transform_bounds('EPSG:32650',src.crs,WEST-5,SOUTH-5,EAST+5,NORTH+5)
        win=window_from_bounds(*sb,transform=src.transform).round_offsets().round_lengths()
        crop=src.read(window=win,boundless=True,fill_value=0)
        for b in range(4):
            reproject(crop[b],dst[b],src_transform=src.window_transform(win),src_crs=src.crs,
                      dst_transform=AFFINE,dst_crs='EPSG:32650',src_nodata=0,dst_nodata=0,
                      resampling=Resampling.bilinear,num_threads=2)
    return dst


def display_rgb(dn,valid):
    # DN remains untouched in the analytical GeoTIFF. One monotone curve per band
    # controls display only; no sharpening, super-resolution or generated pixels.
    rgb=np.moveaxis(dn[[2,1,0]],0,-1)
    low=np.percentile(rgb[valid],.5,axis=0)
    high=np.percentile(rgb[valid],99.8,axis=0)
    linear=np.clip((rgb-low)/np.maximum(high-low,1),0,1)
    display=np.clip(.035+.94*np.power(linear,.72),0,1)
    display[~valid]=0
    return np.round(display*255).astype('uint8'),dict(percentiles=[.5,99.8],low_dn=low.tolist(),high_dn=high.tolist(),gamma=.72,black_lift=.035,note='display stretch, not calibrated reflectance')


def old_mapping_error():
    # Compare the old rectangle interpolation to the actual source georeferencing.
    xs,ys=np.meshgrid(np.linspace(EXTENT[0],EXTENT[2],21),np.linspace(EXTENT[1],EXTENT[3],21))
    u=(xs-EXTENT[0])/(EXTENT[2]-EXTENT[0]); v=(ys-EXTENT[1])/(EXTENT[3]-EXTENT[1])
    a,b,c,d,e,f=DATA['gf2']['crop_transform']
    _,oldh,oldw=DATA['gf2']['shape']
    lon=c+a*u*oldw; lat=f+e*(1-v)*oldh
    tx=Transformer.from_crs('EPSG:4326','EPSG:32650',always_xy=True)
    actualx,actualy=tx.transform(lon,lat)
    err=np.hypot(actualx-X0-xs,actualy-Y0-ys)
    return dict(grid_points=err.size,median_m=float(np.median(err)),max_m=float(err.max()),
                note='Old UV/interpolation-induced discrepancy only; not measured absolute geolocation error.')


def identify_roof_offsets(red_mask, footprints, building_ids):
    """Conservative roof-only registration from independently segmented red regions.

    The shift maps OSM ground footprint coordinates to visible roof pixels.
    It is NOT a correction of the survey coordinate system or building position.
    """
    rr,cc=np.nonzero(red_mask)
    best=(-1,0,0)
    scores=[]
    for dy in range(-40,26):
        for dx in range(-22,23):
            ir,ic=rr-dy,cc-dx
            ok=(ir>=0)&(ir<H)&(ic>=0)&(ic<W)
            coverage=float((building_ids[ir[ok],ic[ok]]>0).sum()/max(1,len(rr)))
            score=coverage-.000003*(dx*dx+dy*dy)
            if score>best[0]:best=(score,dx,dy)
            scores.append((coverage,dx,dy))
    _,gx,gy=best
    offsets={}
    for i,p in enumerate(footprints):
        inner=p.buffer(-1.2)
        if inner.is_empty:continue
        mask=rasterize([(mapping(inner),1)],out_shape=(H,W),transform=LOCAL,dtype='uint8').astype(bool)
        br,bc=np.nonzero(mask)
        if len(br)<80:continue
        bestlocal=(-1,0,0)
        baseline=float(red_mask[br,bc].mean())
        for dy in range(gy-5,gy+6):
            for dx in range(gx-5,gx+6):
                r,c=br+dy,bc+dx
                ok=(r>=0)&(r<H)&(c>=0)&(c<W)
                ratio=float(red_mask[r[ok],c[ok]].sum()/len(br))
                score=ratio-.0005*((dx-gx)**2+(dy-gy)**2)
                if score>bestlocal[0]:bestlocal=(score,dx,dy)
        score,dx,dy=bestlocal
        if score>.55 and score-baseline>.25:
            offsets[i]=dict(dx_m=round(dx*LOCAL.a,4),dy_m=round(dy*LOCAL.e,4),
                       support_before=round(baseline,4),support_after_penalized=round(score,4),
                       method='red-spectrum overlap with eroded OSM roof template; roof UV only')
    return offsets,dict(global_seed_pixel_shift=[gx,gy],global_seed_meter_shift=[gx*LOCAL.a,gy*LOCAL.e],
               red_pixels=len(rr),accepted_red_roofs=len(offsets),
               caution='relative image-to-footprint hypothesis; not ground-control registration')


def main():
    inventory=source_inventory()
    dn=reread();valid=np.all(dn>0,axis=0)
    rgb,stretch=display_rgb(dn,valid)
    blue,green,red,nir=dn
    ndvi=np.divide(nir-red,nir+red,out=np.zeros_like(red),where=(nir+red)>0)
    # This is NDVI calculated on pansharpened DN, not surface reflectance NDVI.
    brightness=dn[:3].mean(axis=0)
    shadow_limit=float(np.percentile(brightness[valid],12))
    shadow=valid & (brightness<shadow_limit)
    scale=np.clip((ndvi+1)*127.5,0,255).astype('uint8')
    otsu,_=cv2.threshold(scale[valid],0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    veg_threshold=float(np.clip(otsu/127.5-1,.08,.22))
    veg=(ndvi>veg_threshold)&valid&~shadow
    veg=cv2.morphologyEx(veg.astype('uint8'),cv2.MORPH_OPEN,np.ones((3,3),np.uint8)).astype(bool)
    footprints=[Polygon(b['coords']) for b in DATA['buildings']]
    building_ids=rasterize([(mapping(p),i+1) for i,p in enumerate(footprints)],out_shape=(H,W),transform=LOCAL,fill=0,dtype='uint16')
    hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV).astype(float)
    r,g,b=np.moveaxis(rgb.astype(float),-1,0)
    redroof=((hsv[:,:,0]<17)|(hsv[:,:,0]>168))&(hsv[:,:,1]>65)&(r>g*1.15)&~veg&~shadow
    coolroof=(b>r*1.10)&(hsv[:,:,1]>40)&~veg&~shadow
    lum=rgb.mean(axis=2)
    light=(lum>150)&~veg&~shadow&~redroof&~coolroof
    roof_offsets,registration=identify_roof_offsets(redroof,footprints,building_ids)
    surface=np.zeros((H,W),dtype='uint8')
    surface[valid]=1;surface[shadow]=2;surface[veg]=3
    surface[(building_ids>0)&~shadow&~veg]=4
    surface[(building_ids>0)&redroof]=5
    surface[(building_ids>0)&coolroof]=6
    surface[(building_ids>0)&light]=7
    records=[]
    for i,building in enumerate(DATA['buildings']):
        from shapely.affinity import translate
        offset=roof_offsets.get(i)
        sampling_polygon=translate(footprints[i],offset['dx_m'],offset['dy_m']) if offset else footprints[i]
        inner=sampling_polygon.buffer(-1.2)
        if inner.is_empty:inner=footprints[i]
        mask=rasterize([(mapping(inner),1)],out_shape=(H,W),transform=LOCAL,dtype='uint8').astype(bool)&valid
        clean=mask&~shadow&~veg
        denom=max(1,int(mask.sum()));clean_count=int(clean.sum())
        rf=float((redroof&clean).sum()/max(1,clean_count));cf=float((coolroof&clean).sum()/max(1,clean_count))
        lf=float((light&clean).sum()/max(1,clean_count))
        quality=clean_count/denom
        kind='uncertain' if quality<.40 or clean_count<20 else 'red_roof' if rf>.45 else 'blue_green_roof' if cf>.45 else 'light_roof' if lf>.5 else 'gray_mixed_roof'
        med=np.median(rgb[clean],axis=0) if clean_count else np.array([160,160,150])
        obs=dict(roof_class=kind,roof_color_srgb=[int(x) for x in med],usable_pixel_count=clean_count,
                 usable_fraction=round(quality,4),vegetation_fraction=round(float((veg&mask).sum()/denom),4),
                 shadow_fraction=round(float((shadow&mask).sum()/denom),4),
                 red_fraction=round(rf,4),cool_fraction=round(cf,4),light_fraction=round(lf,4),
                 source='GF2 2025-06-24, original B3/B2/B1 and DN-based B4/B3 index',
                 method='OSM-constrained spectral thresholds; not independent building detection',
                 facade_source='unobserved: neutral placeholder, no roof-to-wall inference')
        obs['roof_sampling_offset']=offset
        obs['registration_status']='red_roof_candidate_aligned' if offset else 'unverified_original_projection'
        building['gf2_observation']=obs
        records.append(dict(osm_id=building['osm_id'],name=building['name'],**obs))
    # Recompute vegetation candidates in exactly the same metric grid.
    excluded=rasterize([(mapping(p.buffer(2)),1) for p in footprints]+
             [(mapping(Polygon(s['coords']).buffer(1)),1) for s in DATA['surfaces'] if s['kind'] in ['pitch','water']],
             out_shape=(H,W),transform=LOCAL,dtype='uint8').astype(bool)
    crown_mask=veg&~excluded
    score=gaussian_filter(np.where(crown_mask,ndvi,0),1.1)
    candidates=np.argwhere((score==maximum_filter(score,size=13))&crown_mask&(score>veg_threshold))
    candidates=sorted(candidates,key=lambda rc:float(score[tuple(rc)]),reverse=True)
    dist=distance_transform_edt(crown_mask,sampling=[abs(LOCAL.e),LOCAL.a])
    trees=[];positions=[]
    for row,col in candidates:
        x,y=LOCAL*(float(col)+.5,float(row)+.5)
        if any((x-px)**2+(y-py)**2<7.5**2 for px,py in positions):continue
        crown=float(np.clip(dist[row,col]+.8,1.8,5.0))
        trees.append(dict(x=round(x,2),y=round(y,2),ndvi=round(float(ndvi[row,col]),4),
                     crown_radius=round(crown,2),height=round(crown*2.0+1.5,2),
                     source='reprojected GF2 vegetation local maximum; height inferred'))
        positions.append((x,y))
        if len(trees)>=900:break
    DATA['trees']=trees
    DATA['vegetation'].update(tree_count=len(trees),gf2_ndvi_threshold=veg_threshold,
             method='v5: UTM GF2 DN-index vegetation, shadow/OSM masks, metric local maxima; no Sentinel-based geometry')
    DATA['gf2'].update(display_texture='assets/gf2_reanalysis_v5/truecolor_utm.png',
             analytical_raster='assets/gf2_reanalysis_v5/gf2_dn_utm.tif',
             reprojected_crs='EPSG:32650',reprojected_transform=list(AFFINE)[:6],
             reprojected_shape=[4,H,W],display_stretch=stretch)
    DATA['reanalysis_version']='20260905-v5'
    save_raster('gf2_dn_utm.tif',dn)
    save_raster('ndvi_dn_utm.tif',np.where(valid,ndvi,np.nan).astype('float32'))
    save_raster('surface_candidates_utm.tif',surface)
    save_png('truecolor_utm.png',rgb)
    colors=np.array([[0,0,0],[137,133,123],[55,59,72],[87,151,80],[175,170,158],[190,83,57],[68,144,174],[232,222,193]],dtype='uint8')
    save_png('surface_candidates.png',colors[surface])
    # Evidence overlay: only outlines and candidate markers, no generated scene content.
    overlay=rgb.copy()
    for i,p in enumerate(footprints):
        pixels=np.array([(~LOCAL)*(x,y) for x,y in p.exterior.coords],dtype=np.int32)
        cv2.polylines(overlay,[pixels],True,(255,222,93),1,cv2.LINE_AA)
        if i in roof_offsets:
            offset=roof_offsets[i]
            aligned=np.array([(~LOCAL)*(x+offset['dx_m'],y+offset['dy_m']) for x,y in p.exterior.coords],dtype=np.int32)
            cv2.polylines(overlay,[aligned],True,(72,222,255),1,cv2.LINE_AA)
    for tree in trees:
        px,py=(~LOCAL)*(tree['x'],tree['y'])
        cv2.circle(overlay,(round(px),round(py)),2,(90,240,173),1)
    save_png('footprint_vegetation_overlay.png',overlay)
    save_json(ROOT/'assets/campus_assets_v5.json',DATA)
    save_json(OUT/'building_observations.json',records)
    report=dict(version=DATA['reanalysis_version'],created_utc=datetime.now(timezone.utc).isoformat(),
        source_inventory=inventory,selected_source=str(SOURCE),source_bytes=SOURCE.stat().st_size,
        source_selection='retain full-valid PMS1 campus source; other swaths inventoried, not mosaicked',
        source_bands_verified=True,crs='EPSG:32650',origin_utm=[X0,Y0],local_extent_m=EXTENT,
        pixel_size_m=[AFFINE.a,abs(AFFINE.e)],shape=[H,W],valid_fraction=float(valid.mean()),
        old_uv_mapping_discrepancy=old_mapping_error(),display_stretch=stretch,
        roof_relative_registration=registration,
        method='deterministic spectral candidates constrained by existing OSM footprints',
        buildings=len(records),roof_class_counts=dict(Counter(r['roof_class'] for r in records)),
        vegetation_candidates=len(trees),vegetation_candidate_cap=900,vegetation_candidate_pool=len(candidates),vegetation_fraction=float(veg.mean()),
        dn_index_threshold=veg_threshold,shadow_brightness_dn_threshold=shadow_limit,
        limitations=['No calibrated reflectance','No independent ground control or classification accuracy measured',
                    'OSM outlines unchanged; off-nadir rooftop displacement and temporal mismatch may remain',
                    'Facades, window positions and building heights are not recovered from this nadir image',
                    'Attached artistic reference is not used as spectral or survey ground truth'])
    save_json(OUT/'report.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='source_inventory'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
