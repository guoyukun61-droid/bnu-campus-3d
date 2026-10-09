import json
import threading
import unittest
import urllib.request
import urllib.error
from types import SimpleNamespace
from app_server import make_app_server

class ExploreHTTPTests(unittest.TestCase):
    def setUp(self):
        self.server=make_app_server(0,SimpleNamespace(model=SimpleNamespace(configured=False)))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=self.server.origin
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
    def test_preview_and_original_entries(self):
        for path in ('/','/map/','/explore/','/explore/index.html'):
            with urllib.request.urlopen(self.base+path) as r:
                self.assertEqual(r.status,200);self.assertIn(b'<!doctype html>',r.read().lower())
    def test_explicit_assets_and_art_provenance(self):
        for path in ('/explore/main.js','/explore/state.js','/explore/scene.js','/explore/materials.js','/explore/api.js','/explore/explore.css','/explore/art/paper-plaster-v1.png'):
            with urllib.request.urlopen(self.base+path) as r:self.assertEqual(r.status,200);self.assertGreater(len(r.read()),100)
        with urllib.request.urlopen(self.base+'/explore/art/manifest.json') as r:
            m=json.load(r);self.assertFalse(m['geometry_changed']);self.assertFalse(m['measured_facade'])
    def test_private_paths_remain_unavailable(self):
        for path in ('/data/life/contributions/state.json','/explore/../../CLAUDE.md','/explore/art/source.jpg','/explore/art/','/explore/art/ui-provenance-1.11.json'):
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(self.base+path)
            self.assertEqual(error.exception.code,404)
    def test_atelier_exact_routes_and_provenance(self):
        for path in ('/explore/?art=atelier','/explore/atelier.js','/explore/art/atelier-plaster-v1.png'):
            with urllib.request.urlopen(self.base+path) as response:
                self.assertEqual(response.status,200)
                self.assertGreater(len(response.read()),100)
        with urllib.request.urlopen(self.base+'/explore/art/atelier-manifest-v1.json') as response:
            manifest=json.load(response)
        self.assertFalse(manifest['geometry_changed'])
        self.assertFalse(manifest['measured_facade'])
        self.assertEqual(len(manifest['sample_buildings']),4)
    def test_watercolour_assets_have_exact_public_routes(self):
        for name in ('ginkgo-ornament-v1.png','ivory-paper-v1.png','atlas-ornament-v1.png'):
            with urllib.request.urlopen(self.base+'/explore/art/'+name) as r:
                self.assertEqual(r.status,200)
                self.assertEqual(r.headers['Content-Type'],'image/png')
                self.assertEqual(r.read(8),b'\x89PNG\r\n\x1a\n')
                self.assertEqual(r.headers['X-Content-Type-Options'],'nosniff')
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(self.base+'/explore/art/atlas-ornament-v1.manifest.json')
        self.assertEqual(error.exception.code,404)
    def test_building_directory_is_public_projection(self):
        with urllib.request.urlopen(self.base+'/api/app/buildings') as r:d=json.load(r)
        self.assertEqual(d['model'],'white_v7')
        self.assertEqual(len(d['buildings']),234)
        self.assertFalse(any('coords' in b or 'reference_observation' in b for b in d['buildings']))

if __name__=='__main__':unittest.main()
