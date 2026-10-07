"""Read-only, field-level map review from the published catalog."""
import math
from .storage import read, now
from .map_display import display_fields


def review_catalog(catalog, life):
    items=[i for i in catalog['items'] if i.get('source')!='simulated']
    shops=[s for s in catalog['shops'] if s.get('source')!='simulated']
    rows=[]
    for p in catalog['pois']:
        if p.get('source')=='simulated':
            continue
        loc=p.get('map_point') or p.get('location') or {}
        crs=loc.get('crs') if p.get('map_point') else p.get('location_crs')
        valid=crs=='local EPSG:32650' and all(isinstance(loc.get(k),(int,float)) and not isinstance(loc[k],bool) and math.isfinite(loc[k]) for k in ('x','y'))
        inside=valid and abs(loc['x'])<=452 and abs(loc['y'])<=601
        related=[s for s in shops if s.get('poi_id')==p['id']]
        sids={s['id'] for s in related}
        menu=[i for i in items if i.get('shop_id') in sids]
        issues=[]
        if not valid: issues.append('缺坐标：请在三维图点选或补充位置')
        elif not inside: issues.append('模型范围外：核实地址及采集范围')
        elif 'approximate' in p.get('location_source',''): issues.append('位置为近似值：核对入口或实际店面')
        business=p.get('category') not in ('building','gate','sports','library','dormitory')
        if business and not p.get('opening_hours'):
            issues.append('条件营业时间待明确' if p.get('opening_hours_text') else '营业时间缺失')
        unknown=[i for i in menu if i.get('price') is None]
        if unknown: issues.append(f'{len(unknown)}条真实商品缺价格')
        if any(s.get('independent_window_verified') is False for s in related):
            issues.append('菜单所属独立窗口待确认')
        rows.append(dict(id=p['id'],name=p.get('name',p['id']),address=p.get('address',''),
            floor=p.get('floor'),zone=p.get('zone'),category=p.get('category'),**display_fields(p),
            location=dict(x=loc['x'],y=loc['y']) if valid else None,on_map=bool(inside),
            location_source=p.get('location_source','未注明'),building_id=p.get('building_id'),
            opening_hours_text=p.get('opening_hours_text') or '；'.join('–'.join(v) for v in p.get('opening_hours') or []),
            hours_notes=p.get('hours_notes',''),source=p.get('source'),issues=issues,
            shops=[dict(id=s['id'],name=s.get('name'),floor=s.get('floor')) for s in related],
            items=[dict(id=i['id'],name=i.get('name'),price=i.get('price'),specification=i.get('specification'),source=i.get('source')) for i in menu]))
    duplicates=read(life/'possible_duplicates.json',[])
    updates=read(life/'update_candidates.json',[])
    return dict(generated_at=now(),rows=rows,
        counts=dict(pois=len(rows),on_map=sum(r['on_map'] for r in rows),missing_coordinates=sum(r['location'] is None for r in rows),
                    with_issues=sum(bool(r['issues']) for r in rows),real_items=len(items),unknown_prices=sum(i.get('price') is None for i in items),
                    duplicate_candidates=len(duplicates),update_candidates=len(updates)),
        duplicates=duplicates,updates=[dict(id=u.get('id'),name=u.get('candidate',{}).get('name')) for u in updates])


def export_review():
    from .adapters import CatalogAdapter
    from .storage import ROOT
    catalog=CatalogAdapter(ROOT/'data/life',ROOT/'data/campus_info.sqlite3').snapshot()
    result=review_catalog(catalog,ROOT/'data/life')
    c=result['counts']
    lines=['# 三维地图人工审核清单 — 2026-09-30','',
           '统计对象是未去重的已发布非模拟名录，包含校外及非商户对象，不代表现实商户覆盖率。',
           f"当前 {c['pois']} 条POI；模型内 {c['on_map']} 条；缺可用本地坐标 {c['missing_coordinates']} 条；真实商品/规格 {c['real_items']} 条，其中缺价格 {c['unknown_prices']} 条。",'',
           '## 查看与填写','',
           '启动原填报服务后，在 http://127.0.0.1:8792/ 选择 g 登录，再访问 http://127.0.0.1:8792/map/ 。地图可搜索、筛选并点击点位；橙色只表示有待核字段。',
           '同楼同坐标记录请用列表逐个选择；标记高度不表示楼层。缺坐标或模型范围外记录只在列表中显示。修改仍从原填写页面提交并审核。',
           '## 人工处理优先级','',
           '1. 先定位校内新录经营点：补点位、所属建筑、店铺楼层；同名店确认是否为分店。',
           '2. 核对照片菜单所属窗口，补12项缺价格；称重、规格、加料与完整餐品分开。',
           '3. 明确“09:00或10:00”、休息日和大假的适用条件，核对营业时段的当前有效性。',
           '4. 对比疑似重复、旧更新候选与现有正式值；候选可能已过时，不批量覆盖。',
           '5. 几何核对：小吃街缺楼、北侧补建低楼层数，东操场东侧场地及南苑建筑位置/轮廓/高度。已确认层数不自动代表现有模型已改。',
           '6. 最后现场抽查营业状态、菜单在售情况与实际耗时；这些不能由菜单照片推断。',
           '','## 已解决与待生效','',
           '- 淮南牛肉汤四层、校门开放时段已在正式目录中；不再重复请求确认。',
           '- 学五截图已识读：06:30–09:00、10:30–13:30、16:30–21:00；本轮自动写入/启动命令受阻，仍待正式提交。截图未提供拍摄日期或楼层适用范围。',
           '','## 缺可用坐标的逐店清单','']
    for p in result['rows']:
        if p['location'] is None: lines.append(f"- {p['name']}（{p['id']}）：{p['address'] or '地址待补'}；楼层 {p['floor'] or '未知'}")
    lines+=['','## 缺价格的真实菜单','']
    for p in result['rows']:
        for i in p['items']:
            if i['price'] is None:lines.append(f"- {p['name']}：{i['name']}（{i['specification'] or '规格待核'}；{i['id']}）")
    names={p['id']:p['name'] for p in result['rows']}
    lines+=['','## 原始疑似重复（逐组确认，不等于仍未处理）','']
    for d in result['duplicates']:
        a,b=d.get('baidu_id'),d.get('catalog_id')
        lines.append(f"- {names.get(a,a)} [{a}] ↔ {names.get(b,b)} [{b}]：{d.get('reason','核对同店与分店')}")
    lines+=['','## 原始更新候选（先核对是否已被人工修订取代）','']
    lines += [f"- {u['name'] or '名称未附'}：{u['id']}" for u in result['updates']]
    lines+=['','## 逐地点问题','']
    for p in result['rows']:
        if p['issues']:lines.append(f"- {p['name']} [{p['id']}]：{'；'.join(p['issues'])}")
    target=ROOT/'docs/三维地图人工审核清单_2026-09-30.md'
    target.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return dict(counts=c,report=str(target))


if __name__=='__main__':
    import json
    print(json.dumps(export_review(),ensure_ascii=False,indent=2))
