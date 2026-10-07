"""Simulated reservation adapter. Single server process, lock + atomic persistence."""
import uuid
from datetime import timedelta
from .storage import LOCK, read, write, timestamp

class ReservationConflict(ValueError):pass

class SimulatedLibraryAdapter:
    source="simulated"
    seats=("demo-A01","demo-A02","demo-A03","demo-A04")
    users=("demo-student-1","demo-student-2")
    def __init__(self,directory):self.path=directory/"reservations.json"
    def reservations(self,user_id=None):
        rows=read(self.path,[])
        return [r for r in rows if not user_id or r["user_id"]==user_id]
    def validate_window(self,start,end):
        a,b=timestamp(start),timestamp(end)
        if b<=a or b-a>timedelta(hours=4) or a.date()!=b.date() or a.hour<8 or b.hour>22 or (b.hour==22 and b.minute):
            raise ValueError("模拟预约须在同日08:00–22:00内，时长不超过4小时")
        return a,b
    def overlaps(self,row,a,b):
        return row["status"]=="active" and timestamp(row["start"])<b and a<timestamp(row["end"])
    def slots(self,start,end):
        a,b=self.validate_window(start,end)
        rows=self.reservations()
        return [dict(id=seat,start=a.isoformat(),end=b.isoformat(),source=self.source,
            available=not any(r["seat_id"]==seat and self.overlaps(r,a,b) for r in rows)) for seat in self.seats]
    def reserve(self,data):
        if not isinstance(data,dict):raise ValueError("预约必须是对象")
        seat,user,key=data.get("seat_id"),data.get("user_id"),data.get("request_id")
        if seat not in self.seats or user not in self.users:raise ValueError("未知模拟座位或虚构用户")
        if not isinstance(key,str) or not 1<=len(key)<=100:raise ValueError("request_id 必填，最多100字符")
        a,b=self.validate_window(data.get("start"),data.get("end"))
        with LOCK:
            rows=self.reservations()
            previous=next((r for r in rows if r["request_id"]==key and r["user_id"]==user),None)
            if previous:
                if (previous["seat_id"],previous["start"],previous["end"])!=(seat,a.isoformat(),b.isoformat()):
                    raise ReservationConflict("相同 request_id 对应不同预约内容")
                return previous
            if any(self.overlaps(r,a,b) and (r["seat_id"]==seat or r["user_id"]==user) for r in rows):
                raise ReservationConflict("座位或用户在此时段已有模拟预约")
            record=dict(id="sim-"+uuid.uuid4().hex,request_id=key,seat_id=seat,user_id=user,
                        start=a.isoformat(),end=b.isoformat(),status="active",source=self.source)
            rows.append(record);write(self.path,rows)
            return record
    def cancel(self,record_id,user_id):
        with LOCK:
            rows=self.reservations()
            target=next((r for r in rows if r["id"]==record_id and r["user_id"]==user_id),None)
            if target is None:raise ValueError("未找到该用户的模拟预约")
            if target["status"]!="cancelled":
                target["status"]="cancelled";write(self.path,rows)
            return target

