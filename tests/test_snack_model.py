import json
import struct
import unittest
from shapely.geometry import Polygon, box, Point
from backend.storage import ROOT, read
from backend.geo import CampusGeometry


class SnackModelTests(unittest.TestCase):
    def test_only_declared_building_records_changed(self):
        old=read(ROOT/'assets/campus_assets_white_v5.json')
        new=read(ROOT/'assets/campus_assets_white_v6.json')
        patch=read(ROOT/'assets/snack_blocks_v6.json')
        changed={x['osm_id'] for x in patch['changes']+patch['retained']}
        indexed={x['osm_id']:x for x in new['buildings']}
        self.assertEqual(old['coordinate_system'],new['coordinate_system'])
        self.assertEqual(old['surfaces'],new['surfaces'])
        for b in old['buildings']:
            if b['osm_id'] not in changed:self.assertEqual(b,indexed[b['osm_id']])
            self.assertEqual(b['coords'],indexed[b['osm_id']]['coords'])
        for b in patch['changes']:
            self.assertEqual(indexed[b['osm_id']]['floors'],2)
            self.assertEqual(indexed[b['osm_id']]['height'],8)
        self.assertEqual(indexed[499434918]['floors'],4)
        self.assertEqual(indexed[499435186]['floors'],5) # Dormitory != canteen
        self.assertIsNone(indexed[900000000003]['floors'])

    def test_new_footprint_has_no_overlap_and_uses_same_coordinate_frame(self):
        old=read(ROOT/'assets/campus_assets_white_v5.json')
        b=read(ROOT/'assets/snack_blocks_v6.json')['added'][0];p=Polygon(b['coords'])
        self.assertTrue(p.is_valid);self.assertTrue(box(-452,-601,452,601).covers(p))
        for other in old['buildings']:
            for part in other.get('parts',[other]):self.assertLessEqual(p.intersection(Polygon(part['coords'])).area,.001)
        geo=CampusGeometry()
        self.assertEqual(geo.classify(dict(x=p.centroid.x,y=p.centroid.y))[1],b['osm_id'])
        # Existing multipart wings must remain selectable, not just main footprints.
        shapes=dict(geo.buildings)
        self.assertTrue(shapes[900000000001].covers(Point(-375,-330)))

    def test_glb_manifest_and_both_web_entries_match(self):
        path=ROOT/'output/bnu_campus_web_white_v6.glb'
        with path.open('rb') as f:
            h=f.read(20);doc=json.loads(f.read(struct.unpack_from('<I',h,12)[0]))
        self.assertIn('Building_900000000003',{n.get('name') for n in doc['nodes']})
        self.assertFalse(doc.get('images'))
        report=read(ROOT/'output/scene_manifest_white_v6.json')
        self.assertTrue(report['protected_geometry_check'])
        self.assertEqual(report['protected_meshes'],308)
        self.assertTrue(all(d['outside_faces_preserved'] for d in report['detail_audit']))
        self.assertIn("whiteEdition ? 'white_v6'",(ROOT/'index.html').read_text(encoding='utf8'))
        self.assertIn('output/bnu_campus_web_white_v6.glb',(ROOT/'contribution_server.py').read_text(encoding='utf8'))

if __name__=='__main__':unittest.main()
