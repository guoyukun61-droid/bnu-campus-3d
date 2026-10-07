import unittest
from backend.import_field_batch import hours_value, compatible, transcriptions


class FieldBatchTests(unittest.TestCase):
    def test_uncertain_calendar_not_daily(self):
        self.assertIsNone(hours_value('09:00或10:00-23:30'))
        self.assertIsNone(hours_value('07:30-23:00（休息日08:00-23:00）'))
        self.assertIsNone(hours_value('08:00-22:00（大假09:00-19:00）'))
        self.assertEqual(hours_value('00:00-24:00'), [['00:00','00:00']])
        self.assertEqual(hours_value('09:00-21:00'), [['09:00','21:00']])

    def test_rebase_preserves_other_fields_but_rejects_conflicting_price(self):
        record=dict(base=dict(price=10,name='测试'),patch=dict(price=12))
        self.assertTrue(compatible(record,dict(price=10,name='更新名称')))
        self.assertTrue(compatible(record,dict(price=12,name='更新名称')))
        self.assertFalse(compatible(record,dict(price=15,name='更新名称')))

    def test_photo_inventory_and_floor_conflict(self):
        rows=transcriptions('@1|待核|测试菜单\n菜品=?;饮品=8/10\n!小杯大杯待核\n@2|4|另一菜单\n主食=16')
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['floor'],'待核')
        self.assertEqual(rows[0]['notes'],['小杯大杯待核'])
        self.assertTrue(any(i['raw_price']=='?' for r in rows for i in r['items']))


if __name__=='__main__':unittest.main()
