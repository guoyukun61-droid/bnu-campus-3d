"""Whitelisted read-only tools. Public DTOs never include raw field evidence."""
import copy
from ..adapters import CatalogAdapter, SimulatedScheduleAdapter
from ..storage import ROOT, now, timestamp, read
from .candidates import recommend_candidates, merge_conditions, position, outlet_hours
from .presentation import category_info, clean_card, public_source
from ..map_display import display_fields
from ..menu_relations import build_menu_relations, record_data_mode
from ..confirmed_relations import public_confirmations


def readable(*records):
    return record_data_mode(*records)=='real' and all(r.get('status') not in ('historical','archived','closed') for r in records)


def alias_text(p):
    aliases=p.get('aliases')
    return ' '.join(x for x in aliases if isinstance(x,str)) if isinstance(aliases,list) else ''


def canonical_place(pois,requested_id):
    """Follow only explicitly recorded aliases; archived records stay archived."""
    index={p['id']:p for p in pois};seen=set();ident=requested_id
    while ident not in seen:
        seen.add(ident);record=index.get(ident)
        if not record:break
        target=record.get('canonical_poi_id')
        if target:
            if not isinstance(target,str):break
            ident=target;continue
        if readable(record):return record
        break
    raise ValueError('地点不存在或别名关系待核')


def public_outlet(outlet):
    """Only display metadata; photo paths and confirmation audits stay private."""
    return dict(**{k:outlet.get(k) for k in ('id','name','poi_id','floor','identity_status',
                'name_status','signboard_name_verified')},**outlet_hours(outlet))


def menu_outlet_fields(member,outlets,shops):
    ident=member.get('outlet_id');outlet=outlets.get(ident) or shops.get(ident)
    if not outlet:
        return dict(outlet_name=None,outlet_opening_hours=None,outlet_hours_label='尚未录入')
    hours=outlet_hours(outlet)
    return dict(outlet_name=outlet.get('name'),outlet_opening_hours=hours['opening_hours'],
                outlet_hours_label=hours['hours_label'])

def schema(name,description,properties,required=()):
    return dict(type='function',function=dict(name=name,description=description,parameters=dict(type='object',properties=properties,required=list(required),additionalProperties=False)))

TEXT={'type':'string'}
LIST={'type':'array','items':TEXT}
NETWORK_NOTICE='关联链条是资料依据，不是导航；同类、同品牌或功能互补不表示可替代，也不保证预算、饮食、营业或预约条件。未知信息须再查询或现场确认。'


def network_context():
    """Capture public geometry metadata and its seed once, without account IO."""
    from ..campus_content import SEED_PATH, enrich_buildings, area_descriptions
    document=read(SEED_PATH)
    buildings=read(ROOT/'assets/campus_assets_white_v6.json')['buildings']
    return enrich_buildings(buildings,document),area_descriptions(document)


def network_arguments(args):
    kind=args.get('kind','poi');mode=args.get('mode','neighbors');limit=args.get('limit',6)
    if not isinstance(kind,str) or kind not in {'poi','building','outlet'}:
        raise ValueError('关系对象类型无效')
    if not isinstance(mode,str) or mode not in {'neighbors','same_type','complementary','chain'}:
        raise ValueError('关系查询模式无效')
    if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=12:
        raise ValueError('关系查询数量须为1至12')
    ident=args['entity_id']
    if not ident.strip() or any(ord(c)<32 for c in ident):
        raise ValueError('关系对象ID无效')
    return kind,ident,mode,limit


def bounded_network(result,limit):
    """Retain the query module's safe DTO, never the source graph or catalogue.

    Public query paths contain at most 12 containment hops (3 for chain mode).
    Reject unexpected unbounded paths rather than silently truncating evidence.
    """
    allowed={'contract_version','snapshot_id','rule_version','configured','mode','anchor',
             'items','total','loaded_count','truncated','limitations','gaps','max_hops',
             'related_entity_count','related_entity_kinds'}
    dto={k:copy.deepcopy(v) for k,v in result.items() if k in allowed}
    rows=dto.get('items',[])
    if not isinstance(rows,list):raise ValueError('关系查询结果无效')
    dto['items']=rows[:limit]
    dto['loaded_count']=len(dto['items'])
    dto['truncated']=bool(dto.get('truncated') or len(rows)>limit)
    for item in dto['items']:
        paths=[item.get('path')]
        spatial=item.get('spatial_evidence')
        if isinstance(spatial,dict):paths.append(spatial.get('path'))
        for index,path in enumerate(paths):
            if path is None:continue
            bound=3 if index==0 and dto.get('mode')=='chain' else 12
            if (not isinstance(path,dict) or path.get('is_route') is not False
                    or not isinstance(path.get('edges'),list) or len(path['edges'])>bound
                    or not isinstance(path.get('nodes'),list) or len(path['nodes'])!=len(path['edges'])+1
                    or path.get('hop_count')!=len(path['edges'])):
                raise ValueError('关系证据路径无效或过长')
    return dto


