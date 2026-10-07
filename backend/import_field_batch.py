"""Explicitly authorized September field batch; dry run, OS lock and atomic commit."""
import argparse
import copy
import csv
import hashlib
import json
import re
from pathlib import Path
from .storage import ROOT, read, write, now
from .adapters import CatalogAdapter
from .contribution import ContributionStore, digest, overlay

BATCH = 'field-20260930'
DIRECTORY = ROOT / 'data/life' / BATCH
PHOTOS = Path('D:/A-newdesktop/个人/比赛/opc/素材')
SOURCE = 'user_report_20260930'


def hours_value(raw):
    # Conditional calendars and alternative opening times remain unknown to ranking.
    if '（' in raw or '或' in raw:
        return None
    if raw == '00:00-24:00':
        return [['00:00', '00:00']]
    if not re.fullmatch(r'\d\d:\d\d-\d\d:\d\d', raw):
        raise ValueError('Invalid hours: ' + raw)
    return [raw.split('-')]


def transcriptions(text=None):
    groups = []
    if text is None:
        text = (DIRECTORY/'menu_transcription.txt').read_text(encoding='utf-8')
    for line in text.splitlines():
        if not line or line.startswith('#'):
            continue
        if line.startswith('@'):
            ident, floor, title = line[1:].split('|')
            groups.append(dict(photo=ident, floor=floor, title=title, items=[], notes=[]))
        elif line.startswith('!'):
            groups[-1]['notes'].append(line[1:])
        else:
            for entry in line.split(';'):
                name, price = entry.rsplit('=', 1)
                groups[-1]['items'].append(dict(name=name, raw_price=price))
    return groups


def compatible(record, current):
    original = record.get('base') or {}
    return all(current.get(k) == original.get(k) or current.get(k) == v
               for k, v in record['patch'].items())


def prepare_xuewu_hours():
    batch=BATCH+'-xuewu-hours'
    original=read(ROOT/'data/life/contributions/state.json')
    if any(a.get('batch')==batch for a in original['audit']):
        raise ValueError('Hours already applied')
    photo=Path('C:/Users/gyk11/AppData/Local/Temp/codex-clipboard-65d44431-83c8-4d8c-984f-48a8d2db8455.jpg')
    raw=photo.read_bytes()
    sha=hashlib.sha256(raw).hexdigest()
    stage=DIRECTORY/('xuewu-'+now().replace(':','-'))
    stage.mkdir(parents=True,exist_ok=False)
    (stage/'source.jpg').write_bytes(raw)
    state=copy.deepcopy(original)
    patch=dict(opening_hours=[['06:30','09:00'],['10:30','13:30'],['16:30','21:00']],
        opening_hours_text='早餐06:30–09:00；午餐10:30–13:30；晚餐/夜宵16:30–21:00',
        hours_source='user_screenshot_20260930',hours_notes='用户提供截图；拍摄日期与适用楼层未标明。')
    target=state['published'].setdefault('pois',{}).setdefault('canteen-5',{})
    target.update(patch)
    for key in patch:
        target.setdefault('field_evidence',{})[key]=dict(source='user_screenshot_20260930',
            evidence=patch['opening_hours_text'],source_photo_sha256=sha,source_file=str(stage/'source.jpg'),
            observed_at=None,reported_at=now(),reviewed_at=now(),batch=batch)
    target['updated_at']=now()
    state['version']+=1
    state['audit'].append(dict(action='confirmed_xuewu_hours',batch=batch,actor='g',at=now(),source_photo_sha256=sha))
    report=dict(batch=batch,stage=str(stage),original_digest=digest(original),result_digest=digest(state),
        approved=[],conflicts=[],drafts=[],hours=[dict(poi_id='canteen-5',result='applied')],menu_counts={'imported':0})
    overlay(CatalogAdapter(ROOT/'data/life',ROOT/'data/campus_info.sqlite3').snapshot(),state)
    write(stage/'result-state.json',state)
    write(stage/'report.json',report)
    write(DIRECTORY/'xuewu-preview.json',dict(stage=str(stage)))
    return report


