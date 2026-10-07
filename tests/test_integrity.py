import sqlite3
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.adapters import CatalogAdapter
from backend.bootstrap import initialize
from backend.schemas import validate_catalog
from backend.geo import CampusGeometry
from backend.collector import normalize
from backend.storage import read, write

class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
        self.catalog=initialize(self.path/"life")
    def tearDown(self):self.temp.cleanup()
    def test_orphans_invalid_price_and_duplicate_ids(self):
        self.catalog["items"][0]["shop_id"]="missing"
        with self.assertRaises(ValueError):validate_catalog(self.catalog)
        self.catalog["items"][0]["shop_id"]=self.catalog["shops"][0]["id"]
        self.catalog["items"][0]["price"]=float("nan")
        with self.assertRaises(ValueError):validate_catalog(self.catalog)
        self.catalog["items"][0]["price"]=12
        self.catalog["pois"].append(dict(self.catalog["pois"][0]))
        with self.assertRaises(ValueError):validate_catalog(self.catalog)
    def test_legacy_user_edits_and_uid_deduplication(self):
        db=self.path/"legacy.sqlite3"
        c=sqlite3.connect(db)
        c.execute("CREATE TABLE records(id TEXT, payload TEXT)")
        row=dict(id="baidu-373cf757b9861d774354d750",name="兰蕙餐厅（人工核验）",source="user",
                 category="canteen",status="archived",revision=8,x=-390,y=-375,building_id=900000000001)
        c.execute("INSERT INTO records VALUES(?,?)",(row["id"],json.dumps(row)));c.commit();c.close()
        write(self.path/"life/baidu_normalized.json",[dict(id=row["id"],name="百度旧名")])
        before=db.read_bytes()
        data=CatalogAdapter(self.path/"life",db).snapshot()
        p=next(p for p in data["pois"] if p["id"]=="lanhui")
        self.assertEqual(p["name"],row["name"]);self.assertEqual(p["status"],"archived")
        self.assertFalse(any(p["id"]==row["id"] for p in data["pois"]))
        self.assertEqual(before,db.read_bytes())
    def test_spatial_buffer_and_distinct_same_name_branches(self):
        geo=CampusGeometry()
        point,wgs=geo.bd_to_local({"lng":116.366,"lat":39.968})
        self.assertIn(geo.classify(point)[0],{"campus","nearby","outside"})
        self.assertEqual(geo.classify({"x":5000,"y":5000})[0],"outside")
        self.assertEqual(geo.classify({"x":800,"y":0})[0],"nearby")
        self.assertEqual(geo.classify({"x":0,"y":0})[0],"campus")
        # Round trip is approximate but should stay within 10 m, never hundreds.
        bd=geo.local_to_bd(0,0)
        local,_=geo.bd_to_local({"lat":bd[0],"lng":bd[1]})
        self.assertLess(abs(local["x"]),10);self.assertLess(abs(local["y"]),10)
    def test_imported_shop_identity_without_invented_menu(self):
        directory=self.path/"life"
        write(directory/"baidu_normalized.json",[
            dict(id="baidu-coffee-a",name="测试咖啡一店",category="coffee",source="baidu_place_v2",status="unverified"),
            dict(id="baidu-coffee-b",name="测试咖啡二店",category="coffee",source="baidu_place_v2",status="unverified")])
        data=CatalogAdapter(directory).snapshot()
        shops=[s for s in data["shops"] if s["id"].startswith("shop-baidu-")]
        self.assertEqual(len(shops),2)
        self.assertTrue(all(s["menu_status"]=="missing" for s in shops))
        self.assertFalse(any(i["shop_id"] in {s["id"] for s in shops} for i in data["items"]))
        validate_catalog(data)
    def test_normalizer_retains_manual_version_and_proposes_changes(self):
        directory=self.path/"life"
        class Geometry:
            def bd_to_local(self,p):return ({"x":p["lng"],"y":p["lat"]},p)
            def classify(self,p):return ("campus",None,0)
        write(directory/"raw/one.json",dict(retrieved_at="2026-09-21",result={"results":[
            {"uid":"test-a","name":"测试分店","address":"一楼","location":{"lng":1,"lat":1}},
            {"uid":"test-b","name":"测试分店","address":"二楼","location":{"lng":1,"lat":1}}]}))
        # No user database or historical audit is involved.
        with patch("backend.collector.ROOT",self.path):
            rows=normalize(directory,Geometry())
            self.assertEqual(len(rows),2)
            rows[0]["name"]="人工店名";write(directory/"baidu_normalized.json",rows)
            again=normalize(directory,Geometry())
            self.assertEqual(again[0]["name"],"人工店名")
            self.assertEqual(len(read(directory/"update_candidates.json")),1)
            self.assertEqual(len(again),2)

if __name__=="__main__":unittest.main()
