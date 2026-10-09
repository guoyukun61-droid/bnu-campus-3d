"""Evidence-aware candidates, separate from the existing strict recommender."""
import math
import re
from collections import Counter
from datetime import timedelta
from ..storage import now, timestamp
from ..recommendation import open_at
from ..adapters import SimulatedCrowdAdapter
from .model import config
from .presentation import clean_card, category_info
from ..confirmed_relations import public_confirmations

FIELDS={'budget','taste','avoid','likes','current_location','available_minutes','max_queue_minutes','next_class','exclude_poi_ids','exclude_outlet_ids','dietary_requirements'}


def merge_conditions(old, patch):
    if not isinstance(old,dict) or not isinstance(patch,dict):raise ValueError('条件须为对象')
    if set(patch)-FIELDS:raise ValueError('包含不支持的条件')
    result={k:v for k,v in old.items() if k in FIELDS}
    for k,v in patch.items():
        if v is None: result.pop(k,None)
        else: result[k]=v
    for k in ('budget','available_minutes','max_queue_minutes'):
        if k in result and (isinstance(result[k],bool) or not isinstance(result[k],(int,float)) or not math.isfinite(result[k]) or not 0<=result[k]<=10000):
            raise ValueError(k+'数值无效')
    for k in ('taste','avoid','likes','exclude_poi_ids','exclude_outlet_ids','dietary_requirements'):
        if k in result and (not isinstance(result[k],list) or len(result[k])>30 or any(not isinstance(v,str) or len(v)>100 for v in result[k])):raise ValueError(k+'须为短文本数组')
    if 'current_location' in result and (not isinstance(result['current_location'],str) or len(result['current_location'])>100):raise ValueError('位置无效')
    if 'next_class' in result:
        n=result['next_class']
        if not isinstance(n,dict) or set(n)!={'time','location'} or not isinstance(n['location'],str):raise ValueError('下一课须包含时间和位置')
        timestamp(n['time'])
    return result


def position(p):
    loc=p.get('map_point') or p.get('location')
    crs=(loc or {}).get('crs',p.get('location_crs'))
    if crs!='local EPSG:32650' or not loc or not all(isinstance(loc.get(k),(int,float)) and math.isfinite(loc[k]) for k in ('x','y')):return None
    return dict(x=loc['x'],y=loc['y'])


def outlet_hours(outlet):
    """Window hours belong to that window; do not fill them from its floor."""
    hours=outlet.get('opening_hours')
    text=outlet.get('opening_hours_text') or ('；'.join('–'.join(v) for v in hours) if hours else '')
    return dict(opening_hours=hours if hours else None,opening_hours_text=text or None,
                hours_label=text or '尚未录入')


