# 1.20.0 前置数据与发布审计

检查日期：2026-10-08。只读运行，未改变数据、代码行为、账号、模型配置或 Git 历史。这里不是升级验收报告。

## 1. 口径

检查对象是本机当前 `CatalogAdapter.snapshot()` 合成后的数据，以及 `CampusTools` 对外查询投影。条目数按 ID 计数；菜单数量包含规格，不等于互不重复的菜品数。名称存在、可搜索、地图可显示、现实位置准确是四个不同指标。

| 数据层/检查 | 数量或结果 |
|---|---:|
| 基础 catalog.json | 24 POI / 34 Shop / 200 Item |
| 合成快照 | 309 POI / 296 Shop / 560 Item |
| 公开目录 | 308 POI，排除 1 条历史记录 |
| Item 来源 | 200 模拟 / 352 菜单照片 / 8 现场填报 |
| Shop→POI 孤儿 | 0 |
| Item→Shop 孤儿 | 0 |
| 指向缺失建筑的 building_id | 0 |
| 建筑目录对象 | 234，其中 83 有名称、151 无名称 |

296 个 Shop 包含 20 个模拟窗口与楼层集合等，不能作为真实商户数量。上述引用全部存在，也不意味着包含/所属关系在语义上正确。此次没有执行历史趋势分析，不将单次快照当作店铺消失的时间序列证据。

## 2. 菜单混杂：高严重性，高置信度

源数据情况：

| POI | 父对象 | 非模拟菜单规格条目 |
|---|---|---:|
| canteen-3 | menu-collection-xinlequn-3 | 98 |
| canteen-4 | menu-collection-xinlequn-4 | 248 |
| canteen-4 | shop-huainan-xinlequn-4 | 6 |

楼层集合的 `entity_type=floor_menu_collection`，`independent_merchant=false`。346 条集合条目的 `independent_window_verified=false`。历史工作完成的是楼层归档，不是逐窗口归属。

接口 `backend/agent/tools.py:63–74` 汇总 POI 下所有 Shop 的 Item，只保留 name、price、specification、source。`id/shop_id/menu_section` 丢失，导致已独立的淮南也混进四层。

前端 `app/explore/main.js` 的 `renderPlace` 平铺 `p.menu`。默认首批 60 条；新四首批几乎全是第一份饮品菜单，用户难以找到其余窗口。

推荐在 `backend/agent/candidates.py` 按 shop_id 去重，因此一个楼层集合被当作同一家商户，无法真实比较楼层内窗口。

最小修复：保留安全稳定 ID，恢复 menu_groups，按窗口/来源组浏览与分页；源头未知归属仍保留待核。不根据同名菜或相邻屏幕自动合并店铺。

## 3. 来源菜单分组盘点

25 张转录照片中，已发布菜品使用 23 张。457/483 为重复淮南图片；475 是称重信息，没有固定整餐 Item。

### 新三：8 组、98 项

| 原菜单分组线索 | 条目数 |
|---|---:|
| 广式现炒／现炒盖饭 | 19 |
| 重庆嘞碗面／老麻抄手／川味米线 | 25 |
| 贵州蘸水菜 | 5 |
| 甜品小吃／手工咖喱／鲜香水煮 | 10 |
| 6号重庆手撕鸡饭／贵州鸡汤饭 | 12 |
| 风味美食／鲜猪肚鸡汤／武汉黑鸭煲 | 7 |
| 柳香园螺蛳粉／粤式烧腊 | 8 |
| 醉面 | 12 |

### 新四：13 组、254 项

| 原菜单分组线索 | 条目数 |
|---|---:|
| 饮品甜点，店名未见 | 116 |
| 水饺／小谷姐姐麻辣拌邻屏 | 26 |
| 精品拌粉 | 8 |
| 吊龙米线 | 9 |
| 朱家小馆（477+478） | 14 |
| 馋嘴饭（479+480） | 16 |
| 港味苑叉烧饭四宝饭 | 5 |
| 重庆小面／干拌面／刀削面 | 15 |
| 土豆粉 | 15 |
| 轻拌饭 | 4 |
| 肥肠鸡香锅 | 4 |
| 鸡柳大人／汉堡套餐 | 16 |
| 淮南牛肉汤 | 6 |

