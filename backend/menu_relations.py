"""Pure, evidence-aware menu projection. Never reads or modifies source files.

IDs below are a fixed registry, not hashes of mutable titles. A source photo hash
selects a registered group only under its original floor collection. Replacing a
photo/title needs an explicit registry alias; it must not silently create a new
merchant. For unknown collections the fallback hashes (stable parent ID, stable
evidence ID/hash), or the original Item ID when evidence is absent. It deliberately
does not hash menu_section, source_file, names, prices or array positions.

On 2026-10-08 the user confirmed the 20 registered collection groups each refer
to an independent window. This confirmation adds derived outlet identities, not
new source Shop rows. The existing Huainan window remains its original identity.
Recorded menu labels still do not prove exact signboard names or current sales.
Photo 475 and the left part of 472 have weight pricing, not fixed-price meal Items.
Only safe evidence summaries are returned: no file names, paths or raw audits.
"""

import hashlib
import json
import re
from .catalog_identity import MIXUE, IDENTITY_RULES


RULE_VERSION = "1.20.0-data.2"
_FLOOR_PARENTS = {
    "menu-collection-xinlequn-3": ("canteen-3", "3"),
    "menu-collection-xinlequn-4": ("canteen-4", "4"),
}

# Fixed photo identities from the existing private transcription. Hashes contain
# no image/personal information and let file renames retain group identity.
_PHOTO_HASHES = {
    "458": "fb856ad15e855a46267f8209de2e822a190d0846da05e8143765535589a87da1",
    "459": "526c36920c928e2171819499d4ff47fc07d26b34da202370d1a7017c502013d3",
    "460": "078180e9e233557d77c5290c2d76dc4687ef68f9c81aeaa87262163162969b33",
    "461": "aa89d296f3f53144a8448f72151cf1a5477b99a83e49aae4cbe1fba2a4d1aeda",
    "462": "61ae71400d53a131ac3cdde0aa1b15446da33738f0d85217025b940a2f03d0fa",
    "463": "62454b5751c982093ac1d3a2428fc08641627580154dc82d8eae6ef0ca23e2e7",
    "464": "85e14d468ee9221b1f721f833d293e910a6ba28f2878d97ca9bd9c3c3af04900",
    "466": "da549845a68de7fea1589c0e2f4a3d80b604185279b3a6cb3e225cb8bf6c29b7",
    "471": "cc3a297e86585b325d2c774656a216f5e14b5bbba6136e79e697b40419ac1213",
    "472": "a236b15641fbf09d631cc1a7a123d8dca022d4c94e4c300b3904dbe61d3a6094",
    "473": "0e8d9a366be7d019c686181f1af3b709e42ff2d51b357bb126256534c94fffa2",
    "474": "2723c61591ab1f7179ab2abf9e5ad51af861a7b1726020b8e6b74be857417776",
    "477": "89d74cb0ef0f444cc3edbb8b7baffc3ba2bad04d237d3697ddb9bb72cd42bf62",
    "478": "f6d91c6aa8b90e4f8ec5fb1011aab6a18cfb19d7f3fa77b9e05b4c1a0b20e61b",
    "479": "bfa61b806019f5e0b74c660a9ed5583295c1c1397b07cdfe5d45c3cb32a98a81",
    "480": "96eb3e9aa6b1e3413a76c79f0829b97024a071ebfcca97b441def05e63487533",
    "481": "9b6d70d86c48af59dbfa62cd9ac3d1ec817b35770b5b7edeef1af64c1fcb843f",
    "482": "955410034de5faeb0481fe2ee626cacd41d8d978ce3abb5039250d47932cd758",
    "484": "63eb9f8ab1edbc3f76d6d8dd604b2d1b78dc0187019f939ac77bea7e85dbac9a",
    "485": "fc15a7ad7fedfd285010a102f562c1b57bf91eec22a9b0ae6759a66fec6c780b",
    "486": "ce6ce2208f2ab8a3ac13d0b5ce980e45ae20a0db6f8b794e5212f3e9be5bd6e8",
    "487": "d11d56a3bd420a529d4025564ac529ce22f94a060d5aad97bfcfb22b57fed60c",
}
_PHOTO_BY_HASH = {value: key for key, value in _PHOTO_HASHES.items()}