def network_notice(related):
    labels={'contained_in':'所在场所','in_building':'同楼依据','on_floor':'楼层依据',
            'same_building_member':'同栋建筑','has_category':'所属类别','provides_service':'提供服务',
            'of_brand':'品牌归属','has_trait':'菜单特征','offers_trait':'曾有该标签的菜品','service_complements':'功能组合推测',
            'adjacent_to':'相邻依据','west_of':'位于西侧','east_of':'位于东侧',
            'located_in_part':'楼内方位','nearby_estimate':'记录点直线邻近',
            'within_radius':'记录点范围','member_of':'名录分组','ordered_along':'名录顺序'}
    summaries=[]
    for item in related.get('items',[])[:3]:
        types=list(dict.fromkeys(labels.get(e.get('type'),'关系依据')
                                 for e in item.get('path',{}).get('edges',[])))
        summaries.append(item['name']+'（'+'、'.join(types[:3])+'）')
    head='本次关联对象：'+'；'.join(summaries)+'。' if summaries else '当前快照没有返回该模式的关联对象，不代表现实中不存在。'
    if related.get('truncated'):head+='仅展示有限结果。'
    return head+NETWORK_NOTICE


TOOLS=[
    schema('search_places','按店名、菜系、类别或地址关键词找店；同名不同分店分开返回。',{'query':TEXT},['query']),
    schema('get_entity','读取已查到或当前选中的建筑/独立窗口资料。建筑有简介与资料状态；窗口只返回本窗口菜单，不混合整层。kind=poi时沿用地点详情。',{
        'kind':{'type':'string','enum':['poi','building','outlet']},'entity_id':TEXT,
        'offset':{'type':'integer','minimum':0}},['kind','entity_id']),
    schema('get_place','查询场所开放信息；餐饮返回菜单，饮品店返回饮品，零售返回商品，公共设施不返回菜单。每页60条。先search_places获取真实ID。offset为起始位置，默认0。',{'poi_id':TEXT,'offset':{'type':'integer'}},['poi_id']),
    schema('recommend_food','按已知真实条件返回最多3个候选。只传本轮改变的条件；null表示清除字段。缺预算或时间任务缺位置时自动补问。',{
        'within':{'type':'object','properties':{'kind':{'type':'string','enum':['poi','building']},'id':TEXT},'required':['kind','id'],'additionalProperties':False},
        'budget':{'type':['number','null']},'taste':LIST,'avoid':LIST,'likes':LIST,'dietary_requirements':LIST,
        'current_location':{'type':['string','null']},'available_minutes':{'type':['number','null']},'max_queue_minutes':{'type':['number','null']},
        'next_class':{'type':['object','null'],'properties':{'time':TEXT,'location':TEXT},'required':['time','location'],'additionalProperties':False},'exclude_poi_ids':LIST,'exclude_outlet_ids':LIST}),
    schema('get_schedule','查询虚构用户某天的模拟课表，不是真实学校课表。',{'date':TEXT},['date']),
    schema('get_related_places','以已查询到的真实ID探索相关地点：neighbors为直接关系，same_type为同类比较，complementary为有空间依据的功能组合，chain为最多3跳解释链。仅真实可浏览记录；这是证据查询，不是导航或条件推荐。',{
        'kind':{'type':'string','enum':['poi','building','outlet']},'entity_id':TEXT,
        'mode':{'type':'string','enum':['neighbors','same_type','complementary','chain']},
        'limit':{'type':'integer','minimum':1,'maximum':12}},['entity_id'])
]


