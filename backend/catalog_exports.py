"""Reproducible private data exports. Never overwrites a source or an earlier run."""
import argparse
import csv
import hashlib
import io
import json
import re
from pathlib import Path

from .storage import ROOT, now
from .life_relations import RelationRepository, fingerprint, PROJECTION_VERSION


def _json(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)


def _csv(rows, fields):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        cleaned = {}
        for name in fields:
            value = row.get(name)
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            if isinstance(value, str) and value.startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
                value = "'" + value
            cleaned[name] = value
        writer.writerow(cleaned)
    return '\ufeff' + stream.getvalue()


def _notebook(snapshot):
    # A stdlib-only companion; content never needs live data or credentials.
    def markdown(text):
        return dict(cell_type='markdown', metadata={}, source=text.splitlines(keepends=True))
    def code(text):
        return dict(cell_type='code', metadata={}, source=text.splitlines(keepends=True), execution_count=None, outputs=[])
    cells = [
        markdown('## tl;dr\n本次导出是只读关系投影，不是现实商户已全部核验。以下计算只读取本目录 snapshot.json。'),
        markdown('## Context & Methods\n单位：POI、Shop、Item、物理楼栋与菜单组分别计数。\n### Key Assumptions\n名称存在不等于精确点位；菜单组不等于真实独立窗口；模拟项单独报告。'),
        markdown('## Data\n从同目录版本快照读取，不连接账号、不调用外网。'),
        code("import json\nfrom pathlib import Path\nfrom collections import Counter\nsnapshot = json.loads(Path('snapshot.json').read_text(encoding='utf-8'))\nprint(snapshot['snapshot_id'])\nprint(snapshot['summary']['source_counts'])\n"),
        markdown('## Results\n核对原ID覆盖、窗口分组和名录。'),
        code("items = [x for x in snapshot['entities'] if x['ref']['kind'] == 'item']\nassert len({x['ref']['id'] for x in items}) == snapshot['summary']['source_counts']['items']\nassert set(snapshot['item_membership']) == {x['ref']['id'] for x in items}\nprint('Item IDs preserved:', len(items))\nprint('Menu groups:', len(snapshot['menu_groups']))\nprint('Roster:', snapshot['roster']['summary'])\nprint('Building content:', dict(Counter(x.get('content_origin', 'unknown') for x in snapshot['entities'] if x['ref']['kind'] == 'building')))\n"),
        code("for poi_id in ('canteen-3', 'canteen-4'):\n    groups = [g for g in snapshot['menu_groups'] if g['poi_id'] == poi_id and g['identity_status'] != 'simulated']\n    print(poi_id, len(groups), sum(len(g['item_ids']) for g in groups))\nprint('Issue kinds:', dict(Counter(i.get('code', 'unknown') for i in snapshot['issues'])))\n"),
        markdown('## Relationship network\n关系数不是独立商户数或推荐准确率。真实、模拟、记录、计算和推测分开统计；图中的链是证据链，不是步行路线。'),
        code("network = snapshot.get('network')\nif network:\n    node_keys = {n['ref']['kind'] + ':' + n['ref']['id'] for n in network['nodes']}\n    edge_ids = {e['id'] for e in network['edges']}\n    assert len(node_keys) == len(network['nodes'])\n    assert len(edge_ids) == len(network['edges'])\n    for edge in network['edges']:\n        for field in ('subject', 'object'):\n            ref = edge[field]\n            assert ref['kind'] + ':' + ref['id'] in node_keys\n        assert all(x in edge_ids for x in edge.get('supporting_edge_ids', []))\n        assert edge['type'] not in ('route_to', 'walkable_to', 'open_now')\n    assert dict(Counter(e['type'] for e in network['edges'])) == network['summary']['edge_types']\n    print('Network:', network['summary'])\n    print('Network limitations:', network['limitations'])\n"),
        markdown('## Takeaways\n以执行结果为准。已人工确认的20组窗口不再列作身份待核；招牌名称、未录时段、精确店门和实时在售是独立字段。本笔记不计算现实覆盖率或推荐准确率。更新后另导出一个run，不覆盖当前目录。')]
    for index, cell in enumerate(cells):
        cell['id'] = 'cell-' + str(index + 1)
    return dict(nbformat=4, nbformat_minor=5, metadata=dict(
        kernelspec=dict(display_name='Python 3', language='python', name='python3'),
        language_info=dict(name='python', version='3.13'),
        data_snapshot_id=snapshot['snapshot_id']), cells=cells)