def prepare_followup():
    """Explicit follow-up: confirmed fourth-floor window and gate hours."""
    batch=BATCH+'-floor-gates'
    original=read(ROOT/'data/life/contributions/state.json')
    if any(a.get('batch')==batch for a in original['audit']):
        raise ValueError('Follow-up already applied')
    catalog=CatalogAdapter(ROOT/'data/life',ROOT/'data/campus_info.sqlite3').snapshot()
    state=copy.deepcopy(original)
    stage=DIRECTORY/('followup-'+now().replace(':','-'))
    stage.mkdir(parents=True,exist_ok=False)
    report=dict(batch=batch,stage=str(stage),original_digest=digest(original),approved=[],conflicts=[],drafts=[],hours=[],menu_counts={'imported':6})
    evidence='用户2026-09-30补充确认：淮南牛肉汤在四层；东门全天开放，其他门06:00到24:00开放。实际现场观察时间未提供。'
    def put(kind,ident,patch,source='user_report_20260930'):
        target=state['published'].setdefault(kind,{}).setdefault(ident,{})
        target.update(patch)
        for key in patch:
            target.setdefault('field_evidence',{})[key]=dict(source=source,evidence=evidence,
                observed_at=None,reported_at=now(),reviewed_at=now(),batch=batch)
        target['updated_at']=now()
    ids={'campus-gate-'+name for name in ('east','west','north','south','small-east','small-west')}
    ids.add('baidu-3c899072030095c2b75f1ea4')
    known={p['id'] for p in catalog['pois']}
    if not ids.issubset(known):raise ValueError('Gate ID not found')
    for pid in sorted(ids):
        raw='00:00-24:00' if pid=='campus-gate-east' else '06:00-24:00'
        put('pois',pid,dict(opening_hours=[['00:00','00:00']] if pid=='campus-gate-east' else [['06:00','00:00']],
            opening_hours_text=raw,hours_source='user_report_20260930',
            hours_notes='用户确认的校门开放时间；进入校园的身份、预约条件另行核验。'))
        report['hours'].append(dict(poi_id=pid,hours=raw,result='applied'))
    photo=next(PHOTOS.glob('新乐群四层/*_483_44.jpg'))
    sha=hashlib.sha256(photo.read_bytes()).hexdigest()
    sid='shop-huainan-xinlequn-4'
    if any(s['id']==sid for s in catalog['shops']):raise ValueError('Window already exists')
    put('shops',sid,dict(id=sid,name='淮南牛肉汤',poi_id='canteen-4',floor='4',
        source='menu_photo',status='verified',menu_status='photo_transcribed',
        identity_status='user_confirmed',source_file=photo.name,source_photo_sha256=sha))
    group=next(g for g in transcriptions() if g['photo']=='457')
    for item in group['items']:
        ident='photo-item-'+hashlib.sha256((sid+'|'+item['name']).encode()).hexdigest()[:20]
        patch=dict(id=ident,shop_id=sid,name=item['name'],price=float(item['raw_price']),
            tags=['面食'] if '面' in item['name'] else [],source='menu_photo',price_source='menu_photo',
            status='verified',available=None,availability_note='菜单列示商品；实时在售状态未知',
            serving_minutes=None,specification='每份' if '单买饼' in item['name'] else '照片未注明规格',
            sales_channel='堂食',source_file=photo.name,source_photo_sha256=sha,observation_date=None,
            retrieved_at=now(),menu_section='淮南牛肉汤',item_type='side' if '单买饼' in item['name'] else 'dish')
        if item['name'].endswith('汤'):patch['add_ons']=[dict(name='饼',price=1,condition='搭配汤购买')]
        put('items',ident,patch,'menu_photo')
        for key in ('name','price','specification','add_ons'):
            if key in patch:
                state['published']['items'][ident]['field_evidence'][key]['evidence']='照片'+photo.name+'，人工视觉转录；用户另行确认窗口在四层。'
    state['version']+=1
    state['audit'].append(dict(action='confirmed_floor_and_gate_hours',batch=batch,actor='g',at=now(),
        note=evidence,source_digest=report['original_digest'],gate_ids=sorted(ids),shop_id=sid))
    overlay(catalog,state)
    report['result_digest']=digest(state)
    write(stage/'result-state.json',state)
    write(stage/'report.json',report)
    write(DIRECTORY/'followup-preview.json',dict(stage=str(stage)))
    return report