# (stable id suffix, floor, photo ids, display label, identity, category, meal role)
# All 20 identities are explicitly confirmed by the user's 2026-10-08 follow-up.
# Display labels are retained transcription descriptions, not verified branding.
_RULES = (
    ("3-001", "3", ("458",), "广式现炒／现炒盖饭", "confirmed", "food", "main"),
    ("3-002", "3", ("459",), "重庆嘞碗面／老麻抄手／川味米线", "confirmed", "food", "main"),
    ("3-003", "3", ("460",), "贵州蘸水菜", "confirmed", "food", "unknown"),
    ("3-004", "3", ("461",), "甜品小吃／手工咖喱／鲜香水煮", "confirmed", "food", "mixed"),
    ("3-005", "3", ("462",), "6号重庆手撕鸡饭／贵州鸡汤饭", "confirmed", "food", "main"),
    ("3-006", "3", ("463",), "风味美食／鲜猪肚鸡汤／武汉黑鸭煲", "confirmed", "food", "unknown"),
    ("3-007", "3", ("464",), "柳香园螺蛳粉／粤式烧腊", "confirmed", "food", "main"),
    ("3-008", "3", ("466",), "醉面", "confirmed", "food", "main"),
    ("4-001", "4", ("471",), "饮品甜点（窗口名称待核）", "confirmed", "drinks", "mixed"),
    ("4-002", "4", ("472",), "水饺菜单（邻屏小谷姐姐不归入本组）", "confirmed", "food", "main"),
    ("4-003", "4", ("473",), "精品拌粉", "confirmed", "food", "main"),
    ("4-004", "4", ("474",), "吊龙米线", "confirmed", "food", "main"),
    ("4-005", "4", ("477", "478"), "朱家小馆", "confirmed", "food", "main"),
    ("4-006", "4", ("479", "480"), "馋嘴饭", "confirmed", "food", "main"),
    ("4-007", "4", ("481",), "港味苑叉烧饭四宝饭", "confirmed", "food", "main"),
    ("4-008", "4", ("482",), "重庆小面／干拌面／刀削面", "confirmed", "food", "main"),
    ("4-009", "4", ("484",), "土豆粉", "confirmed", "food", "main"),
    ("4-010", "4", ("485",), "轻拌饭", "confirmed", "food", "main"),
    ("4-011", "4", ("486",), "肥肠鸡香锅", "confirmed", "food", "unknown"),
    ("4-012", "4", ("487",), "鸡柳大人／汉堡套餐", "confirmed", "food", "mixed"),
)
_RULE_BY_PHOTO = {photo: rule for rule in _RULES for photo in rule[2]}
_HUAINAN = "shop-huainan-xinlequn-4"
_UNSAFE_LABEL = re.compile(r"[A-Za-z]:[\\/]|(?:https?|file)://|\\\\|/(?:Users|home|tmp|data)/", re.I)
_DESSERT = re.compile(r"布丁|双皮奶|冰粉|冰豆花|酒酿小丸子|清补凉|西米露|圣代|雪顶|冰淇淋")
_DRINK = re.compile(r"奶茶|牛奶|轻乳茶|果茶|红茶|绿茶|柠檬水|酸梅汤|咖啡|美式|拿铁|可可|果汁|奶昔|养乐多|益菌多|杨枝甘露")
_SIDE = re.compile(r"单买|单点|单加|加料|鸡柳|薯条|年糕|盐酥鸡")
_MAIN = re.compile(r"饭|面|米线|米粉|拌粉|土豆粉|河粉|螺蛳粉|水饺|套餐|汉堡|鸡腿堡")


def _digest(*values):
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()[:24]


def _label(value, fallback):
    if not isinstance(value, str) or not value.strip() or _UNSAFE_LABEL.search(value):
        return fallback
    return " ".join(value.split())[:160]


def _floor(value):
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return _label(value, "")


def _index(catalog, kind):
    result = {}
    for row in catalog.get(kind, []):
        ident = row.get("id") if isinstance(row, dict) else None
        if not isinstance(ident, str) or not ident or ident in result:
            raise ValueError(kind + " contains invalid or duplicate IDs")
        result[ident] = row
    return result


def record_data_mode(*records):
    # Both provenance fields inherit through the source hierarchy. A real-looking
    # child must never erase an explicitly simulated or inferred ancestor.
    sources = {row.get(field) for row in records
               for field in ("source", "content_origin", "price_source")}
    if "simulated" in sources:
        return "simulated"
    if sources & {"inferred", "illustrative", "generated"}:
        return "inferred"
    return "real"


