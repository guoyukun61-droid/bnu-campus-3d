"""Read-only, explicit-ID supplements; reviewed human values always win."""
import copy
import re
from urllib.parse import urlsplit

HOURS_FIELDS=('opening_hours','opening_hours_text','hours_source','hours_notes')


def review_hours(catalog,document):
    """Compare a reviewed source with current records without fuzzy matching."""
    records={p['id']:p for p in catalog['pois']}
    result=[]
    for entry in document.get('hours',[]):
        p=records.get(entry['poi_id'])
        reason='review_only'
        if not p:
            reason='missing_entity'
        elif p.get('status') in ('historical','archived','closed'):
            reason='inactive_entity'
        elif any(p.get(k)!=v for k,v in entry['identity'].items()):
            reason='identity_changed'
        elif p.get('opening_hours')==entry['value']:
            reason='already_matches'
        elif p.get('opening_hours') or p.get('opening_hours_text'):
            reason='conflict_preserved'
        elif any(k in p.get('field_evidence',{}) for k in HOURS_FIELDS) or p.get('hours_source') not in (None,'','unknown'):
            reason='manual_or_prior_evidence_preserved'
        elif entry.get('decision')=='fill_missing':
            reason='fill_missing'
        result.append(dict(poi_id=entry['poi_id'],name=entry['identity']['name'],reason=reason,
                           current_hours=p.get('opening_hours') if p else None,
                           current_text=p.get('opening_hours_text') if p else None,
                           proposed_hours=entry['value']))
    return result


def supplement_hours(catalog,document):
    if not document:return catalog
    source=document['source']
    if (document.get('review_status')!='verified_web_page' or
        urlsplit(source['url']).hostname!='zwb.bnu.edu.cn' or
        source.get('temporal_scope')!='undated_service_guide'):
        return catalog
    result=copy.deepcopy(catalog)
    index={p['id']:p for p in result['pois']}
    eligible={r['poi_id'] for r in review_hours(catalog,document) if r['reason']=='fill_missing'}
    for entry in document['hours']:
        if entry['poi_id'] not in eligible:continue
        hours=entry['value']
        if (not isinstance(hours,list) or not hours or len(hours)>8 or
            any(not isinstance(pair,list) or len(pair)!=2 or
                any(not isinstance(t,str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',t) for t in pair)
                for pair in hours)):
            raise ValueError('Invalid official hours')
        p=index[entry['poi_id']]
        p.update(opening_hours=copy.deepcopy(hours),
                 opening_hours_text='；'.join('–'.join(pair) for pair in hours),
                 hours_source=source['url'],
                 hours_notes='学校服务指南公示；页面未标发布日期，节假日与临时调整请以现场公告为准。')
        for field in HOURS_FIELDS:
            p.setdefault('field_evidence',{})[field]=dict(source=source['url'],
                retrieved_at=source['retrieved_at'],published_at=None,observed_at=None,
                review_status='verified_web_page',batch=document['id'],
                evidence=entry['identity'])
    return result


def supplement_services(catalog,document):
    """Dated service descriptions, never geometric or live opening assertions."""
    if not document or document.get('review_status')!='verified_web_page':return catalog
    source=document['source']
    if urlsplit(source['url']).hostname!='news.bnu.edu.cn':return catalog
    result=copy.deepcopy(catalog)
    records={p['id']:p for p in result['pois']}
    for entry in document.get('services',[]):
        p=records.get(entry['poi_id'])
        if (not p or p.get('status') in ('historical','closed','archived') or
            p.get('service_info') or 'service_info' in p.get('field_evidence',{}) or
            any(p.get(k)!=v for k,v in entry['identity'].items())):continue
        p['service_info']=dict(summary=entry['summary'],source_url=source['url'],
                               published_at=source['published_at'],retrieved_at=source['retrieved_at'])
        p.setdefault('field_evidence',{})['service_info']=dict(source=source['url'],
            published_at=source['published_at'],retrieved_at=source['retrieved_at'],
            observed_at=None,batch=document['id'],review_status='verified_web_page')
    return result
