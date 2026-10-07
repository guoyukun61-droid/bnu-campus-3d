import json, struct, unittest
from pathlib import Path
from shapely.geometry import Polygon, box
from backend.main_geometry import clip_north
from backend.agent.buildings import building_directory
ROOT=Path(__file__).resolve().parents[1]

def geometry_signatures(path):
    raw=path.read_bytes();n=struct.unpack_from('<I',raw,12)[0];d=json.loads(raw[20:20+n]);binary=raw[28+n:]
    def accessor(index):
        a=d['accessors'][index];v=d['bufferViews'][a['bufferView']]
        offset=v.get('byteOffset',0)+a.get('byteOffset',0)
        return (a['componentType'],a['type'],a['count'],binary[offset:v.get('byteOffset',0)+v['byteLength']])
    return {node['name']:[({k:accessor(v) for k,v in p['attributes'].items()},accessor(p['indices'])) for p in d['meshes'][node['mesh']]['primitives']] for node in d['nodes'] if 'mesh'in node}

class ExploreV18Tests(unittest.TestCase):
    def test_clipping_removes_self_intersection_not_by_buffering(self):
        d=json.loads((ROOT/'assets/campus_assets_white_v6.json').read_text(encoding='utf-8'))
        b=next(b for b in d['buildings'] if b['osm_id']==267948584)
        self.assertFalse(Polygon([p for p in b['coords'] if p[1]>-253]).is_valid)
        repaired=Polygon(clip_north(b['coords']))
        self.assertTrue(repaired.is_valid)
        expected=Polygon(b['coords']).intersection(box(-1000,-253,1000,1000))
        self.assertLess(repaired.symmetric_difference(expected).area,1e-7)
    def test_glb_unrelated_mesh_buffers_unchanged(self):
        before=geometry_signatures(ROOT/'output/bnu_campus_web_white_v6.glb')
        after=geometry_signatures(ROOT/'output/bnu_campus_web_white_v7.glb')
        self.assertEqual(set(before),set(after))
        changed=[n for n in before if before[n]!=after[n]]
        self.assertEqual(set(changed),{'Building_267948584','Reference_Detail_267948584'})
    def test_public_building_contract(self):
        d=building_directory();self.assertEqual(len(d['buildings']),234)
        tech=next(b for b in d['buildings'] if b['id']=='172257586')
        self.assertEqual(tech['name'],'科技楼')
        self.assertEqual(set(tech),{'id','name','description','source','description_status'})
        self.assertNotIn('瑞幸',tech['name'])

if __name__=='__main__':unittest.main()