def _mode(item, shop, poi):
    return record_data_mode(item, shop, poi)


def _source(value):
    if value in {"simulated", "menu_photo", "official_menu", "field_observation", "baidu_place_v2",
                 "inferred", "illustrative", "generated", "published", "unknown"}:
        return value
    if isinstance(value, str) and value.startswith("user_"):
        return "user_reported"
    return "unknown"


def _category(poi, shop):
    # Same explicit Mixue identity already corrected by the old frontend, now in
    # the read projection as well. Source rows are never overwritten.
    if poi["id"] == MIXUE and poi.get('name') in IDENTITY_RULES[MIXUE]['names']:
        return "drinks"
    category = shop.get("category") or poi.get("category")
    if category in {"coffee", "drink", "drinks"}:
        return "drinks"
    if category in {"canteen", "restaurant", "snack", "food"}:
        return "food"
    if category in {"retail", "supermarket"}:
        return "retail"
    return "other"


def _meal_role(item, group):
    explicit = item.get("meal_role")
    if explicit in {"main", "drink", "snack", "side", "weight_based", "unknown"}:
        return explicit
    kind = item.get("item_type")
    if kind in {"side", "add_on"}:
        return "side"
    if kind in {"weight_based", "by_weight"}:
        return "weight_based"
    if kind in {"drink", "dessert", "snack"}:
        return "drink" if kind == "drink" else "snack"
    name = str(item.get("name") or "")
    if _DESSERT.search(name):
        return "snack"
    if _DRINK.search(name):
        return "drink"
    if re.search(r"单买|单点|单加|加料", name):
        return "side"
    if group["category"] == "drinks":
        return "drink"
    # A menu bundle can have soup without rice or a side; do not inherit 'main'
    # merely because its parent venue is a canteen.
    if _MAIN.search(name):
        return "main"
    if _SIDE.search(name):
        return "snack"
    return "unknown"


def _known_rule(item, shop):
    parent = _FLOOR_PARENTS.get(shop["id"])
    if parent is None or shop.get("poi_id") != parent[0] or item.get("source") != "menu_photo":
        return None
    photo = _PHOTO_BY_HASH.get(item.get("source_photo_sha256"))
    rule = _RULE_BY_PHOTO.get(photo)
    return rule if rule is not None and rule[1] == parent[1] else None


def _is_collection(shop):
    return (shop.get("entity_type") == "floor_menu_collection"
            or shop.get("independent_merchant") is False or shop["id"] in _FLOOR_PARENTS)


def _canonical_shop_id(shop, shops, poi):
    """Resolve approved Shop aliases without crossing venue or data-mode bounds.

    Source Shop/Item IDs stay unchanged. Broken aliases fail rather than letting
    items silently disappear or attach to an unrelated/simulated merchant.
    """
    current, seen = shop, set()
    while True:
        ident = current["id"]
        if ident in seen:
            raise ValueError("Canonical Shop alias cycle")
        seen.add(ident)
        if (current.get("poi_id") != poi["id"] or _is_collection(current)
                or record_data_mode(current, poi) != "real"):
            raise ValueError("Canonical Shop crosses venue, collection or data-mode boundary")
        target = current.get("canonical_shop_id")
        if target is None:
            return ident
        if not isinstance(target, str) or not target or target not in shops:
            raise ValueError("Canonical Shop target is invalid or missing")
        current = shops[target]