**8+13 是来源分组数，不是已确认窗口数。** 除淮南外，20 个来源组/346 项尚未有独立核验窗口映射。

本轮复看 462、472、477、487 原图，得到：

- 462 的“6 重庆手撕鸡饭”店招与菜单屏清晰，可形成 12 项归属候选。
- 477 可见朱家小馆品牌，477/478 转录合组可形成 14 项窗口候选。
- 472 为相邻屏幕，26 项实际是水饺规格，不能改成小谷姐姐的菜单。
- 487 左鸡柳、右汉堡套餐，是否同经营窗口仍不明确。
- 471 的 116 项不能猜成某个连锁饮品品牌。
- 473/474 关系待核；475 与 472 左屏可补称重规则，但不能生成固定整餐价格。

优先复核 471、472、473、474、475、487 共 6 张；其中 5 张关联现有 175 项，475 尚无整餐条目。

同名菜保留不同出处，例如三层不同分组都有红烧牛肉面，四层不同分组都有酸菜肉丝面；价格不同不是必然错误，不按名字去重。

## 4. 搜索失败：高严重性，高置信度

| 实测查询 | 结果 |
|---|---|
| 新三、新四 | 均为 0 |
| 学三、学四 | 各 1 |
| 淮南牛肉汤 | 命中整个学四食堂 |
| 朱家小馆、6号重庆手撕鸡饭、小谷姐姐、烤盘饭 | 均为 0 |

`backend/agent/tools.py:51–59` 只匹配 POI/Shop 名称与部分别名，不匹配来源菜单组。修复不仅是加别名，还要让搜索返回具体匹配层级和父路径，不能全部指回楼层大卡。

## 5. 店铺“丢失”：当前名录未丢，空间表达不充分

时间表 `data/life/field-20260930/hours.tsv` 的 38 条均在公开目录。

| 分组 | 名录数 | 有可用展示点 | 无点 |
|---|---:|---:|---:|
| 北段生活服务 | 2 | 0 | 2 |
| 小吃街主排 | 13 | 3 | 10 |
| 南侧二层 | 3 | 0 | 3 |
| 学五周边 | 6 | 1 | 5 |
| 西侧时间表部分 | 5 | 1 | 4 |
| 天猫校园服务组 | 9 | 2 | 7 |
| 合计 | 38 | 7 | 31 |

“有展示点”包含楼栋代表点，并非 7 个已测量店门。此项风险为高，置信度高；不应继续将名录覆盖 38/38 当作地图验收通过。

主排从北到南：小果匠水果捞、蜜雪冰城、肯德基、无名缘粉面、卤肉饭、苗香掉渣饼、沪上阿姨、渝见你酸辣粉、彩棠里、好这口重庆小面、曾三仙米线、学之缘饼屋、快客100。只有蜜雪、肯德基、曾三仙具有当前可用点位。

西侧组：

| 店铺 | 安全 ID | 关系状态 |
|---|---|---|
| 乡村基 | reported-174e0a7adb61c3ad | 西侧参照，无所属模型建筑 |
| 塔斯汀 | reported-f91106f326893dd0 | 同上 |
| 鹏记重庆鸡公煲 | reported-af9de3e5b1e29fe6 | 同上，二层 |
| 夜罐罐米线 | reported-25db5caa2fbffbf4 | 同上，二层 |
| 库迪咖啡 | reported-cotti-northwest-campus | 同上，一层，照片额外补录 |
| 西北风味餐厅 | baidu-7388dffd488f73f2d3ff2365 | 有点，建筑 499437130，是独立参照对象 |

前五家“同楼”缺逻辑实体承接。不能直接复制参照建筑 499437130 作为它们所属楼栋。

当前 1.9 以后的列表代码已有完整分页；过去 120 条截断不是当前确定根因。一级吃喝包含餐饮+饮品，但后端/前端蜜雪分类仍不一致。`markerGroups` 排除无点位对象可以避免伪精确落点，却必须配套区域名录入口。

## 6. 其他风险