def recommend_candidates(catalog, conditions, mode='real', at=None, *, eligible_poi_ids=None):
    from ..menu_relations import build_menu_relations
    c=merge_conditions({},conditions); cfg=config(); at=timestamp(at or now())
    if mode not in ('real','demo'):raise ValueError('模式无效')
    missing=[]
    if 'budget' not in c:missing.append('这次每人预算大约多少元？')
    locations={p['id']:p for p in catalog['pois']}
    locations.update({p['id']:dict(p,location={'x':p['x'],'y':p['y']},location_crs='local EPSG:32650') for p in catalog['locations']})
    origin=locations.get(c.get('current_location'))
    if ('available_minutes' in c or 'next_class' in c) and (not origin or not position(origin)):
        missing.append('请在位置选择器中选择当前位置，以便检查时间条件。')
    if missing:return dict(cards=[],clarification=' '.join(missing),conditions=c,rejected={})
    destination=None; available=c.get('available_minutes')
    if c.get('next_class'):
        destination=locations.get(c['next_class']['location'])
        if not destination or not position(destination):return dict(cards=[],clarification='下一节课在哪里？请选择有坐标的课堂位置。',conditions=c,rejected={})
        minutes=(timestamp(c['next_class']['time'])-at).total_seconds()/60
        if minutes<=0:raise ValueError('下一节课时间必须晚于当前时间')
        available=min(available,minutes) if available is not None else minutes
    pois={p['id']:p for p in catalog['pois']}; shops={s['id']:s for s in catalog['shops']}; rejected=Counter(); candidates=[]
    menu_data=build_menu_relations(catalog);membership=menu_data['item_membership']
    outlets={o['id']:o for o in menu_data.get('outlets',[])}
    valid_outlets={m['outlet_id'] for m in membership.values() if m.get('outlet_id')}
    if any(ident not in valid_outlets for ident in c.get('exclude_outlet_ids',[])):
        raise ValueError('排除窗口ID无效，不接受楼层或菜单组ID')
    for item in catalog['items']:
        shop=shops.get(item.get('shop_id')); poi=pois.get(shop.get('poi_id')) if shop else None
        if not poi:continue
        if eligible_poi_ids is not None and poi['id'] not in eligible_poi_ids:continue
        member=membership[item['id']]
        outlet=outlets.get(member.get('outlet_id'))
        display_shop=outlet.get('name') if outlet else shop.get('name','')
        if category_info(poi)['display_category'] in ('retail','services','sports','campus','drinks'):
            rejected['非正餐场所']+=1;continue
        if mode=='real' and member['data_mode']=='simulated':continue
        if mode=='real' and (member['data_mode']!='real' or item.get('source') not in ('menu_photo','field_observation','official_menu')):
            rejected['商品事实依据不足']+=1;continue
        if mode=='demo' and item.get('source')!='simulated':continue
        if poi['id'] in c.get('exclude_poi_ids',[]):continue
        if member.get('outlet_id') in c.get('exclude_outlet_ids',[]):continue
        if any(r.get('status') in ('historical','archived','closed') for r in (poi,shop)) or poi.get('business_status') in ('暂停营业','可能已关闭','已关闭'):
            rejected['历史或停业']+=1;continue
        if poi.get('scope_status') in ('pending','outside') or poi.get('access_scope')=='staff':rejected['范围或准入待核']+=1;continue
        if item.get('status') in ('historical','archived','closed'):rejected['历史或停业']+=1;continue
        if item.get('item_type','dish')!='dish':rejected['加料或非完整餐品']+=1;continue
        if member.get('meal_role') in ('drink','dessert','snack','beverage','non_meal','weighed','weight_based','side'):
            rejected['饮品甜点或称重餐非定价正餐']+=1;continue
        # A meal recommendation must not substitute a cheap coffee/dessert for lunch.
        # This is a candidate policy, not a change to the source catalogue.
        if re.search(cfg['non_meal_item_pattern'],item.get('name','')) or re.search(cfg['drink_shop_pattern'],display_shop):
            rejected['饮品甜点非正餐']+=1;continue
        price=item.get('price')
        if isinstance(price,bool) or not isinstance(price,(int,float)) or not math.isfinite(price) or price<0 or price>c['budget']:rejected['价格未知或超预算']+=1;continue
        if item.get('available') is False:rejected['已停售']+=1;continue
        tags=set(item.get('tags',[])); title=item.get('name','')
        if any(t in tags or t in title or (t=='米饭' and '饭' in title) for t in c.get('avoid',[])):rejected['不符合忌口']+=1;continue
        dietary=c.get('dietary_requirements',[])
        if dietary and (not item.get('dietary_verified') or not set(dietary).issubset(item.get('dietary_certifications',[]))):rejected['饮食安全依据不足']+=1;continue
        unknown=[]; parts={'budget':max(0,1-price/max(c['budget'],1))}; reasons=[f'记录价格 ¥{price:g}，不超过预算 ¥{c["budget"]:g}']
        if item.get('available') is not True:unknown.append('当前在售待确认')
        if poi.get('access_scope')=='unknown':unknown.append('准入条件待确认')
        for field in ('taste','likes'):
            wanted=c.get(field,[])
            if wanted:
                if tags:
                    matches=tags.intersection(wanted);parts['taste' if field=='taste' else 'preference']=len(matches)/len(wanted)
                    if matches:reasons.append('已记录标签：'+'、'.join(sorted(matches)))
                    else:unknown.append('未匹配'+('口味' if field=='taste' else '偏好'))
                else:
                    parts['taste' if field=='taste' else 'preference']=0
                    unknown.append('口味标签待补')
        if c.get('avoid') and not tags:unknown.append('菜品配料与忌口需向窗口确认')
        loc=position(poi); walk=None; back=0;walking_source=None
        if origin and position(origin) and loc:
            start=position(origin)
            walk=math.ceil(math.hypot(start['x']-loc['x'],start['y']-loc['y'])*cfg['detour_factor']/cfg['walk_metres_per_minute'])
            walking_source='distance_estimate'
            for t in catalog.get('walking_times',[]):
                if t.get('from')==origin['id'] and t.get('to')==poi['id']:walk=t['minutes'];walking_source=t.get('source','manual_table');break
            parts['distance']=1/(1+walk/10)
            if destination:
                dest=position(destination);back=math.ceil(math.hypot(dest['x']-loc['x'],dest['y']-loc['y'])*cfg['detour_factor']/cfg['walk_metres_per_minute'])
        elif available is not None:unknown.append('步行时间未知')
        queue=None
        if mode=='demo':
            queue=SimulatedCrowdAdapter().get(shop['id'],at.isoformat())['queue_minutes'];parts['queue']=max(0,1-queue/max(c.get('max_queue_minutes',10),1))
        else:unknown.append('实时排队未知')
        if queue is not None and queue>c.get('max_queue_minutes',180):rejected['排队超过上限']+=1;continue
        serving=item.get('serving_minutes')
        if serving is None:unknown.append('出餐时间未知')
        # New confirmed windows are separate businesses, even though original
        # Items retain the floor collection's shop_id. Never inherit its hours.
        window_hours=outlet_hours(outlet or shop)
        hours=window_hours['opening_hours'] if outlet else shop.get('opening_hours') or poi.get('opening_hours')
        when=at+timedelta(minutes=walk or 0)
        venue_hours=poi.get('opening_hours')
        if outlet and venue_hours and open_at(venue_hours,when) is False:
            rejected['所在楼层记录时段不营业']+=1;continue
        if hours:
            if open_at(hours,when) is False:rejected['记录时段不营业']+=1;continue
            if walk is None:unknown.append('到店时间未知，营业判断仅按当前时刻')
        else:unknown.append('窗口营业时间尚未录入' if outlet else '营业时间待确认')
        total=walk+queue+serving+cfg['meal_minutes']+back+cfg['buffer_minutes'] if None not in (walk,queue,serving) else None
        if available is not None and total is not None and total>available:rejected['时间不足']+=1;continue
        lower_bound=(walk or 0)+(queue or 0)+(serving or 0)+cfg['meal_minutes']+back+cfg['buffer_minutes']
        if available is not None and lower_bound>available:rejected['已知最低用时已超限']+=1;continue
        if hours and None not in (walk,queue,serving) and open_at(hours,when,queue+serving) is not True:rejected['取餐前停止营业']+=1;continue
        if available is not None and total is None:unknown.append('无法确认上课前完成用餐')
        weight=sum(cfg['weights'][k] for k in parts)
        score=sum(cfg['weights'][k]*v for k,v in parts.items())/weight
        card=dict(type='food',id=item['id'],poi_id=poi['id'],shop_id=shop['id'],name=item['name'],shop=display_shop,poi=poi['name'],floor=(outlet.get('floor') if outlet else None) or shop.get('floor') or poi.get('floor'),
            address=poi.get('address',''),price=price,specification=item.get('specification','规格未注明'),location=loc,building_id=poi.get('building_id'),
            reasons=reasons,unknown=list(dict.fromkeys(unknown)),source=item.get('price_source',item.get('source','unknown')),simulation=mode=='demo',
            total_minutes=total,walking_minutes=walk,walking_source=walking_source,feasibility='estimate' if total is not None else 'conditional',score=round(score,4),score_parts=parts,
            hours=window_hours['hours_label'] if outlet else shop.get('opening_hours_text') or poi.get('opening_hours_text') or '；'.join('–'.join(v) for v in hours or []) or '尚未录入',
            observed_at=(item.get('field_evidence',{}).get('price') or {}).get('observed_at') or item.get('observation_date') or item.get('observed_at'),generated_at=at.isoformat())
        card.update(group_id=member['group_id'],outlet_id=member.get('outlet_id'),identity_status=member.get('identity_status'))
        card.update(public_confirmations(poi))
        if outlet:
            card.update(outlet_name=display_shop,outlet_opening_hours=window_hours['opening_hours'],
                        outlet_hours_label=window_hours['hours_label'],hours_scope='outlet',
                        venue_opening_hours=venue_hours,name_status=outlet.get('name_status'),
                        signboard_name_verified=outlet.get('signboard_name_verified',False))
        if not member.get('outlet_id'):
            card['unknown'].append('窗口身份待核，当前按楼层供餐集合保守去重')
        card.update(category_info(poi))
        candidates.append(clean_card(card))
    candidates.sort(key=lambda x:(bool(x['unknown']),-x['score'],x['price'],x['id']))
    selected=[];seen=set()
    for card in candidates:
        # Unknown window membership remains conservatively grouped by source
        # collection; confirmed windows in one floor must not collapse to one.
        identity=('outlet',card['outlet_id']) if card.get('outlet_id') else ('collection',card['shop_id'])
        if identity in seen:continue
        seen.add(identity);selected.append(card)
        if len(selected)==3:break
    return dict(cards=selected,conditions=c,rejected=dict(rejected),clarification=None,
        notice='演示数据与耗时仅供流程体验。' if mode=='demo' else '以下是基于已记录资料的候选；待确认项不作为已满足条件。')
