import tempfile
import unittest
from pathlib import Path
from backend.map_review import review_catalog


class MapReviewTest(unittest.TestCase):
    def test_coordinates_and_simulation(self):
        rows=[dict(id='a',name='same',location={'x':0,'y':0},location_crs='local EPSG:32650'),
              dict(id='b',name='same',location={'x':0,'y':0},location_crs='BD09'),
              dict(id='c',location={'x':900,'y':0},location_crs='local EPSG:32650'),
              dict(id='s',source='simulated')]
        with tempfile.TemporaryDirectory() as tmp:
            result=review_catalog(dict(pois=rows,shops=[],items=[]),Path(tmp))
        self.assertEqual(result['counts']['pois'],3)
        self.assertEqual(result['counts']['on_map'],1)
        self.assertEqual(result['counts']['missing_coordinates'],1)

    def test_menu_link_and_conditional_hours(self):
        catalog=dict(pois=[dict(id='p',opening_hours_text='09:00或10:00')],
            shops=[dict(id='s',poi_id='p',independent_window_verified=False)],
            items=[dict(id='i',shop_id='s',price=None),dict(id='demo',shop_id='s',source='simulated')])
        with tempfile.TemporaryDirectory() as tmp:
            result=review_catalog(catalog,Path(tmp))
        self.assertEqual(result['counts']['real_items'],1)
        self.assertEqual(result['counts']['unknown_prices'],1)
        self.assertIn('菜单所属独立窗口待确认',result['rows'][0]['issues'])
        self.assertIn('条件营业时间待明确',result['rows'][0]['issues'])
