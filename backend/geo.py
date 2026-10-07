"""Baidu conversion is approximate; geographic scope is not the GLB rectangle."""
from .storage import ROOT, read

class CampusGeometry:
    def __init__(self):
        import eviltransform
        from pyproj import Transformer
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        self.convert=eviltransform
        self.to_metric=Transformer.from_crs(4326,32650,always_xy=True)
        self.to_wgs=Transformer.from_crs(32650,4326,always_xy=True)
        assets=read(ROOT/"assets/campus_assets_white_v6.json")
        self.ox,self.oy=assets["coordinate_system"]["origin_utm"]
        self.boundary=Polygon(read(ROOT/"assets/campus_context_v4.json")["boundary"])
        self.region=self.boundary.buffer(1000)
        self.buildings=[(b["osm_id"],unary_union([Polygon(p["coords"]).buffer(0) for p in b.get("parts",[b])])) for b in assets["buildings"]]

    def bd_to_local(self,location):
        lat,lng=self.convert.bd2wgs(location["lat"],location["lng"])
        x,y=self.to_metric.transform(lng,lat)
        return dict(x=round(x-self.ox,2),y=round(y-self.oy,2)),dict(lng=lng,lat=lat)

    def local_to_bd(self,x,y):
        lng,lat=self.to_wgs.transform(x+self.ox,y+self.oy)
        glat,glng=self.convert.wgs2gcj(lat,lng)
        blat,blng=self.convert.gcj2bd(glat,glng)
        return blat,blng

    def classify(self,location):
        from shapely.geometry import Point
        point=Point(location["x"],location["y"])
        distance=self.boundary.distance(point)
        zone="campus" if self.boundary.covers(point) else "nearby" if distance<=1000 else "outside"
        matches=[bid for bid,shape in self.buildings if shape.covers(point)]
        bid=matches[0] if len(matches)==1 and zone=="campus" else None
        return zone,bid,round(distance,2)
