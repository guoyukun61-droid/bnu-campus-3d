"""Minimal runtime integrity checks for the editable JSON data contract."""
import math
def validate_catalog(data):
    if not isinstance(data,dict) or data.get("schema_version")!=1:
        raise ValueError("catalog schema_version 必须为1")
    for name in ("pois","shops","items","locations"):
        rows=data.get(name)
        if not isinstance(rows,list):raise ValueError(name+" 须为数组")
        ids=set()
        for row in rows:
            if not isinstance(row,dict) or not isinstance(row.get("id"),str) or not row["id"] or row["id"] in ids:
                raise ValueError(name+" 存在无效或重复ID")
            ids.add(row["id"])
            if not isinstance(row.get("name"),str) or not isinstance(row.get("source"),str):
                raise ValueError(name+" 缺少名称或来源")
    pois={r["id"] for r in data["pois"]};shops={r["id"] for r in data["shops"]}
    for shop in data["shops"]:
        if shop.get("poi_id") not in pois:raise ValueError("窗口缺少有效poi_id")
    for item in data["items"]:
        if item.get("shop_id") not in shops:raise ValueError("菜品缺少有效shop_id")
        price=item.get("price")
        if price is not None and (isinstance(price,bool) or not isinstance(price,(int,float)) or not math.isfinite(price) or price<0):
            raise ValueError("菜品价格必须是非负有限数或null")
        if not isinstance(item.get("tags"),list) or any(not isinstance(t,str) for t in item["tags"]):
            raise ValueError("菜品标签必须为字符串数组")
    for poi in data["pois"]:
        position=poi.get("location")
        if position is not None and (not isinstance(position,dict) or any(isinstance(position.get(k),bool) or not isinstance(position.get(k),(int,float)) or not math.isfinite(position[k]) for k in ("x","y"))):
            raise ValueError("地点坐标必须是有限x/y或null")
    return data

