import copy
import unittest
from backend.official_sources import supplement_hours,review_hours,supplement_services


class OfficialSourcesTests(unittest.TestCase):
    def setUp(self):
        self.catalog={'pois':[{'id':'coffee','name':'测试咖啡','address':'科技楼二层大厅','hours_source':'unknown'}]}
        self.doc={'id':'test','review_status':'verified_web_page',
                  'source':{'url':'https://zwb.bnu.edu.cn/guide','retrieved_at':'2026-10-08',
                            'temporal_scope':'undated_service_guide'},
                  'hours':[{'poi_id':'coffee','identity':{'name':'测试咖啡','address':'科技楼二层大厅'},
                            'value':[['07:00','19:00']],'decision':'fill_missing'}]}

    def test_missing_hours_filled_with_evidence_without_mutating_input(self):
        before=copy.deepcopy(self.catalog)
        result=supplement_hours(self.catalog,self.doc)
        p=result['pois'][0]
        self.assertEqual(p['opening_hours'],[['07:00','19:00']])
        self.assertIsNone(p['field_evidence']['opening_hours']['observed_at'])
        self.assertEqual(before,self.catalog)
        self.assertEqual(supplement_hours(result,self.doc),result)

    def test_existing_or_explicit_unknown_preserved(self):
        for fields in ({'opening_hours':[['08:00','22:00']]},
                       {'opening_hours_text':'09:00或10:00开门'},
                       {'opening_hours':None,'field_evidence':{'opening_hours':{'source':'field_observation'}}},
                       {'hours_source':'user_report'}):
            c=copy.deepcopy(self.catalog);c['pois'][0].update(fields)
            self.assertEqual(supplement_hours(c,self.doc),c)

    def test_branch_name_address_and_inactive_records_not_applied(self):
        for fields in ({'id':'different-branch'},{'name':'另一个店'},{'address':'新乐群三层'},
                       {'status':'closed'},{'status':'archived'},{'status':'historical'}):
            c=copy.deepcopy(self.catalog);c['pois'][0].update(fields)
            self.assertEqual(supplement_hours(c,self.doc),c)

    def test_unreviewed_holiday_and_wrong_domain_do_not_apply(self):
        for change in ('unreviewed','holiday','domain','review_only'):
            d=copy.deepcopy(self.doc)
            if change=='unreviewed':d['review_status']='pending'
            if change=='holiday':d['source']['temporal_scope']='summer_2026'
            if change=='domain':d['source']['url']='https://zwb.bnu.edu.cn.evil.example/'
            if change=='review_only':d['hours'][0]['decision']='review_only'
            self.assertEqual(supplement_hours(self.catalog,d),self.catalog)

    def test_conflicts_remain_reviewable(self):
        self.catalog['pois'][0]['opening_hours']=[['09:00','23:00']]
        row=review_hours(self.catalog,self.doc)[0]
        self.assertEqual(row['reason'],'conflict_preserved')
        self.assertEqual(row['current_hours'],[['09:00','23:00']])
        self.assertEqual(row['proposed_hours'],[['07:00','19:00']])

    def test_invalid_time_is_rejected(self):
        self.doc['hours'][0]['value']=[['25:00','19:00']]
        with self.assertRaises(ValueError):supplement_hours(self.catalog,self.doc)

    def test_service_notes_are_dated_and_do_not_create_locations_or_hours(self):
        from backend.agent.tools import CampusTools
        c={'pois':[{'id':'parcel','name':'快递中心','source':'official','category':'service'}],
           'shops':[],'items':[],'locations':[]}
        d={'id':'parcel-test','review_status':'verified_web_page',
           'source':{'url':'https://news.bnu.edu.cn/example.htm','published_at':'2025-09-06','retrieved_at':'2026-10-08'},
           'services':[{'poi_id':'parcel','identity':{'name':'快递中心'},'summary':'中区柜机可自助取件；人工服务时间待核。'}]}
        result=supplement_services(c,d)
        self.assertNotIn('location',result['pois'][0]);self.assertNotIn('opening_hours',result['pois'][0])
        card=CampusTools(result).execute('get_place',{'poi_id':'parcel'}, {})['cards'][0]
        self.assertEqual(card['service_info']['published_at'],'2025-09-06')
        self.assertNotIn('field_evidence',card);self.assertNotIn('menu',card)
        self.assertEqual(supplement_services(result,d),result)
        c['pois'][0]['field_evidence']={'service_info':{'source':'manual'}}
        self.assertEqual(supplement_services(c,d),c)
