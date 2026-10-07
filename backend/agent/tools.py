"""Whitelisted read-only tools. Public DTOs never include raw field evidence."""
from ..adapters import CatalogAdapter, SimulatedScheduleAdapter
from ..storage import ROOT, now, timestamp
from .candidates import recommend_candidates, merge_conditions, position
from .presentation import category_info, clean_card, public_source
from ..map_display import display_fields

def schema(name,description,properties,required=()):
    return dict(type='function',function=dict(name=name,description=description,parameters=dict(type='object',properties=properties,required=list(required),additionalProperties=False)))

TEXT={'type':'string'}
LIST={'type':'array','items':TEXT}
TOOLS=[
    schema('search_places','按店名、菜系、类别或地址关键词找店；同名不同分店分开返回。',{'query':TEXT},['query']),
    schema('get_place','查询场所开放信息；餐饮返回菜单，饮品店返回饮品，零售返回商品，公共设施不返回菜单。每页60条。先search_places获取真实ID。offset为起始位置，默认0。',{'poi_id':TEXT,'offset':{'type':'integer'}},['poi_id']),
    schema('recommend_food','按已知真实条件返回最多3个候选。只传本轮改变的条件；null表示清除字段。缺预算或时间任务缺位置时自动补问。',{
        'budget':{'type':['number','null']},'taste':LIST,'avoid':LIST,'likes':LIST,'dietary_requirements':LIST,
        'current_location':{'type':['string','null']},'available_minutes':{'type':['number','null']},'max_queue_minutes':{'type':['number','null']},
        'next_class':{'type':['object','null'],'properties':{'time':TEXT,'location':TEXT},'required':['time','location'],'additionalProperties':False},'exclude_poi_ids':LIST}),
    schema('get_schedule','查询虚构用户某天的模拟课表，不是真实学校课表。',{'date':TEXT},['date'])
]


class CampusTools:
    def __init__(self,catalog=None):
        self.catalog=catalog

    def snapshot(self):
        return self.catalog or CatalogAdapter(ROOT/'data/life',ROOT/'data/campus_info.sqlite3').snapshot()

    @staticmethod
    def place(p):
        return clean_card(dict(type='place',id=p['id'],poi_id=p['id'],name=p['name'],address=p.get('address',''),floor=p.get('floor'),category=p.get('category'),
            hours=p.get('opening_hours_text') or '；'.join('–'.join(v) for v in p.get('opening_hours') or []),hours_notes=p.get('hours_notes',''),
            location=position(p),building_id=p.get('building_id'),source=p.get('hours_source',p.get('source')),simulation=False,**display_fields(p),
            unknown=([] if p.get('opening_hours') or p.get('opening_hours_text') else ['开放时段待确认'])+(['位置资料尚未现场核实'] if p.get('status')=='unverified' else []), **category_info(p)))

    def directory(self):
        c=self.snapshot()
        return dict(pois=[self.place(p) for p in c['pois'] if p.get('source')!='simulated' and p.get('status') not in ('historical','archived','closed')],
            locations=[dict(id=p['id'],name=p['name']) for p in c['locations']])

    def execute(self,name,args,conditions,mode='real',at=None):
        definition=next((x['function'] for x in TOOLS if x['function']['name']==name),None)
        if not definition or not isinstance(args,dict):raise ValueError('未知工具或参数')
        if set(args)-set(definition['parameters']['properties']):raise ValueError('工具包含未知参数')
        for k in definition['parameters']['required']:
            if not isinstance(args.get(k),str) or not args[k] or len(args[k])>200:raise ValueError('工具参数缺失或过长')
        c=self.snapshot()
        if name=='recommend_food':
            return recommend_candidates(c,merge_conditions(conditions,args),mode,at)
        if name=='search_places':
            q=args['query'].casefold().strip()
            if not q:raise ValueError('关键词不能为空')
            aliases={'新乐群':['canteen-1','canteen-2','canteen-3','canteen-4'],'学五':['canteen-5'],'学三':['canteen-3'],'学四':['canteen-4']}
            shop_matches={s['poi_id'] for s in c['shops'] if s.get('source')!='simulated' and q in s.get('name','').casefold()}
            rows=[p for p in c['pois'] if p.get('source')!='simulated' and p.get('status') not in ('historical','closed','archived') and
                (q in (p.get('name','')+' '+p.get('address','')+' '+p.get('category','')+' '+' '.join(p.get('aliases',[]))).casefold() or p['id'] in aliases.get(q,[]) or p['id'] in shop_matches)]
            return dict(cards=[self.place(p) for p in rows[:8]],total=len(rows),notice='同名对象可能是分店或待核重复，请按地址和楼层区分。')
        if name=='get_place':
            p=next((p for p in c['pois'] if p['id']==args['poi_id'] and p.get('source')!='simulated' and p.get('status') not in ('historical','closed','archived')),None)
            if not p:raise ValueError('地点不存在')
            ids={s['id'] for s in c['shops'] if s['poi_id']==p['id'] and s.get('source')!='simulated'}
            items=[i for i in c['items'] if i['shop_id'] in ids and i.get('source')!='simulated']
            offset=args.get('offset',0)
            if isinstance(offset,bool) or not isinstance(offset,int) or not 0<=offset<=10000:raise ValueError('分页位置无效')
            card=self.place(p)
            if card['capabilities']['items']:
                card['menu']=[dict(name=i['name'],price=i.get('price'),specification=i.get('specification'),source=public_source(i.get('price_source',i.get('source')))) for i in items[offset:offset+60]]
                card['menu_total']=len(items)
                card['menu_offset']=offset
            notice = (card['collection_label']+'为记录资料，当前在售情况需向店铺确认。') if card['collection_label'] else '开放与服务信息以现场公告为准。'
            return dict(cards=[card],notice=notice)
        if name=='get_schedule':
            date=args['date']
            timestamp(date+'T00:00:00+08:00')
            rows=SimulatedScheduleAdapter().get('demo-student-1',date)
            return dict(cards=[dict(type='schedule',id=r['id'],name=r['name'],start=r['start'],end=r['end'],location_name=r['location'],simulation=True) for r in rows],notice='虚构用户的模拟课表，不是你的真实课程安排。')