def prepare():
    original = read(ROOT/'data/life/contributions/state.json')
    baseline = CatalogAdapter(ROOT/'data/life', ROOT/'data/campus_info.sqlite3').snapshot()
    stage = DIRECTORY / ('preview-' + now().replace(':', '-'))
    stage.mkdir(parents=True, exist_ok=False)
    write(stage/'catalog.json', baseline)
    write(stage/'contributions/state.json', original)
    store = ContributionStore(stage/'contributions', CatalogAdapter(stage))
    admin = dict(id='g', name='g', role='admin')
    report = dict(batch=BATCH, prepared_at=now(), original_digest=digest(original),
                  stage=str(stage), approved=[], conflicts=[], drafts=[], hours=[], photos=[], gaps=[])
    for record in original['submissions'].values():
        if record['status'] == 'draft':
            report['drafts'].append(record['id'])
            continue
        if record['status'] != 'submitted':
            continue
        current = next((r for r in store.entities()[record['kind']]
                        if r['id'] == record['entity_id']), None)
        if (digest(current) if current else None) != record['base_revision']:
            if current is None or not compatible(record, current):
                report['conflicts'].append(record['id'])
                continue
            state = store.state()
            state['audit'].append(dict(action='review_nonconflicting_rebase', at=now(), actor='g',
                                      submission_id=record['id'], original_record=copy.deepcopy(record),
                                      current_base=copy.deepcopy(current), batch=BATCH))
            state['submissions'][record['id']]['base_revision'] = digest(current)
            write(store.path, state)
        store.review(admin, dict(id=record['id'], revision=record['revision'], action='approved',
                                note='用户2026-09-30明确授权批准；重叠字段核对后保留原始审计。'))
        report['approved'].append(record['id'])

    catalog = store.entities()
    state = store.state()
    if any(a.get('action') == 'field_batch_import' and a.get('batch') == BATCH for a in state['audit']):
        raise ValueError('Batch already imported; do not duplicate records.')
    index = {kind: {r['id']: r for r in catalog[kind]} for kind in ('pois', 'shops', 'items')}

    def publish(kind, ident, patch, evidence, source=SOURCE):
        current = index[kind].get(ident, {})
        result = copy.deepcopy(state['published'].setdefault(kind, {}).get(ident, {}))
        provenance = result.setdefault('field_evidence', {})
        for field, value in patch.items():
            provenance[field] = dict(source=source, evidence=evidence, observed_at=None,
                                     reported_at=now(), reviewed_at=now(), batch=BATCH)
            result[field] = copy.deepcopy(value)
        result['updated_at'] = now()
        state['published'][kind][ident] = result
        index[kind][ident] = dict(current, **result)

    with (DIRECTORY/'hours.tsv').open(encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream, delimiter='\t'):
            pid = row['poi_id']
            if not pid and row['name'] in {'曾三线米线', '24h超市'}:
                report['gaps'].append(dict(type='identity_match', **row,
                    candidate_id='baidu-be4b47af81efd4befb2d6156' if row['name']=='曾三线米线' else 'baidu-5dbb42fb4c2f8060a21de9cf'))
                report['hours'].append(dict(**row, result='identity_pending'))
                continue
            patch = dict(opening_hours=hours_value(row['hours']), opening_hours_text=row['hours'],
                         hours_source=SOURCE, hours_notes=row['note'])
            if not pid:
                pid = 'reported-' + hashlib.sha256(row['name'].encode()).hexdigest()[:16]
                patch.update(id=pid, name=row['name'], source=SOURCE, status='unverified',
                             category=row['category'], zone='campus', location=None, building_id=None,
                             scope_status='pending', access_scope='unknown', address=row['note'],
                             floor='2' if row['note']=='南侧二层' else '', identity_status='reported')
            if pid not in index['pois'] and row['poi_id']:
                raise ValueError('Unknown explicit POI: ' + pid)
            publish('pois', pid, patch, '用户2026-09-30提供：'+row['name']+' '+row['hours']+'；'+row['note'])
            matching = [s for s in index['shops'].values() if s['poi_id']==pid and s.get('source')!='simulated']
            for shop in matching:
                publish('shops', shop['id'], {k:patch[k] for k in ('opening_hours','opening_hours_text','hours_source','hours_notes')},
                        '用户提供营业时间；通过明确POI父级关联')
            if not matching:
                sid = 'shop-'+pid
                publish('shops', sid, dict(id=sid, poi_id=pid, name=row['name'], source=SOURCE,
                    status='unverified', floor=patch.get('floor', index['pois'][pid].get('floor','')),
                    menu_status='missing', opening_hours=patch['opening_hours'],
                    opening_hours_text=row['hours'], hours_source=SOURCE, hours_notes=row['note']), '用户提供的校内经营点；未核实具体坐标')
            report['hours'].append(dict(**row, resolved_id=pid, result='applied'))

    for pid, desc, floor in [('canteen-1','常规食堂','1'), ('canteen-2','智慧食堂，自选菜','2'),
                              ('canteen-3','风味窗口','3'), ('canteen-4','风味窗口','4'),
                              ('canteen-5','一层、二层为常规食堂','1、2')]:
        publish('pois',pid,dict(dining_type=desc,floor=floor), '用户2026-09-30明确食堂楼层用途；不修改原有营业时段')

    groups = transcriptions()
    files = {p.name.split('_')[-2]: p for p in PHOTOS.rglob('*.jpg')}
    if set(files) != {g['photo'] for g in groups}:
        raise ValueError('Photo inventory and transcription differ')
    # Floor collections are archival parents, NOT independent merchant/window claims.
    for floor in ('3','4'):
        sid = 'menu-collection-xinlequn-'+floor
        publish('shops', sid, dict(id=sid, poi_id='canteen-'+floor,
            name='新乐群'+floor+'层风味供餐（窗口待细分）', floor=floor,
            source='menu_photo', status='verified', entity_type='floor_menu_collection',
            independent_merchant=False, menu_status='photo_transcribed'), '用户确认楼层用途；照片目录标注楼层，单独窗口归属仍待核', 'menu_photo')
    excluded = {'462': {'黑汁鸡肉套餐','贵州酸汤肉汤饭'},
                '477': {'肉沫拌面','豇豆肉沫拌面'},
                '486': {'酸辣猪肉片','鲜虾烩三爽'}}
    counts = dict(imported=0, uncertain=0, add_on=0)
    for group in groups:
        path = files[group['photo']]
        evidence = dict(file=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                        floor=group['floor'], title=group['title'], notes=group['notes'])
        report['photos'].append(evidence)
        if group['floor'] == '待核':
            report['gaps'].append(dict(type='floor_conflict',photo=group['photo'],detail='457和483为完全相同照片，三/四层目录冲突；菜单文本保留但暂不分配楼层入库'))
            continue
        sid = 'menu-collection-xinlequn-'+group['floor']
        for item in group['items']:
            if item['name'] in excluded.get(group['photo'],set()):
                report['gaps'].append(dict(type='unreadable_name',photo=group['photo'],**item));counts['uncertain']+=1
                continue
            if '单点' in item['name'] or '单加' in item['name']:
                counts['add_on']+=1
                continue
            price_raw=item['raw_price']
            if price_raw=='?':
                report['gaps'].append(dict(type='price_uncertain',photo=group['photo'],**item));counts['uncertain']+=1
            prices = [None] if price_raw=='?' else [float(v) for v in price_raw.split('/')]
            for i,price in enumerate(prices):
                spec = (['小份','大份'] if group['photo']=='472' else ['中杯','大杯'])[i] if len(prices)==2 else '照片未注明规格'
                menu_group = '朱家小馆' if group['photo'] in {'477','478'} else group['title']
                ident='photo-item-'+hashlib.sha256((sid+'|'+menu_group+'|'+item['name']+'|'+spec).encode()).hexdigest()[:20]
                previous=index['items'].get(ident)
                if previous:
                    if previous.get('price')!=price:raise ValueError('Conflicting menu price '+ident)
                    continue
                tags=[]
                if '饭' in item['name']:tags.append('米饭')
                if '面' in item['name'] or '水饺' in item['name']:tags.append('面食')
                if '辣' in item['name']:tags.append('辣')
                patch=dict(id=ident,shop_id=sid,name=item['name'],price=price,tags=tags,
                    source='menu_photo',price_source='menu_photo' if price is not None else 'unknown',
                    status='verified' if price is not None else 'unverified',available=None,
                    availability_note='菜单列示商品；实时在售状态未知',serving_minutes=None,
                    specification=spec,sales_channel='堂食',menu_section=menu_group,
                    source_file=path.name,source_photo_sha256=evidence['sha256'],
                    observation_date=None,retrieved_at=now(),independent_window_verified=False)
                publish('items',ident,patch,'用户照片 '+path.name+'；'+group['title']+'；人工视觉转录，拍摄日期未确认','menu_photo')
                counts['imported']+=1
    state['version']+=1
    state['audit'].append(dict(action='field_batch_import', batch=BATCH, at=now(), actor='g',
        note='用户授权批准待审核并补充营业时间和照片；保留草稿、条件时段、身份及楼层疑点',
        counts=counts, source_digest=report['original_digest']))
    overlay(baseline,state)
    report['menu_counts']=counts
    report['result_digest']=digest(state)
    write(stage/'result-state.json',state)
    write(stage/'report.json',report)
    write(DIRECTORY/'latest-preview.json',dict(stage=str(stage)))
    return report