def _group_for(item, shop, poi, mode, conflicted_groups=(), canonical_outlet_id=None):
    rule = _known_rule(item, shop) if mode == "real" else None
    if rule is not None:
        suffix, floor, photos, name, identity, category, meal_role = rule
        if ("menu-group-xinlequn-" + suffix in conflicted_groups
                or any(_floor(row.get("floor")) not in ("", floor) for row in (item, shop, poi))):
            identity = "source_only"
        floor = _floor(shop.get("floor") or poi.get("floor")) or floor
        confirmed = identity == "confirmed"
        return dict(id="menu-group-xinlequn-" + suffix, poi_id=poi["id"], name=name,
                    floor=floor, outlet_id="outlet-xinlequn-" + suffix if confirmed else None,
                    source_collection_id=shop["id"], identity_status=identity,
                    name_status="recorded_description_not_signboard_verified",
                    identity_evidence=dict(source="user_confirmation", confirmed_at="2026-10-08",
                        observed_at=None, applied=confirmed,
                        scope="20个既定菜单组各自对应独立窗口；不确认招牌名称、营业时段或当前在售。"),
                    category=category, meal_role=meal_role, source="menu_photo",
                    evidence_summary=dict(source="menu_photo", photo_labels=list(photos), observed_at=None,
                        identity_source="user_confirmation",
                        note="用户确认本菜单组对应独立窗口；名称沿用菜单描述，招牌名、营业时段和当前在售尚未重新核实。"
                        if confirmed else "楼层记录与确认范围冲突，暂不应用窗口身份确认；保留原分组和楼层，等待核对。"))
    if shop["id"] == _HUAINAN and poi["id"] == "canteen-4" and mode == "real":
        conflict = any(_floor(row.get("floor")) not in ("", "4") for row in (item, shop, poi))
        return dict(id="menu-group-xinlequn-4-013", poi_id=poi["id"], name="淮南牛肉汤",
                    floor=_floor(shop.get("floor") or poi.get("floor")) or "4", outlet_id=canonical_outlet_id or _HUAINAN,
                    identity_status="existing_shop" if conflict else "confirmed", category="food",
                    meal_role="mixed", source="menu_photo",
                    evidence_summary=dict(source="user_reported", photo_labels=["483"], observed_at=None,
                        note="楼层记录存在冲突，保留既有窗口身份和原楼层值。" if conflict else "用户确认淮南牛肉汤位于四层；保留既有独立窗口，实时在售未知。"))
    collection = _is_collection(shop)
    if collection:
        evidence = item.get("source_evidence_id") or item.get("evidence_id") or item.get("source_photo_sha256")
        token = ("evidence", evidence) if isinstance(evidence, str) and evidence else ("item", item["id"])
        ident = "menu-group-unresolved-" + _digest(shop["id"], mode, *token)
        identity = "source_only" if token[0] == "evidence" else "unassigned"
        name = _label(item.get("menu_section"), "本层待归属菜单")
        outlet = None
        note = "仅整理原记录的稳定证据组；窗口身份和独立商户关系未确认。"
    else:
        ident = "menu-group-shop-" + _digest(shop["id"], mode)
        identity = "confirmed" if shop.get("identity_status") == "user_confirmed" else "existing_shop"
        name = _label(shop.get("name"), "已录入店铺菜单")
        outlet = (canonical_outlet_id or shop["id"]) if mode == "real" else None
        note = "沿用既有店铺关联；不代表本轮重新核验身份、菜单或当前营业。"
        if outlet and outlet != shop["id"]:
            note = "沿用已确认同店的规范窗口身份；保留原菜单组和原商品所属Shop ID，不重新核验菜单或当前营业。"
    if mode != "real":
        identity = mode
        note = "模拟菜单，仅供演示。" if mode == "simulated" else "推测或创作资料，不参与真实条件保证。"
    source = mode if mode != "real" else _source(item.get("source"))
    return dict(id=ident, poi_id=poi["id"], name=name,
                floor=_floor(shop.get("floor") if shop.get("floor") not in (None, "") else poi.get("floor")), outlet_id=outlet,
                identity_status=identity, category=_category(poi, shop), meal_role="unknown", source=source,
                evidence_summary=dict(source=source, photo_labels=[], observed_at=None, note=note))


