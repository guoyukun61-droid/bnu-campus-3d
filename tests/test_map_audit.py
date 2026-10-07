import unittest
import json
import struct
from backend.storage import ROOT,read
from shapely.geometry import Polygon,box

class MapAuditTests(unittest.TestCase):
    def test_buildings_preserved_and_sports_valid(self):
        old=read(ROOT/'assets/campus_assets_white_v4.json')
        new=read(ROOT/'assets/campus_assets_white_v5.json')
        self.assertEqual(old['buildings'],new['buildings'])
        self.assertEqual(old['coordinate_system'],new['coordinate_system'])
        report=read(ROOT/'output/scene_manifest_white_v5.json')
        self.assertTrue(report['protected_geometry_check'])
        self.assertEqual(report['protected_meshes'],313)
        self.assertEqual(len(report['added_surfaces']),2)
        polygons=[]
        for row in report['added_surfaces']:
            p=Polygon(row['coords']);self.assertTrue(p.is_valid);self.assertTrue(box(-452,-601,452,601).covers(p))
            self.assertFalse(any(p.intersection(Polygon(b['coords'])).area>.01 for b in old['buildings']))
            polygons.append(p)
        self.assertEqual(polygons[0].intersection(polygons[1]).area,0)

    def test_glb_contains_restored_meshes(self):
        with (ROOT/'output/bnu_campus_web_white_v5.glb').open('rb') as f:
            header=f.read(20);size=struct.unpack_from('<I',header,12)[0];doc=json.loads(f.read(size))
        names={n.get('name') for n in doc['nodes']}
        for ident in (267948582,267948583):self.assertIn('Surface_V5_Restored_'+str(ident),names)
        self.assertFalse(doc.get('images'))

if __name__=='__main__':unittest.main()