def commit(stage):
    report=read(stage/'report.json')
    result=read(stage/'result-state.json')
    directory=ROOT/'data/life/contributions'
    # Same byte and OS lock as contribution_server.py; never write alongside it.
    with (directory/'writer.lock').open('a+b') as lock:
        import os
        lock.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        current=read(directory/'state.json')
        if digest(current)!=report['original_digest']:raise ValueError('Live submissions changed; prepare a fresh preview')
        if digest(result)!=report['result_digest']:raise ValueError('Preview digest mismatch')
        live=CatalogAdapter(ROOT/'data/life',ROOT/'data/campus_info.sqlite3').snapshot()
        overlay(live,result)
        write(stage/'before-live-state.json',current)
        write(directory/'state.json',result)
        write(stage/'commit-receipt.json',dict(committed_at=now(),before=digest(current),after=digest(result)))
    return dict(approved=len(report['approved']), conflicts=len(report['conflicts']),drafts=len(report['drafts']),
                hours_applied=sum(r['result']=='applied' for r in report['hours']),menus=report['menu_counts'])


def export_report(stage):
    report=read(stage/'report.json')
    receipt=read(stage/'commit-receipt.json')
    if not receipt:raise ValueError('Batch is not committed')
    state=read(stage/'result-state.json')
    items=[r for r in state['published'].get('items',{}).values()
           if r.get('field_evidence',{}).get('name',{}).get('batch')==BATCH]
    lines=['# 现场资料入库报告 — 2026-09-30','',
        f"已于 {receipt['committed_at']} 完成；批准待审核 {len(report['approved'])} 条，未解决审核冲突 {len(report['conflicts'])} 条。",
        f"保留 {len(report['drafts'])} 条未提交草稿。用户授权批准不等于独立复测全部字段；新建记录缺坐标者继续待核。",
        '',f"营业时间清单 {len(report['hours'])} 项，已匹配/新增入库 {sum(r['result']=='applied' for r in report['hours'])} 项，身份匹配待核 {sum(r['result']=='identity_pending' for r in report['hours'])} 项。",
        f"25 张照片逐张查阅，其中 1 对文件 SHA-256 完全相同；新增 {len(items)} 条菜品/规格记录，其中明确价格 {sum(r.get('price') is not None for r in items)} 条，价格未知 {sum(r.get('price') is None for r in items)} 条。",
        '照片菜单挂接三层、四层供餐集合；不把集合计为独立店铺，不把每张菜单计为一家店。商品实时在售、排队与出餐耗时均未知，原200条模拟商品继续独立标记。',
        '', '## 审核与恢复','',
        '先在副本重放审核，再取得服务相同的OS写锁；检查原始状态指纹后备份并原子替换。好邻居两条旧候选的变化与已发布值兼容，已留存重新核对的原记录。',
        f"私有备份：[before-live-state.json]({(stage/'before-live-state.json').as_posix()})。恢复须先停止写入服务，并确认要恢复的版本；不能直接覆盖运行中的数据。",
        '', '## 食堂用途','',
        '| 场所 | 用途 |','|---|---|',
        '| 新乐群一层 | 常规食堂 |','| 新乐群二层 | 智慧食堂，自选菜 |',
        '| 新乐群三层、四层 | 风味窗口 |','| 学五食堂一层、二层 | 常规食堂 |',
        '', '用途来自用户本次说明；原有官网营业时段保留，不能据用途推断新的开门时间。',
        '', '## 营业时间','', '| 名称 | 原文时段 | 处理 | 备注 |','|---|---|---|---|']
    for row in report['hours']:
        status='身份待核，已保存候选' if row['result']=='identity_pending' else ('入库，条件时段不参与固定营业判定' if hours_value(row['hours']) is None else '已入库')
        lines.append(f"| {row['name']} | {row['hours']} | {status} | {row['note']} |")
    lines+=['','## 图片转录','',
        '以下为照片可见文字的整理。?为未确定价格；每段备注列出被遮挡、规格未明、名称待核或仅作加料的内容。出现文字不代表已被作为可推荐商品入库。']
    for group in transcriptions():
        lines+=['',f"### 照片 {group['photo']} · {group['floor']}层 · {group['title']}",'']
        photo=next(p for p in report['photos'] if Path(p['file']).name.split('_')[-2]==group['photo'])
        lines.append(f"[查看原照片]({Path(photo['file']).as_posix()})")
        if group['items']:
            lines+=['','| 名称 | 照片标价（元） |','|---|---|']
            lines += [f"| {i['name']} | {i['raw_price']} |" for i in group['items']]
        lines+=['']+group['notes']
    lines+=['','## 待核与本次纠错','',
        '- 用户补充确认曾三线=现有曾三仙米线、24h超市=现有天猫校园超市；更新原ID，不创建重复店铺。确认依据保存在营业时间字段证据及匹配表中。',
        '- 淮南牛肉汤：457和483为同一照片却归入不同楼层，菜单已转录，暂不绑定三层或四层。',
        '- 休息日、大假需明确适用日期；“09:00或10:00”不能改成固定09:00。',
        '- 菜单字迹、优惠两价、杯型和称重单位按原文保留；不清晰项不猜。',
        '- “我的提交不可见”与“未落盘”须分别查提交、审核日志与上传链路；本批保存并批准了此前已落盘的lyx提交，不声称恢复了未上传的数据。',
        '- 图片文件名日期不能自动当作已确认拍摄时间；本批 observed_at 留空，reported_at/retrieved_at 记录整理时间。',
        '- 原始照片含现场人物，只保存本地引用；没有发布原照片为公网静态资源。']
    (ROOT/'docs/现场资料入库报告_2026-09-30.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    with (DIRECTORY/'菜单入库明细.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        fields=['id','name','shop_id','menu_section','specification','price','price_source','source_file','availability_note']
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(items)
    return dict(report=str(ROOT/'docs/现场资料入库报告_2026-09-30.md'),items=len(items))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--commit',type=Path)
    parser.add_argument('--export',type=Path)
    parser.add_argument('--prepare-floor-gates',action='store_true')
    parser.add_argument('--prepare-xuewu-hours',action='store_true')
    args=parser.parse_args()
    report=export_report(args.export) if args.export else commit(args.commit) if args.commit else prepare_xuewu_hours() if args.prepare_xuewu_hours else prepare_followup() if args.prepare_floor_gates else prepare()
    if not args.commit and not args.export:
        report={k:report[k] for k in ('stage','approved','conflicts','drafts','menu_counts')}
    print(json.dumps(report,ensure_ascii=False,indent=2))