def build_menu_relations(catalog):
    """Return lossless menu membership without writes, IO, model calls or mutation.

    Every input Item, including simulated/historical/unknown ones, has exactly one
    membership. Consumers must use data_mode and operational status for visibility;
    existence in this archival projection is not a recommendation eligibility flag.
    Unknown evidence grouping never uses mutable titles. Invalid parent references
    fail closed rather than silently dropping Items. Empty shops do not gain menus.
    """
    pois, shops, items = (_index(catalog, kind) for kind in ("pois", "shops", "items"))
    groups, membership, issues, outlets = {}, {}, [], []
    # One conflicting item must not acquire a confirmed identity because another
    # item in its registered group happened to be processed first.
    conflicted_groups = set()
    for item in items.values():
        shop = shops.get(item.get("shop_id"))
        poi = pois.get(shop.get("poi_id")) if shop else None
        if not shop or not poi or _mode(item, shop, poi) != "real":
            continue
        rule = _known_rule(item, shop)
        if rule and any(_floor(row.get("floor")) not in ("", rule[1]) for row in (item, shop, poi)):
            conflicted_groups.add("menu-group-xinlequn-" + rule[0])
    for ident in sorted(items):
        item = items[ident]
        shop = shops.get(item.get("shop_id"))
        if shop is None or shop.get("poi_id") not in pois:
            raise ValueError("Menu item has no valid shop/POI parent")
        poi = pois[shop["poi_id"]]
        mode = _mode(item, shop, poi)
        canonical_outlet_id = _canonical_shop_id(shop, shops, poi) if mode == "real" and not _is_collection(shop) else None
        template = _group_for(item, shop, poi, mode, conflicted_groups, canonical_outlet_id)
        expected_floor = _FLOOR_PARENTS.get(shop["id"], (None, None))[1]
        if shop["id"] == _HUAINAN:
            expected_floor = "4"
        if expected_floor and any(_floor(row.get("floor")) not in ("", expected_floor) for row in (item, shop, poi)):
            issues.append(dict(code="MENU_FLOOR_EVIDENCE_CONFLICT", item_id=ident,
                               poi_id=poi["id"], note="现有楼层与菜单来源楼层不一致；保留原值，需人工确认。"))
        gid = template["id"]
        if gid not in groups:
            groups[gid] = dict(**template, data_mode=mode, simulation=mode == "simulated", item_ids=[], item_count=0, sources=[])
        group = groups[gid]
        if group["poi_id"] != poi["id"] or group["data_mode"] != mode:
            raise ValueError("Menu group identity conflict")
        group["item_ids"].append(ident)
        source = mode if mode != "real" else _source(item.get("source"))
        if source not in group["sources"]:
            group["sources"].append(source)
        membership[ident] = dict(group_id=gid, outlet_id=group["outlet_id"],
            identity_status=group["identity_status"], meal_role=_meal_role(item, group), data_mode=mode,
            meal_role_basis="explicit_field" if item.get("meal_role") in {"main", "drink", "snack", "side", "weight_based", "unknown"}
            else "item_type" if item.get("item_type") in {"side", "add_on", "weight_based", "by_weight", "drink", "dessert", "snack"}
            else "menu_label_rule")
    for group in groups.values():
        group["item_count"] = len(group["item_ids"])
        group["sources"].sort()
        group["evidence_summary"]["item_sources"] = list(group["sources"])
        if len(group["sources"]) > 1:
            group["source"] = "published"
        roles = {membership[ident]["meal_role"] for ident in group["item_ids"]}
        group["meal_role"] = next(iter(roles)) if len(roles) == 1 else "mixed"
        if (group["identity_status"] == "confirmed" and group["data_mode"] == "real"
                and group.get("source_collection_id") in _FLOOR_PARENTS
                and (group.get("outlet_id") or "").startswith("outlet-xinlequn-")):
            # A floor collection's hours describe the venue, not every window.
            # These are new read-model identities, never updates to existing Shops.
            outlets.append(dict(id=group["outlet_id"], name=group["name"],
                poi_id=group["poi_id"], floor=group["floor"],
                source_collection_id=group["source_collection_id"], menu_group_id=group["id"],
                identity_status="confirmed", source="user_confirmation", data_mode="real",
                name_status=group["name_status"], signboard_name_verified=False,
                identity_evidence=dict(group["identity_evidence"]),
                opening_hours=None, opening_hours_text=None, hours_label="尚未录入",
                hours_source=None, operational_status="unknown", current_sale_verified=False,
                category=group["category"], meal_role=group["meal_role"]))
        if group["identity_status"] in {"source_only", "candidate", "unassigned"}:
            issues.append(dict(code="WINDOW_IDENTITY_UNCONFIRMED", group_id=group["id"],
                               poi_id=group["poi_id"], item_count=group["item_count"]))
    if "menu-collection-xinlequn-4" in shops and "canteen-4" in pois:
        issues.append(dict(code="WEIGHT_PRICING_NOT_FIXED_MEAL", poi_id="canteen-4",
                           photo_labels=["472", "475"], item_count=0,
                           note="称重菜单需按单位整理，未创建固定整餐或商户。"))
    return dict(menu_groups=sorted(groups.values(), key=lambda g: (g["poi_id"], g["data_mode"], g["id"])),
                outlets=sorted(outlets, key=lambda outlet: outlet["id"]),
                item_membership=membership, issues=sorted(issues, key=lambda r: (r["code"], r.get("group_id", ""), r.get("item_id", ""))))
