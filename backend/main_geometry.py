"""Clip a footprint against the existing portico boundary, retaining edge intersections."""
def clip_north(coords, boundary=-253.0):
    result=[]
    for a,b in zip(coords,coords[1:]+coords[:1]):
        inside_a,inside_b=a[1]>=boundary,b[1]>=boundary
        if inside_a != inside_b:
            t=(boundary-a[1])/(b[1]-a[1])
            result.append([a[0]+t*(b[0]-a[0]),boundary])
        if inside_b:result.append(list(b))
    area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(result,result[1:]+result[:1]))
    return result if area>0 else result[::-1]
