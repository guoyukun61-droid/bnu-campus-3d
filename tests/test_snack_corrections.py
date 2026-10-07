import copy
import hashlib
import unittest
from pathlib import Path
from shapely.geometry import Polygon, Point
from backend.snack_corrections import corrected_state, LUCKIN, LAIXIFU_CANDIDATE, COTTI, representative
from backend.contribution import overlay
from backend.agent.tools import CampusTools
from backend.agent.candidates import position
from backend.map_review import review_catalog
from backend.map_display import display_fields


class SnackCorrectionsTests(unittest.TestCase):
    def setUp(self):
        self.hours=[dict(name='fixture-'+str(i),poi_id='p'+str(i)) for i in range(38)]
        names={LUCKIN:'瑞幸咖啡', 'luckin':'瑞幸科技楼店','laixifu':'来喜福',LAIXIFU_CANDIDATE:'来喜福炒酸奶鸡蛋仔'}
        for name in ('乡村基','塔斯汀','鹏记重庆鸡公煲','夜罐罐米线'):
            names['reported-'+hashlib.sha256(name.encode()).hexdigest()[:16]]=name
        names.update({r['poi_id']:r['name'] for r in self.hours})
        self.catalog=dict(schema_version=1,pois=[dict(id=k,name=v,source='manual',category='coffee',
            location={'x':2,'y':3},location_crs='local EPSG:32650',opening_hours_text='原时段') for k,v in names.items()],
            shops=[dict(id='shop-'+k,poi_id=k,name=v,source='manual') for k,v in names.items()],items=[],locations=[])
        self.buildings=[dict(osm_id=i,coords=[[0,0],[10,0],[10,10],[0,10]]) for i in [499434918,172257586,499437078,499437130]]
        self.state=dict(version=10,audit=[],published={},submissions={'draft':{'status':'draft'}})

    def apply(self):
        state,ids=corrected_state(self.state,self.catalog,self.buildings,self.hours,'2026-10-02T12:00:00+08:00','photo-fixture')
        return state,{p['id']:p for p in overlay(self.catalog,state)['pois']}

    def test_does_not_mutate_or_overwrite_hours(self):
        old=copy.deepcopy(self.state);oldc=copy.deepcopy(self.catalog);s,p=self.apply()
        self.assertEqual(old,self.state);self.assertEqual(oldc,self.catalog)
        self.assertEqual(s['submissions'],self.state['submissions'])
        self.assertEqual(p['laixifu']['opening_hours_text'],'原时段')

    def test_branches_and_shop_floors(self):
        s,p=self.apply();self.assertEqual(p[LUCKIN]['floor'],'3');self.assertEqual(p['luckin']['floor'],'2')
        self.assertNotEqual(p[LUCKIN]['building_id'],p['luckin']['building_id'])
        self.assertEqual(s['published']['shops']['shop-'+LUCKIN]['floor'],'3')

    def test_same_building_not_fake_entrance(self):
        s,p=self.apply()
        for ident in ('laixifu',LAIXIFU_CANDIDATE):
            self.assertEqual(p[ident]['building_id'],499437078)
            self.assertIsNone(position(p[ident]))
            self.assertEqual(p[ident]['field_evidence']['location']['previous_value'],{'x':2,'y':3})

    def test_representative_is_inside_building(self):
        for b in self.buildings:
            p=representative(self.buildings,b['osm_id'])
            self.assertTrue(Polygon(b['coords']).covers(Point(p['x'],p['y'])))

    def test_sequence_no_coordinate_interpolation(self):
        s,p=self.apply()
        self.assertEqual([p['p'+str(i)]['spatial_sequence']['order'] for i in range(2,15)],list(range(1,14)))
        self.assertEqual(p['p15']['spatial_sequence']['order'],1)
        self.assertEqual(p['p3']['location'],{'x':2,'y':3})

    def test_photo_only_one_new_merchant(self):
        s,p=self.apply();self.assertEqual(len(p),len(self.catalog['pois'])+1)
        self.assertIsNone(p[COTTI]['location']);self.assertIsNone(p[COTTI]['building_id'])
        self.assertIsNone(p[COTTI]['opening_hours']);self.assertIsNone(p[COTTI]['spatial_sequence']['order'])

    def test_public_and_review_share_display_fields_not_private_evidence(self):
        s,p=self.apply();c=overlay(self.catalog,s)
        public=CampusTools.place(p['laixifu'])
        review=next(r for r in review_catalog(c,Path('__fixture__'))['rows'] if r['id']=='laixifu')
        self.assertEqual(public['display_anchor'],review['display_anchor'])
        self.assertIsNone(public['location']);self.assertFalse(review['on_map'])
        self.assertNotIn('field_evidence',public);self.assertNotIn('photo-fixture',str(public))

    def test_idempotency_and_changed_inventory(self):
        s,p=self.apply()
        with self.assertRaises(ValueError): corrected_state(s,self.catalog,self.buildings,self.hours,'at','sha')
        with self.assertRaises(ValueError): corrected_state(self.state,self.catalog,self.buildings,self.hours[:-1],'at','sha')

    def test_nonfinite_display_anchor_rejected(self):
        self.assertEqual(display_fields({'display_anchor':{'x':float('nan'),'y':2,'crs':'local EPSG:32650'}}),{})

if __name__=='__main__':unittest.main()
