import copy
import unittest
from backend.poi_corrections import corrected_state,AED,JIEDIAN
from backend.contribution import overlay
from backend.agent.tools import CampusTools
from backend.map_review import review_catalog
from pathlib import Path


class CorrectionTests(unittest.TestCase):
    def setUp(self):
        self.catalog=dict(schema_version=1,pois=[
            dict(id=AED,name='AED(北京师范大学)',source='baidu',category='other',location={'x':1,'y':2},location_crs='local EPSG:32650'),
            dict(id=JIEDIAN,name='街电(巴依老爷新疆美食北师大店)',source='baidu',category='service',location={'x':3,'y':4},location_crs='local EPSG:32650',map_point={'x':3,'y':4,'crs':'local EPSG:32650'},building_id=10),
            dict(id='untouched',name='原店',source='manual',location={'x':5,'y':6})],shops=[],items=[],locations=[])
        self.state=dict(version=2,audit=[],published={'pois':{JIEDIAN:{'opening_hours_text':'原时段'}}},submissions=[{'id':'draft','status':'draft'}])
    def test_exact_name_keeps_raw_evidence(self):
        new=corrected_state(self.state,self.catalog,'2026-10-02T12:00:00+08:00')
        row=overlay(self.catalog,new)['pois'][0]
        self.assertEqual(row['name'],'邱季端体育场');self.assertEqual(row['original_name'],'AED(北京师范大学)')
        self.assertEqual(row['location'],{'x':1,'y':2});self.assertEqual(row['source'],'baidu')
    def test_invalid_marker_hidden_in_both_consumers(self):
        new=corrected_state(self.state,self.catalog,'2026-10-02T12:00:00+08:00');merged=overlay(self.catalog,new)
        row=merged['pois'][1]
        self.assertIsNone(row['location']);self.assertIsNone(row['map_point']);self.assertIsNone(row['building_id'])
        self.assertEqual(row['field_evidence']['location']['previous_value'],{'x':3,'y':4})
        self.assertIsNone(CampusTools(merged).directory()['pois'][1]['location'])
        self.assertFalse(review_catalog(merged,Path('__fixture_no_private_data__'))['rows'][1]['on_map'])
    def test_no_mutation_and_preserves_other_records(self):
        before=copy.deepcopy(self.state);new=corrected_state(self.state,self.catalog,'2026-10-02T12:00:00+08:00')
        self.assertEqual(before,self.state);self.assertEqual(new['submissions'],before['submissions'])
        self.assertEqual(new['published']['pois'][JIEDIAN]['opening_hours_text'],'原时段')
        self.assertEqual(new['version'],3);self.assertEqual(overlay(self.catalog,new)['pois'][2],self.catalog['pois'][2])
    def test_repeat_rejected(self):
        new=corrected_state(self.state,self.catalog,'2026-10-02T12:00:00+08:00')
        with self.assertRaises(ValueError):corrected_state(new,self.catalog,'2026-10-02T12:01:00+08:00')

if __name__=='__main__':unittest.main()
