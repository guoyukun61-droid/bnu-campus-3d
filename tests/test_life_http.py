import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
import campus_server as server
from backend.bootstrap import initialize

class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.old_db,cls.old_life=server.DB,server.LIFE_DIR
        server.DB=Path(cls.temp.name)/"legacy.sqlite3"
        server.LIFE_DIR=Path(cls.temp.name)/"life"
        server.init();initialize(server.LIFE_DIR)
        cls.server=server.ThreadingHTTPServer(("127.0.0.1",0),server.Handler)
        cls.url="http://127.0.0.1:"+str(cls.server.server_port)
        threading.Thread(target=cls.server.serve_forever,daemon=True).start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close()
        server.DB,server.LIFE_DIR=cls.old_db,cls.old_life;cls.temp.cleanup()
    def request(self,path,data=None,origin=True):
        headers={"Content-Type":"application/json"}
        if origin:headers["Origin"]=self.url
        req=urllib.request.Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        try:
            with urllib.request.urlopen(req) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as error:return error.code,json.load(error)
    def test_get_post_validation_and_private_files(self):
        for path in ("/api/life/pois","/api/life/shops","/api/life/items","/api/life/coverage","/api/life/locations","/api/life/schedule"):
            self.assertEqual(self.request(path)[0],200)
        for path in ("/data/life/catalog.json","/backend/seeds/ranking.json","/.git/config"):
            self.assertEqual(self.request(path)[0],403)
        self.assertEqual(self.request("/api/life/recommendations",{},False)[0],403)
        self.assertEqual(self.request("/api/life/recommendations",{})[0],400)
        self.assertEqual(self.request("/api/life/unknown")[0],404)
    def test_recommendation_and_reservation_http(self):
        req=dict(current_time="2026-09-21T11:45:00+08:00",current_location="教八",budget=20)
        code,body=self.request("/api/life/recommendations",req)
        self.assertEqual(code,200);self.assertEqual(len(body["recommendations"]),3)
        booking=dict(seat_id="demo-A01",user_id="demo-student-1",request_id="http-test",
                     start="2026-09-21T16:00:00+08:00",end="2026-09-21T17:00:00+08:00")
        code,first=self.request("/api/life/library/reservations",booking)
        self.assertEqual(code,200)
        self.assertEqual(self.request("/api/life/library/reservations",dict(booking,user_id="demo-student-2"))[0],409)
        self.assertEqual(self.request("/api/life/library/reservations/"+first["id"]+"/cancel",{"user_id":booking["user_id"]})[1]["status"],"cancelled")

if __name__=="__main__":unittest.main()

