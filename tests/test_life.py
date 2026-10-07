import copy
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from backend.bootstrap import initialize
from backend.storage import read, write
from backend.recommendation import recommend, open_at
from backend.storage import timestamp
from backend.library import SimulatedLibraryAdapter, ReservationConflict
from backend.service import LifeService
from backend.collector import Collector, make_task, RequestFailure

class LifeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.directory=Path(self.temp.name)
        self.data=initialize(self.directory)
    def tearDown(self):self.temp.cleanup()
    def request(self,**changes):
        value=dict(current_location="教八",current_time="2026-09-21T11:45:00+08:00",
                   next_class=dict(time="2026-09-21T13:30:00+08:00",location="教九"),
                   budget=20,max_queue_minutes=10,available_minutes=105,taste=["辣"],mode="demo")
        value.update(changes);return value
    def test_seed_provenance_and_idempotence(self):
        self.assertGreaterEqual(len(self.data["items"]),100)
        self.assertGreaterEqual(len({s["poi_id"] for s in self.data["shops"] if s["source"]=="simulated"}),10)
        self.assertTrue(all(i["source"]=="simulated" for i in self.data["items"]))
        self.data["pois"][0]["name"]="人工更名";write(self.directory/"catalog.json",self.data)
        initialize(self.directory)
        self.assertEqual(read(self.directory/"catalog.json")["pois"][0]["name"],"人工更名")
    def test_spicy_budget_unique_shops(self):
        result=recommend(self.data,self.request())
        rows=result["recommendations"]
        self.assertEqual(len(rows),3)
        self.assertEqual(len({r["shop_id"] for r in rows}),3)
        self.assertTrue(all(r["price"]<=20 for r in rows))
        self.assertTrue(all(r["sources"]["item"]=="simulated" and r["sources"]["queue"]=="simulated" for r in rows))
        self.assertTrue(all("辣" in r["item"] for r in rows))
    def test_budget_15_and_no_rice(self):
        rows=recommend(self.data,self.request(budget=15,avoid=["米饭"]))["recommendations"]
        self.assertTrue(rows)
        lookup={i["id"]:i for i in self.data["items"]}
        self.assertTrue(all(r["price"]<=15 and "米饭" not in lookup[r["item_id"]]["tags"] for r in rows))
    def test_35_minutes_and_next_class_walking(self):
        r=self.request(available_minutes=35,next_class={"time":"2026-09-21T12:20:00+08:00","location":"教九"})
        # Current demo has no feasible 35-minute round trip: never relax the deadline.
        self.assertEqual(recommend(self.data,r)["recommendations"],[])
        # A controlled nearby fixture establishes that genuinely feasible rows pass.
        origin=self.data["locations"][0]
        self.data["pois"][0]["location"]={"x":origin["x"],"y":origin["y"]}
        rows=recommend(self.data,r)["recommendations"]
        self.assertTrue(rows)
        self.assertTrue(all(x["total_estimated_minutes"]<=35 and x["return_walking_minutes"]>=0 for x in rows))
    def test_no_candidates_not_fabricated(self):
        self.assertEqual(recommend(self.data,self.request(budget=1))["recommendations"],[])
        self.assertEqual(recommend(self.data,self.request(mode="verified"))["recommendations"],[])
    def test_food_safety_not_inferred(self):
        self.assertEqual(recommend(self.data,self.request(dietary_requirements=["无花生"]))["recommendations"],[])
    def test_historical_closed_and_hours(self):
        for p in self.data["pois"]:p["status"]="historical"
        self.assertEqual(recommend(self.data,self.request())["recommendations"],[])
        self.assertFalse(open_at([["10:00","12:00"]],timestamp("2026-09-21T11:59:00+08:00"),3))
        self.assertTrue(open_at([["22:00","02:00"]],timestamp("2026-09-22T01:00:00+08:00"),5))
    def test_missing_position_kept_but_simulated_walking(self):
        for p in self.data["pois"]:p["location"]=None
        rows=recommend(self.data,self.request())["recommendations"]
        self.assertTrue(rows)
        self.assertTrue(all(r["location"] is None and r["sources"]["walking"]=="simulated" for r in rows))
    def test_invalid_input(self):
        for patch in ({"budget":float("nan")},{"max_queue_minutes":-1},{"taste":"辣"},{"top_k":1.5},{"current_time":"11:45"},{"next_class":{"time":"2026-09-21T10:00:00+08:00","location":"教九"}}):
            with self.subTest(patch=patch),self.assertRaises(ValueError):recommend(self.data,self.request(**patch))
    def test_catalog_filter_and_unknowns(self):
        s=LifeService(self.directory)
        rows=s.get("/pois",{"zone":["nearby"]})["records"]
        self.assertEqual(len(rows),3)
        self.assertTrue(all(p["location"] is None for p in rows))
        self.assertEqual(len(s.get("/pois",{"building_id":["499434918"]})["records"]),4)
        self.assertFalse(s.coverage()["real_world_complete"])