class CampusTools:
    def __init__(self,catalog=None,*,buildings=None,areas=None):
        self.catalog=catalog
        self._buildings=copy.deepcopy(buildings)
        self._areas=copy.deepcopy(areas)
        self._relation_snapshot=None

    def snapshot(self):
        return self.catalog or CatalogAdapter(ROOT/'data/life',ROOT/'data/campus_info.sqlite3').snapshot()

    def frozen(self):
        """One agent turn sees one catalogue even when a new review is published."""
        catalog=copy.deepcopy(self.snapshot())
        if self._buildings is None or self._areas is None:
            buildings,areas=network_context()
        else:buildings,areas=self._buildings,self._areas
        return CampusTools(catalog,buildings=buildings,areas=areas)

    def relation_snapshot(self,catalog):
        if self._relation_snapshot is None:
            # Lazy import: life_relations already imports agent.presentation.
            from ..life_relations import build_relation_snapshot
            if self._buildings is None or self._areas is None:
                buildings,areas=network_context()
                self._buildings,self._areas=copy.deepcopy(buildings),copy.deepcopy(areas)
            self._relation_snapshot=build_relation_snapshot(copy.deepcopy(catalog),self._buildings,self._areas)
        return self._relation_snapshot

    @staticmethod
    def place(p):
        return clean_card(dict(type='place',id=p['id'],poi_id=p['id'],name=p['name'],address=p.get('address',''),floor=p.get('floor'),category=p.get('category'),
            hours=p.get('opening_hours_text') or '；'.join('–'.join(v) for v in p.get('opening_hours') or []) or '尚未录入',hours_notes=p.get('hours_notes',''),
            location=position(p),building_id=p.get('building_id'),source=p.get('hours_source',p.get('source')),
            simulation=record_data_mode(p)=='simulated',data_mode=record_data_mode(p),**display_fields(p),**public_confirmations(p),
            unknown=([] if p.get('opening_hours') or p.get('opening_hours_text') else ['开放时段待确认'])+(['位置资料尚未现场核实'] if p.get('status')=='unverified' else []), **category_info(p)))

    def directory(self):
        c=self.snapshot()
        return dict(pois=[self.place(p) for p in c['pois'] if readable(p)],
            locations=[dict(id=p['id'],name=p['name']) for p in c['locations']])

    def entity(self,kind,ident,mode='real'):
        """Re-resolve typed IDs against the frozen public projection, not client text."""
        from .context import resolve_context
        from .evidence import text
        resolved=resolve_context(self,{'selected':{'kind':kind,'id':ident}},[],mode)
        selected=resolved['selected']
        if not selected:raise ValueError('对象不存在或当前不可浏览')
        c=self.snapshot()
        row=next((e for e in self.relation_snapshot(c)['entities'] if e['ref']=={'kind':selected['kind'],'id':selected['id']}),None)
        if row is None:raise ValueError('对象详情尚未录入')
        result=dict(selected,ref={'kind':selected['kind'],'id':selected['id']},source=public_source(row.get('source')))
        for field in ('description','description_status','content_origin','identity_status','name_status'):
            if text(row.get(field),600):result[field]=text(row[field],600)
        result['limitations']=[text(v) for v in row.get('content_limitations',[]) if text(v)]
        # Only explicit public URLs; no arbitrary source fields or local filenames.
        from urllib.parse import urlsplit
        links=[]
        for source in row.get('source_links',[])[:8]:
            url=source.get('url') if isinstance(source,dict) else source
            if isinstance(url,str) and text(url,600)==url:
                try:
                    parsed=urlsplit(url)
                    if parsed.scheme in ('http','https') and parsed.hostname and not parsed.username and not parsed.password:
                        links.append(url)
                except ValueError:pass
        result['source_urls']=links
        if kind=='outlet':
            outlet=next((o for o in build_menu_relations(c)['outlets'] if o['id']==selected['id']),None)
            shop=next((s for s in c['shops'] if s['id']==selected['id']),None)
            result.update(outlet_hours(outlet or shop or {}))
        return result

    def execute(self,name,args,conditions,mode='real',at=None):
        definition=next((x['function'] for x in TOOLS if x['function']['name']==name),None)
        if not definition or not isinstance(args,dict):raise ValueError('未知工具或参数')
        if set(args)-set(definition['parameters']['properties']):raise ValueError('工具包含未知参数')
        for k in definition['parameters']['required']:
            if not isinstance(args.get(k),str) or not args[k] or len(args[k])>200:raise ValueError('工具参数缺失或过长')
        if name=='get_related_places':network_args=network_arguments(args)
        c=self.snapshot()
        if name=='get_entity':
            kind=args['kind'];ident=args['entity_id']
            if kind not in {'poi','building','outlet'}:raise ValueError('对象类型无效')
            if kind=='poi':return self.execute('get_place',{'poi_id':ident,'offset':args.get('offset',0)},conditions,mode,at)
            entity=self.entity(kind,ident,mode)
            if kind=='building':
                return dict(cards=[],entities=[entity],notice='建筑介绍的事实、推测与待补状态分别标注；选中建筑不代表你当前在这里。')
            offset=args.get('offset',0)
            if isinstance(offset,bool) or not isinstance(offset,int) or not 0<=offset<=10000:raise ValueError('分页位置无效')
            # Collect only this outlet across source pages, then paginate the outlet itself.
            poi_id=entity.get('poi_id');items=[];card=None
            for page in range(0,len(c.get('items',[]))+1,60):
                part=self.execute('get_place',{'poi_id':poi_id,'offset':page},conditions,mode,at)['cards'][0]
                if card is None:card=part
                items.extend(i for i in part.get('menu',[]) if i.get('outlet_id')==entity['id'])
                if page+60>=part.get('menu_total',0):break
            card.update(id=entity['id'],name=entity['name'],menu=items[offset:offset+60],menu_total=len(items),menu_offset=offset,
                        outlet_id=entity['id'],outlet_name=entity['name'],hours=entity.get('hours_label','尚未录入'),
                        outlets=[o for o in card.get('outlets',[]) if o['id']==entity['id']],
                        menu_groups=[g for g in card.get('menu_groups',[]) if g.get('outlet_id')==entity['id']])
            if entity.get('hours_label')=='尚未录入':card['unknown']=list(dict.fromkeys(card.get('unknown',[])+['窗口营业时间尚未录入']))
            return dict(cards=[card],entities=[entity],notice='只展示该窗口记录菜单；窗口时段不继承整层，当前在售需确认。')
        if name=='get_related_places':
            from ..poi_network_query import query_network
            kind,ident,query_mode,limit=network_args
            related=bounded_network(query_network(self.relation_snapshot(c),kind=kind,ident=ident,
                                                  mode=query_mode,limit=limit),limit)
            indices={p['id']:p for p in c['pois'] if readable(p)}
            cards=[self.place(indices[row['ref']['id']]) for row in related['items']
                   if row['ref']['kind']=='poi' and row['ref']['id'] in indices]
            return dict(cards=cards,related_places=related,notice=network_notice(related))
        if name=='recommend_food':
            patch=dict(args);within=patch.pop('within',None);eligible=None;scope=None
            if within is not None:
                from .context import resolve_entity
                if not isinstance(within,dict) or within.get('kind') not in {'poi','building'}:raise ValueError('推荐范围无效')
                scope=resolve_entity(self,within,mode)
                if not scope:raise ValueError('推荐范围不存在')
                eligible=({scope['id']} if scope['kind']=='poi' else
                          {p['id'] for p in c['pois'] if str(p.get('building_id'))==scope['id']})
            result=recommend_candidates(c,merge_conditions(conditions,patch),mode,at,eligible_poi_ids=eligible)
            if scope:
                result['scope']=scope
                result['notice']=(result.get('notice','')+' 本次仅在'+scope['name']+'范围内比较，不自动扩大到其他场所。').strip()
            return result
        if name=='search_places':
            q=args['query'].casefold().strip()
            if not q:raise ValueError('关键词不能为空')
            aliases={'新乐群':['canteen-1','canteen-2','canteen-3','canteen-4'],'学五':['canteen-5'],'学三':['canteen-3'],'学四':['canteen-4'],
                     '新三':['canteen-3'],'新四':['canteen-4'],'新乐群三层':['canteen-3'],'新乐群四层':['canteen-4']}
            poi_index={p['id']:p for p in c['pois']}
            shop_index={s['id']:s for s in c['shops'] if s.get('poi_id') in poi_index and readable(s,poi_index[s['poi_id']])}
            shop_matches={s['poi_id'] for s in shop_index.values() if q in s.get('name','').casefold()}
            for alias in c['pois']:
                if alias.get('canonical_poi_id') and q in ' '.join([alias.get('name') or '',alias_text(alias)]).casefold():
                    try:shop_matches.add(canonical_place(c['pois'],alias['id'])['id'])
                    except ValueError:pass
            menu_data=build_menu_relations(c)
            item_names={i['id']:i['name'] for i in c['items'] if i.get('shop_id') in shop_index and readable(i)}
            matching_groups=[g for g in menu_data['menu_groups'] if g['data_mode']=='real' and set(g['item_ids']).intersection(item_names) and
                             (q in g['name'].casefold() or any(q in item_names[i].casefold() for i in g['item_ids'] if i in item_names))]
            shop_matches.update(g['poi_id'] for g in matching_groups)
            rows=[p for p in c['pois'] if readable(p) and
                (q in ' '.join([p.get('name') or '',p.get('address') or '',p.get('category') or '',alias_text(p)]).casefold() or p['id'] in aliases.get(q,[]) or p['id'] in shop_matches)]
            cards=[self.place(p) for p in rows[:8]]
            for card in cards:
                card['matched_menu_groups']=[{k:g[k] for k in ('id','name','identity_status','outlet_id')}
                                             for g in matching_groups if g['poi_id']==card['id']]
            entities=[]
            for row in self.relation_snapshot(c)['entities']:
                if row['ref']['kind'] not in {'building','outlet'}:continue
                if q not in ' '.join([row.get('name','')]+row.get('aliases',[])).casefold():continue
                try:entities.append(self.entity(row['ref']['kind'],row['ref']['id'],mode))
                except ValueError:continue
                if len(entities)>=8:break
            return dict(cards=cards,entities=entities,total=len(rows),entities_truncated=len(entities)>=8,notice='同名分店按地址和楼层区分；独立窗口与待核菜单组分别标注，营业及当前在售仍需确认。')
        if name=='get_place':
            p=canonical_place(c['pois'],args['poi_id'])
            ids={s['id'] for s in c['shops'] if s['poi_id']==p['id'] and readable(s,p)}
            items=[i for i in c['items'] if i['shop_id'] in ids and readable(i)]
            offset=args.get('offset',0)
            if isinstance(offset,bool) or not isinstance(offset,int) or not 0<=offset<=10000:raise ValueError('分页位置无效')
            card=self.place(p)
            if p['id']!=args['poi_id']:
                card.update(requested_poi_id=args['poi_id'],canonical_poi_id=p['id'],
                            alias_notice='该旧记录已确认与当前地点相同，现展示合并后的有效记录。')
            info=p.get('service_info')
            if isinstance(info,dict):
                card['service_info']={k:info.get(k) for k in ('summary','source_url','published_at','retrieved_at')}
            if card['capabilities']['items']:
                menu_data=build_menu_relations(c);membership=menu_data['item_membership']
                outlets={o['id']:o for o in menu_data.get('outlets',[])};shops={s['id']:s for s in c['shops']}
                card['menu']=[dict(id=i['id'],shop_id=i['shop_id'],group_id=membership[i['id']]['group_id'],
                    outlet_id=membership[i['id']].get('outlet_id'),data_mode=membership[i['id']]['data_mode'],
                    identity_status=membership[i['id']]['identity_status'],meal_role=membership[i['id']]['meal_role'],
                    **menu_outlet_fields(membership[i['id']],outlets,shops),
                    name=i['name'],price=i.get('price'),specification=i.get('specification'),source=public_source(i.get('price_source',i.get('source')))) for i in items[offset:offset+60]]
                item_ids={i['id'] for i in items}
                card['menu_groups']=[dict(id=g['id'],name=g['name'],floor=g.get('floor'),outlet_id=g.get('outlet_id'),
                    **menu_outlet_fields(g,outlets,shops),
                    identity_status=g['identity_status'],data_mode=g['data_mode'],source=g['source'],item_count=len(item_ids.intersection(g['item_ids'])))
                    for g in menu_data['menu_groups'] if g['poi_id']==p['id'] and item_ids.intersection(g['item_ids'])]
                visible_outlets={g['outlet_id'] for g in card['menu_groups'] if g.get('outlet_id')}
                card['outlets']=[public_outlet(o) for ident,o in outlets.items() if ident in visible_outlets]
                card['menu_total']=len(items)
                card['menu_offset']=offset
            notice = (card['collection_label']+'为记录资料，当前在售情况需向店铺确认。') if card['collection_label'] else '开放与服务信息以现场公告为准。'
            return dict(cards=[card],notice=notice)
        if name=='get_schedule':
            date=args['date']
            timestamp(date+'T00:00:00+08:00')
            rows=SimulatedScheduleAdapter().get('demo-student-1',date)
            return dict(cards=[dict(type='schedule',id=r['id'],name=r['name'],start=r['start'],end=r['end'],location_name=r['location'],simulation=True) for r in rows],notice='虚构用户的模拟课表，不是你的真实课程安排。')