- 建筑简介目前只是模板位置说明；83 个有名建筑也不能视为已补职能。严重性中、置信度高。
- `map_review.py` 在 Shop 查独立窗口标志，但相关未核状态主要在 Item，可能遗漏 346 项提示。严重性中，需新增单测核验。
- `package_release.py` 扩展名白名单遗漏无扩展名 `vendor/three/LICENSE`。严重性高，发布前修复。
- 当前包清单 320 个文件、364,973,833 字节（未压缩）；约 310MB 在 output，含历史模型/Blend。保留旧文件但新运行包不必带全部。
- HTTP 公共模型剥离 extras，归档原模型未必剥离；二者不能混称脱敏。
- GitHub 已只读确认为私有 `guoyukun61-droid/bnu-campus-3d`；最近提交 v1.12.1，本地 1.13–1.15 未提交。推送前审查准确文件范围。

## 7. 最小修复及自动验收

先在合成快照之后建立只读版本投影，保留源库、历史、ID；修复 DTO 后 UI 消费统一关系，不在前端重复补分类。

必测：

1. 98+254 条原菜单规格记录无丢失、无重复造项；分组后全部可分页。
2. 已确认淮南 6 项只属于其四层窗口；待核窗口不自动升级为真实身份。
3. 新三/新四别名、朱家等来源组可搜索，返回匹配路径。
4. 38 条时间表、主排 13 条、西侧组 6 条在搜索/列表/区域入口均可达。
5. 示意点、参照物和代表点不参与真实距离/准时保证。
6. ID 稳定，父引用存在，包含关系无环；人工修订不覆盖。
7. 真实、模拟、推测分开计数；价格未知、称重、加料不误当完整餐品。
8. 安全公开 DTO 不暴露 source_file 本地路径、原图或个人信息。

## 8. 复现检查

在项目根目录运行下面的只读命令，不初始化或迁移，不访问账号目录。输出统计与安全商户字段，不输出照片路径或提交者信息。

```powershell
@'
import sys
sys.stdout.reconfigure(encoding="utf-8")
import csv, hashlib
from collections import Counter
from pathlib import Path
from backend.adapters import CatalogAdapter
from backend.agent.tools import CampusTools

root = Path(".")
c = CatalogAdapter(root / "data/life", root / "data/campus_info.sqlite3").snapshot()
t = CampusTools(c)
public = t.directory()["pois"]
index = {p["id"]: p for p in public}
print("TOTAL", {k: len(c[k]) for k in ("pois", "shops", "items")})
print("PUBLIC", len(public))
print("SOURCES", dict(Counter(i.get("source") for i in c["items"])))
for pid in ("canteen-3", "canteen-4"):
    shop_ids = {s["id"] for s in c["shops"]
                if s["poi_id"] == pid and s.get("source") != "simulated"}
    items = [i for i in c["items"] if i["shop_id"] in shop_ids
             and i.get("source") != "simulated"]
    print(pid, len(items), dict(Counter(
        (i["shop_id"], i.get("menu_section")) for i in items)))
with (root / "data/life/field-20260930/hours.tsv").open(
        encoding="utf-8", newline="") as f:
    rows = list(csv.DictReader(f, delimiter="\t"))
for n, r in enumerate(rows, 1):
    ident = r["poi_id"] or "reported-" + hashlib.sha256(r["name"].encode()).hexdigest()[:16]
    p = index.get(ident, {})
    point = p.get("display_anchor") or p.get("location")
    inside = bool(point and abs(point["x"]) <= 452 and abs(point["y"]) <= 601)
    print(n, r["name"], "present", bool(p), "displayable", inside,
          "reference", bool(p.get("map_reference")))
for query in ("新三", "新四", "学三", "学四", "朱家小馆", "淮南牛肉汤"):
    r = t.execute("search_places", {"query": query}, {})
    print("SEARCH", query, r["total"], [(p["id"], p["name"]) for p in r["cards"]])
'@ | & 'C:/Users/gyk11/AppData/Local/Programs/Python/Python313/python.exe' -B -
```

几何范围判断用于复现当前地图展示条件，不证明真实店门精度。此审计不能证明现实商户完整、当前在售或官网时效；升级后的复测必须重新运行，不能沿用本报告数字当新结果。