class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.directory=Path(self.temp.name)
        self.lib=SimulatedLibraryAdapter(self.directory)
        self.data=dict(seat_id="demo-A01",user_id="demo-student-1",request_id="first",
                       start="2026-09-21T16:00:00+08:00",end="2026-09-21T17:00:00+08:00")
    def tearDown(self):self.temp.cleanup()
    def test_idempotence_conflict_cancel_persistence(self):
        first=self.lib.reserve(self.data)
        self.assertEqual(self.lib.reserve(self.data),first)
        with self.assertRaises(ReservationConflict):self.lib.reserve(dict(self.data,seat_id="demo-A02",request_id="second"))
        with self.assertRaises(ReservationConflict):self.lib.reserve(dict(self.data,user_id="demo-student-2"))
        with self.assertRaises(ReservationConflict):self.lib.reserve(dict(self.data,end="2026-09-21T18:00:00+08:00"))
        other=SimulatedLibraryAdapter(self.directory)
        self.assertEqual(len(other.reservations()),1)
        cancelled=self.lib.cancel(first["id"],self.data["user_id"])
        self.assertEqual(self.lib.cancel(first["id"],self.data["user_id"]),cancelled)
        self.assertTrue(self.lib.slots(self.data["start"],self.data["end"])[0]["available"])
        self.assertEqual(self.lib.reserve(self.data)["status"],"cancelled")
        self.assertEqual(self.lib.reserve(dict(self.data,request_id="new"))["status"],"active")
    def test_concurrent_double_booking(self):
        def reserve(user):
            try:return self.lib.reserve(dict(self.data,user_id=user))
            except ReservationConflict:return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(reserve,self.lib.users))
        self.assertEqual(sum(r is not None for r in results),1)
    def test_invalid_duration_and_seat(self):
        for patch in ({"seat_id":"real-seat"},{"user_id":"real-student"},{"end":"2026-09-21T15:00:00+08:00"},{"end":"2026-09-21T22:30:00+08:00"},{"start":"2026-09-21T16:00:00"},{"request_id":""}):
            with self.subTest(patch=patch),self.assertRaises(ValueError):self.lib.reserve(dict(self.data,**patch))

class FakeGeometry:
    def local_to_bd(self,x,y):return y,x

class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.directory=Path(self.temp.name)
        write(self.directory/"collection.json",dict(tasks=[make_task([0,0,500,500],"美食")],requests_total=0))
    def tearDown(self):self.temp.cleanup()
    def collector(self,fetch):return Collector(self.directory,FakeGeometry(),fetch,sleep=lambda n:None,clock=lambda:0)
    def test_circle_geometry_persisted_and_mode_locked(self):
        calls=[]
        def fetch(params,key):
            calls.append(params)
            return dict(status=0,total=0,results=[])
        state=self.collector(fetch).run("SECRET",geometry="circle")
        self.assertEqual(state["run_status"],"complete")
        self.assertEqual(calls[0]["location"],"250.0,250.0")
        self.assertEqual(calls[0]["radius"],374)
        self.assertNotIn("bounds",calls[0])
        self.assertEqual(state["query_geometry"],"circle")
        with self.assertRaises(ValueError):self.collector(fetch).run("SECRET",geometry="bounds")
    def test_permission_failure_audited_without_retry(self):
        def fetch(params,key):raise RequestFailure("api_9")
        state=self.collector(fetch).run("SECRET")
        self.assertEqual(state["last_run_requests"],1)
        self.assertEqual(state["last_attempt_status"],"request_failed")
        self.assertEqual(state["tasks"][0]["error"],"api_9")
    def test_pagination_budget_resume_no_key_leak(self):
        calls=[]
        def fetch(params,key):
            calls.append(params["page_num"])
            return dict(status=0,total=23,results=[{"uid":str(i),"name":"sample"} for i in range(params["page_num"]*20,min((params["page_num"]+1)*20,23))])
        s=self.collector(fetch).run("SECRET",max_requests=1)
        self.assertEqual(s["run_status"],"partial")
        s=self.collector(fetch).run("SECRET",max_requests=1)
        self.assertEqual(s["run_status"],"complete")
        self.assertEqual(calls,[0,1])
        self.assertEqual(len(s["tasks"][0]["uids"]),23)
        self.assertNotIn("SECRET","".join(p.read_text(encoding="utf-8") for p in self.directory.rglob("*.json")))
    def test_duplicate_missing_records_not_complete(self):
        def fetch(params,key):return dict(total=23,results=[{"uid":str(i)} for i in range(20)])
        s=self.collector(fetch).run("KEY",max_requests=2)
        self.assertEqual(s["tasks"][0]["status"],"split")
        self.assertEqual(s["run_status"],"partial")
        s=self.collector(fetch).run("KEY",max_requests=100)
        self.assertTrue(any(t["status"]=="incomplete" for t in s["tasks"]))
    def test_split_and_truncation(self):
        def fetch(params,key):return dict(total=150,results=[{"uid":"1"}])
        s=self.collector(fetch).run("KEY",max_requests=1)
        self.assertEqual(s["tasks"][0]["status"],"split")
        self.assertEqual(len(s["tasks"]),5)
        s=self.collector(fetch).run("KEY",max_requests=100)
        self.assertTrue(any(t["status"]=="truncated" for t in s["tasks"]))
        self.assertEqual(s["run_status"],"partial")
    def test_quota_stops_and_missing_key_skips_network(self):
        calls=[]
        def fetch(params,key):calls.append(1);raise RequestFailure("api_302")
        s=self.collector(fetch).run("")
        self.assertEqual(calls,[])
        self.assertEqual(s["run_status"],"blocked_missing_key")
        s=self.collector(fetch).run("KEY")
        self.assertEqual(len(calls),1);self.assertEqual(s["tasks"][0]["status"],"failed")
    def test_transport_retry_budget_counts_attempts(self):
        calls=[]
        def fetch(params,key):calls.append(1);raise RequestFailure("transport_error")
        self.collector(fetch).run("KEY",max_requests=2)
        self.assertEqual(len(calls),2)

if __name__=="__main__":unittest.main()
