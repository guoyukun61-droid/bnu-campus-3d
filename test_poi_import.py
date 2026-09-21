import unittest
import import_baidu_pois as importer

class ImportTest(unittest.TestCase):
    def test_reviewed_coordinates_and_links(self):
        rows,report=importer.prepare()
        self.assertEqual(len(rows),12)
        self.assertEqual(len({r['id'] for r in rows}),12)
        by_name={r['name']:r for r in rows}
        self.assertEqual(by_name['学10楼']['building_id'],267948892)
        self.assertEqual(by_name['北京师范大学餐饮服务中心']['building_id'],681441378)
        self.assertIsNone(by_name['兰蕙餐厅']['building_id'])
        self.assertEqual(by_name['兰蕙餐厅']['floor'],'2楼')
        self.assertIsNone(by_name['留学生第三公寓']['building_id'])
        self.assertTrue(all(abs(r['x'])<=452 and abs(r['y'])<=601 for r in rows))
        self.assertTrue(all(r['status']=='unverified' for r in rows))

if __name__=='__main__':unittest.main()