def export_snapshot(snapshot, directory, run_id, input_hashes=None):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,100}', run_id) or '..' in run_id:
        raise ValueError('无效run_id')
    base = Path(directory).resolve()
    output = base / run_id
    if output.parent != base:
        raise ValueError('输出超出私有目录')
    if output.exists():
        raise FileExistsError('已有同名导出，保留原版本；请选择新run_id')
    output.mkdir(parents=True, exist_ok=False)
    entities = snapshot['entities']
    artifacts = {'snapshot.json': _json(snapshot),
                 'relations.json': _json(snapshot['relations']),
                 'menu-groups.json': _json(snapshot['menu_groups']),
                 'roster-review.json': _json(snapshot['roster']),
                 'review-issues.json': _json(snapshot['issues'])}
    network = snapshot.get('network')
    if network:
        artifacts['network.json'] = _json(network)
        artifacts['network-edges.csv'] = _csv(network['edges'],
            ['id', 'type', 'subject', 'object', 'status', 'data_mode', 'graph_visible',
             'basis', 'distance_m', 'direction', 'symmetric', 'precision', 'original_category',
             'rule_origin', 'rule_version', 'evidence_refs', 'supporting_edge_ids', 'limitations'])
        artifacts['network-issues.csv'] = _csv(network['issues'],
            ['code', 'entity', 'severity', 'reason', 'recorded_category', 'proposed_category',
             'affected_poi_count', 'message', 'note'])
        from .poi_network_query import query_network
        examples = [('科技楼瑞幸的同类比较', 'poi', 'luckin', 'same_type'),
                    ('蜜雪冰城的直接关系', 'poi', 'baidu-9d9d7030bb7bcc77e0110373', 'neighbors'),
                    ('蜜雪与餐饮的组合发现', 'poi', 'baidu-9d9d7030bb7bcc77e0110373', 'complementary'),
                    ('新三窗口的同类比较', 'outlet', 'outlet-xinlequn-3-001', 'same_type'),
                    ('西侧乡村基的关系链', 'poi', 'reported-174e0a7adb61c3ad', 'chain'),
                    ('图书馆与其他服务的组合缺口', 'building', '267944894', 'complementary'),
                    ('优果荟与天猫的定性相邻', 'poi', 'baidu-4fa1ea3de624c94dc7effb11', 'neighbors')]
        node_index = {e['ref']['kind'] + ':' + e['ref']['id']: e for e in network['nodes']}
        artifacts['network-examples.json'] = _json([
            dict(question=title, query=dict(kind=kind, ident=ident, mode=mode, limit=8),
                 result=query_network(snapshot, kind=kind, ident=ident, mode=mode, limit=8))
            for title, kind, ident, mode in examples if node_index.get(kind + ':' + ident, {}).get('graph_visible')])
    for kind in ('building', 'floor', 'poi', 'outlet', 'collection', 'item', 'area', 'building_group'):
        artifacts[kind + 's.json'] = _json([e for e in entities if e['ref']['kind'] == kind])
    artifacts['shops-roster.csv'] = _csv(snapshot['roster']['rows'],
        ['id', 'name', 'roster_name', 'group', 'order', 'present', 'category', 'floor',
         'building_id', 'has_display_point', 'location_mode', 'operational_status'])
    artifacts['menus.csv'] = _csv([dict(id=e['ref']['id'], **{k:v for k,v in e.items() if k != 'ref'})
                                  for e in entities if e['ref']['kind'] == 'item'],
        ['id', 'name', 'poi_id', 'group_id', 'outlet_id', 'specification', 'price', 'price_unit',
         'meal_role', 'identity_status', 'source', 'is_simulated', 'availability'])
    artifacts['buildings.csv'] = _csv([dict(id=e['ref']['id'], **{k:v for k,v in e.items() if k != 'ref'})
                                      for e in entities if e['ref']['kind'] == 'building'],
        ['id', 'name', 'description', 'content_origin', 'description_status', 'review_state', 'source_links'])
    artifacts['confirmed-windows.csv'] = _csv([dict(id=e['ref']['id'], **{k:v for k,v in e.items() if k != 'ref'})
                                              for e in entities if e['ref']['kind'] == 'outlet' and e.get('source_collection_id')],
        ['id', 'name', 'poi_id', 'floor', 'menu_group_id', 'source_collection_id', 'identity_status',
         'name_status', 'hours_label', 'opening_hours', 'identity_evidence'])
    artifacts['review-issues.csv'] = _csv(snapshot['issues'],
        ['code', 'entity', 'item_id', 'poi_id', 'group_id', 'ids', 'severity', 'review_state', 'message', 'detail', 'note'])
    artifacts['inspect.ipynb'] = _json(_notebook(snapshot))
    summary = snapshot['summary']
    roster = snapshot['roster']['summary']
    lines = ['# 校园数据整理结果', '', '状态：数据阶段预发布；未改UI、原库或模型。',
             '', '- 数据版本：`' + snapshot['snapshot_id'] + '`',
             '- 原对象：' + json.dumps(summary['source_counts'], ensure_ascii=False),
             '- 菜单分组：' + str(len(snapshot['menu_groups'])) + '（含模拟，不能称真实窗口数）',
             '- 本批已确认独立窗口：' + str(sum(e['ref']['kind'] == 'outlet' and bool(e.get('source_collection_id')) for e in entities)) + '；身份确认不等于时段、招牌和实时在售全部核验。',
             '- 已知时间表名录：' + str(roster['present_count']) + '/' + str(roster['expected_roster_count']),
             '- 当前展示点：' + str(roster['displayable_count']) + '；无展示点：' + str(roster['without_display_point_count']),
             '- 现实店铺完整性：未知，需要现场核对。', '',
             '## 从哪里查看', '',
             '- shops-roster.csv：38项逐行名录、类别、楼层和位置精度。',
             '- menus.csv / menu-groups.json：商品→菜单组→窗口（可为空）→楼层入口。',
             '- confirmed-windows.csv：本批20个窗口，含楼层、原集合ID及尚未录入的营业时间。',
             '- buildings.csv：楼名、用途、依据、待核状态。',
             '- relations.json：包含、别名同店、相邻/东西/建筑部位、区域成员与原集合溯源；定性关系不产生精确坐标。',
             '- network.json / network-edges.csv：多维关系图；类别、服务、品牌、标签采用共享概念，不两两造边。',
             '- network-examples.json：从本次数据实际运行的邻域、同类、跨类与证据链查询；不是模型生成答案。',
             '- network-issues.csv：无法计算距离、分类冲突、截断及路网缺失；不等于所有对象都需要重新采集。',
             '- review-issues.csv / .json：仍缺的位置与计价信息（同一对象可能有多条问题，不能相加当商户数）。',
             '- inspect.ipynb：只读复算覆盖与数量。', '',
             '## 新三与新四分组', '', '| 楼层入口 | 菜单分组 | 条目数 | 身份状态 |', '|---|---|---:|---|']
    for group in snapshot['menu_groups']:
        if group['poi_id'] in ('canteen-3', 'canteen-4') and group['identity_status'] != 'simulated':
            lines.append('| ' + ' | '.join([group['poi_id'], group['name'].replace('|', '/'),
                         str(len(group['item_ids'])), group['identity_status']]) + ' |')
    lines.extend(['', '## 使用边界', '',
                  '来源照片转录不等于当前在售；推测简介持续带标记。字段未知保持未知。',
                  '这里是派生整理包，不是源库迁移；不要把它直接覆盖 catalog.json 或 contributions/state.json。',
                  '本目录私有，不在HTTP静态白名单；重新生成必须使用新run_id。'])
    if network:
        lines.extend(['', '## 本轮关系网络', '',
                      '网络契约：' + network['contract_version'] + '；规则：' + network['rule_version'],
                      '', '```json', _json(network['summary']), '```', '',
                      *['- ' + note for note in network['limitations']]])
    artifacts['README.md'] = '\n'.join(lines) + '\n'
    for filename, body in artifacts.items():
        with (output / filename).open('x', encoding='utf-8', newline='') as stream:
            stream.write(body)
    manifest = dict(run_id=run_id, created_at=now(), projection_version=PROJECTION_VERSION,
                    snapshot_id=snapshot['snapshot_id'], source_mutated=False,
                    input_hashes=input_hashes or {},
                    files={name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in artifacts})
    with (output / 'manifest.json').open('x', encoding='utf-8') as stream:
        stream.write(_json(manifest))
    reopened = json.loads((output / 'snapshot.json').read_text(encoding='utf-8'))
    if fingerprint(reopened) != fingerprint(snapshot):
        raise ValueError('导出重读校验失败')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', default='data-' + now().replace(':', '-').replace('+', '_'))
    args = parser.parse_args()
    source_files = ['data/life/catalog.json', 'data/life/baidu_normalized.json',
                    'data/life/contributions/state.json', 'data/campus_info.sqlite3',
                    'assets/campus_assets_white_v6.json']
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in source_files if (ROOT / name).exists()}
    snapshot = RelationRepository.load()
    after = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in source_files if (ROOT / name).exists()}
    if hashes != after:
        raise ValueError('源数据在核对期间变化，请完成发布后重新导出')
    output = export_snapshot(snapshot, ROOT / 'data/life/organized', args.run_id, hashes)
    print(json.dumps(dict(output=str(output), summary=snapshot['summary'], roster=snapshot['roster']['summary']), ensure_ascii=False))


if __name__ == '__main__':
    main()
