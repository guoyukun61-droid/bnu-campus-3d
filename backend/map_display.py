"""Display-only building anchors never become routing coordinates."""
import math

def display_fields(p):
    result={}
    for field in ('display_anchor','map_reference'):
        row=p.get(field)
        if isinstance(row,dict) and row.get('crs')=='local EPSG:32650' and all(
            isinstance(row.get(k),(int,float)) and not isinstance(row[k],bool) and math.isfinite(row[k]) for k in ('x','y')):
            result[field]={k:row[k] for k in ('x','y','building_id','precision','label','relation') if k in row}
    row=p.get('spatial_sequence')
    if isinstance(row,dict):
        result['spatial_sequence']={k:row[k] for k in ('group','label','order','direction') if k in row}
    return result
