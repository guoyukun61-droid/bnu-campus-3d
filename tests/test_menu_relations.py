"""Isolated menu relation checks: no private store, model or migration is used."""
import copy
import json
import unittest

from backend.menu_relations import build_menu_relations, _PHOTO_HASHES


def catalog(items, floor="3"):
    pid, sid = "canteen-" + floor, "menu-collection-xinlequn-" + floor
    return dict(pois=[dict(id=pid, name="测试楼层", category="canteen", floor=floor, source="published")],
                shops=[dict(id=sid, poi_id=pid, name="测试楼层集合", floor=floor, source="menu_photo",
                            entity_type="floor_menu_collection", independent_merchant=False)],
                items=[dict(id="item-" + str(n), shop_id=sid, source="menu_photo", name=name,
                            source_photo_sha256=_PHOTO_HASHES[photo], menu_section="原转录标题")
                       for n, (photo, name) in enumerate(items)])


class MenuRelationsTests(unittest.TestCase):
    def test_known_third_floor_eight_groups_and_exact_membership(self):
        data = catalog([(p, "测试饭") for p in ("458", "459", "460", "461", "462", "463", "464", "466")])
        before = copy.deepcopy(data)
        result = build_menu_relations(data)
        self.assertEqual(data, before)
        self.assertEqual(len(result["menu_groups"]), 8)
        self.assertEqual(set(result["item_membership"]), {i["id"] for i in data["items"]})
        self.assertEqual(len(result["outlets"]), 8)
        self.assertEqual({g["outlet_id"] for g in result["menu_groups"]}, {o["id"] for o in result["outlets"]})
        self.assertTrue(all(g["identity_status"] == "confirmed" for g in result["menu_groups"]))
        self.assertEqual(next(g for g in result["menu_groups"] if g["id"].endswith("3-005"))["outlet_id"], "outlet-xinlequn-3-005")

    def test_fourth_floor_shared_pages_and_huainan(self):
        data = catalog([(p, "测试饭") for p in ("471", "472", "473", "474", "477", "478", "479", "480", "481", "482", "484", "485", "486", "487")], "4")
        data["shops"].append(dict(id="shop-huainan-xinlequn-4", poi_id="canteen-4", name="淮南牛肉汤", source="menu_photo"))
        data["items"].append(dict(id="huainan-side", shop_id="shop-huainan-xinlequn-4", name="单买饼", item_type="side", source="menu_photo"))
        result = build_menu_relations(data)
        self.assertEqual(len(result["menu_groups"]), 13)
        self.assertEqual(len(result["outlets"]), 12)
        self.assertNotIn("shop-huainan-xinlequn-4", {o["id"] for o in result["outlets"]})
        self.assertEqual(result["item_membership"]["item-4"]["group_id"], result["item_membership"]["item-5"]["group_id"])
        self.assertEqual(result["item_membership"]["item-6"]["group_id"], result["item_membership"]["item-7"]["group_id"])
        self.assertNotEqual(result["item_membership"]["item-2"]["group_id"], result["item_membership"]["item-3"]["group_id"])
        huainan = result["item_membership"]["huainan-side"]
        self.assertEqual(huainan["outlet_id"], "shop-huainan-xinlequn-4")
        self.assertEqual(huainan["identity_status"], "confirmed")
        self.assertEqual(huainan["meal_role"], "side")
        self.assertIn("WEIGHT_PRICING_NOT_FIXED_MEAL", {i["code"] for i in result["issues"]})

    def test_registered_ids_ignore_names_prices_paths_and_input_order(self):
        data = catalog([("477", "同名面"), ("478", "同名面")], "4")
        before = build_menu_relations(data)
        data["items"].reverse()
        for item in data["items"]:
            item.update(name="重新校正名称", menu_section="完全改变标题", price=99,
                        source_file="C:/private/new-file.jpg", field_evidence={"secret": "PRIVATE"})
        after = build_menu_relations(data)
        for ident in before["item_membership"]:
            for key in ("group_id", "outlet_id", "identity_status", "data_mode"):
                self.assertEqual(before["item_membership"][ident][key], after["item_membership"][ident][key])
        self.assertEqual([g["id"] for g in before["menu_groups"]], [g["id"] for g in after["menu_groups"]])
        self.assertNotIn("private", json.dumps(after))
        self.assertNotIn("PRIVATE", json.dumps(after))

    def test_simulated_and_inferred_items_do_not_join_real_group(self):
        data = catalog([("462", "手撕鸡饭"), ("462", "手撕鸡饭"), ("462", "手撕鸡饭")])
        data["items"][1]["source"] = "simulated"
        data["items"][2]["source"] = "inferred"
        result = build_menu_relations(data)
        self.assertEqual(len(result["menu_groups"]), 3)
        self.assertEqual({g["data_mode"] for g in result["menu_groups"]}, {"real", "simulated", "inferred"})
        self.assertEqual(len(result["outlets"]), 1)
        self.assertEqual(result["outlets"][0]["id"], "outlet-xinlequn-3-005")
        self.assertTrue(all(g["outlet_id"] is None for g in result["menu_groups"] if g["data_mode"] != "real"))

    def test_simulated_parent_makes_child_simulated(self):
        data = catalog([("462", "手撕鸡饭")])
        data["pois"][0]["source"] = "simulated"
        group = build_menu_relations(data)["menu_groups"][0]
        self.assertTrue(group["simulation"])
        self.assertEqual(group["identity_status"], "simulated")

    def test_source_and_content_origin_inherit_from_every_source_level(self):
        for field in ("source", "content_origin"):
            for table in ("items", "shops", "pois"):
                for origin in ("simulated", "inferred", "illustrative", "generated"):
                    with self.subTest(field=field, table=table, origin=origin):
                        data = catalog([("462", "手撕鸡饭")])
                        data[table][0][field] = origin
                        before = copy.deepcopy(data)
                        result = build_menu_relations(data)
                        group = result["menu_groups"][0]
                        expected = "simulated" if origin == "simulated" else "inferred"
                        self.assertEqual(group["data_mode"], expected)
                        self.assertEqual(group["identity_status"], expected)
                        self.assertEqual(result["item_membership"]["item-0"]["data_mode"], expected)
                        self.assertIsNone(group["outlet_id"])
                        self.assertEqual(result["outlets"], [])
                        self.assertNotEqual(group["id"], "menu-group-xinlequn-3-005")
                        self.assertEqual(data, before)

    def test_simulated_origin_takes_precedence_over_inferred_source(self):
        data = catalog([("462", "手撕鸡饭")])
        data["items"][0]["source"] = "inferred"
        data["pois"][0]["content_origin"] = "simulated"
        group = build_menu_relations(data)["menu_groups"][0]
        self.assertTrue(group["simulation"])
        self.assertEqual(group["source"], "simulated")

    def test_official_and_unknown_sources_are_not_relabelled_published(self):
        for source, expected in (("official_menu", "official_menu"), ("unknown", "unknown"),
                                 (None, "unknown"), ("unrecognised-private-source", "unknown"),
                                 ("published", "published")):
            with self.subTest(source=source):
                data = dict(pois=[dict(id="p", name="商户", source="published")],
                            shops=[dict(id="s", poi_id="p", name="商户", source="published")],
                            items=[dict(id="i", shop_id="s", name="米饭", source=source)])
                group = build_menu_relations(data)["menu_groups"][0]
                self.assertEqual(group["source"], expected)
                self.assertEqual(group["sources"], [expected])
                self.assertEqual(group["evidence_summary"]["source"], expected)

    def test_unknown_evidence_uses_stable_evidence_not_label(self):
        data = catalog([("458", "面"), ("459", "饭")])
        for item in data["items"]:
            item["source_photo_sha256"] = "unknown-stable-evidence"
        first = build_menu_relations(data)
        self.assertEqual(len(first["menu_groups"]), 1)
        for item in data["items"]:
            item["menu_section"] = "改名后"
        self.assertEqual(first["item_membership"], build_menu_relations(data)["item_membership"])

    def test_no_evidence_does_not_merge_same_name_items(self):
        data = catalog([("458", "同名面"), ("459", "同名面")])
        for item in data["items"]:
            item.pop("source_photo_sha256")
        result = build_menu_relations(data)
        self.assertEqual(len(result["menu_groups"]), 2)
        self.assertEqual({g["identity_status"] for g in result["menu_groups"]}, {"unassigned"})

    def test_photo_identity_never_moves_item_across_floor(self):
        data = catalog([("462", "饭")], "4")
        group = build_menu_relations(data)["menu_groups"][0]
        self.assertEqual(group["poi_id"], "canteen-4")
        self.assertTrue(group["id"].startswith("menu-group-unresolved-"))

    def test_manual_floor_change_is_not_replaced_by_registered_floor(self):
        data = catalog([("462", "饭")])
        data["shops"][0]["floor"] = "2"
        result = build_menu_relations(data)
        group = result["menu_groups"][0]
        self.assertEqual(group["floor"], "2")
        self.assertEqual(group["id"], "menu-group-xinlequn-3-005")
        self.assertEqual(group["identity_status"], "source_only")
        self.assertIsNone(group["outlet_id"])
        self.assertFalse(group["identity_evidence"]["applied"])
        self.assertEqual(result["outlets"], [])
        self.assertIn("MENU_FLOOR_EVIDENCE_CONFLICT", {i["code"] for i in result["issues"]})

    def test_adjacent_dumpling_screen_is_not_xiaogu_menu(self):
        group = build_menu_relations(catalog([("472", "牛肉水饺")], "4"))["menu_groups"][0]
        self.assertTrue(group["name"].startswith("水饺菜单"))
        self.assertEqual(group["outlet_id"], "outlet-xinlequn-4-002")
        self.assertEqual(group["identity_status"], "confirmed")

    def test_item_floor_conflict_prevents_confirmation_of_whole_registered_group(self):
        data = catalog([("462", "鸡汤饭"), ("462", "手撕鸡饭")])
        data["items"][1]["floor"] = "4"
        before = copy.deepcopy(data)
        result = build_menu_relations(data)
        self.assertEqual(result["outlets"], [])
        self.assertEqual(result["menu_groups"][0]["identity_status"], "source_only")
        self.assertTrue(all(m["outlet_id"] is None for m in result["item_membership"].values()))
        self.assertIn("MENU_FLOOR_EVIDENCE_CONFLICT", {i["code"] for i in result["issues"]})
        data["items"].reverse()
        self.assertEqual(build_menu_relations(data), result)
        data["items"].reverse()
        self.assertEqual(data, before)

    def test_dessert_drink_side_and_meal_do_not_inherit_canteen_role(self):
        data = catalog([("471", "芒果布丁"), ("471", "招牌奶茶"), ("487", "香酥鸡柳"), ("487", "香辣鸡腿堡套餐")], "4")
        member = build_menu_relations(data)["item_membership"]
        self.assertEqual([member["item-" + str(i)]["meal_role"] for i in range(4)], ["snack", "drink", "snack", "main"])

    def test_generic_shop_preserves_existing_relation_and_unrelated_fields(self):
        data = dict(pois=[dict(id="p", name="商户", category="retail", source="published")],
                    shops=[dict(id="s", poi_id="p", name="原店名", source="published")],
                    items=[dict(id="i", shop_id="s", name="不明商品", source="field_observation", available=False)])
        group = build_menu_relations(data)["menu_groups"][0]
        self.assertEqual(group["outlet_id"], "s")
        self.assertEqual(group["identity_status"], "existing_shop")
        self.assertEqual(group["meal_role"], "unknown")
        data["shops"][0]["name"] = "新店名"
        self.assertEqual(group["id"], build_menu_relations(data)["menu_groups"][0]["id"])
        self.assertFalse(data["items"][0]["available"])

    def test_same_brand_different_existing_shops_stay_separate(self):
        data = dict(pois=[dict(id="p", name="楼", source="published")],
                    shops=[dict(id=s, poi_id="p", name="同名店", source="published") for s in ("s1", "s2")],
                    items=[dict(id="i" + s, shop_id=s, name="同名菜", source="field_observation") for s in ("s1", "s2")])
        self.assertEqual(len(build_menu_relations(data)["menu_groups"]), 2)

    def test_no_private_source_path_in_fallback(self):
        data = catalog([("458", "面")])
        data["items"][0].update(source_photo_sha256="opaque", menu_section="C:/private/photos", source_file="C:/private/photos/anything.jpg")
        result = build_menu_relations(data)
        self.assertEqual(result["menu_groups"][0]["name"], "本层待归属菜单")
        self.assertNotIn("private", json.dumps(result))

    def test_original_filename_without_original_hash_is_not_identity_proof(self):
        data = catalog([("462", "同名饭")])
        data["items"][0].update(source_photo_sha256="different-image", source_file="微信图片_20260929141354_462_44.jpg")
        group = build_menu_relations(data)["menu_groups"][0]
        self.assertTrue(group["id"].startswith("menu-group-unresolved-"))
        self.assertEqual(group["identity_status"], "source_only")

    def test_existing_shop_mixed_sources_and_integer_floor_are_preserved(self):
        data = dict(pois=[dict(id="p", name="商户", category="restaurant", source="published")],
                    shops=[dict(id="s", poi_id="p", name="原店名", source="published", floor=2)],
                    items=[dict(id="a", shop_id="s", name="面", source="menu_photo"),
                           dict(id="b", shop_id="s", name="饭", source="field_observation")])
        group = build_menu_relations(data)["menu_groups"][0]
        self.assertEqual(group["floor"], "2")
        self.assertEqual(group["source"], "published")
        self.assertEqual(group["evidence_summary"]["item_sources"], ["field_observation", "menu_photo"])

    def test_stable_evidence_id_without_photo_keeps_one_source_group(self):
        data = catalog([("458", "面"), ("459", "饭")])
        for item in data["items"]:
            item.pop("source_photo_sha256")
            item["source_evidence_id"] = "persisted-evidence-001"
        self.assertEqual(len(build_menu_relations(data)["menu_groups"]), 1)

    def test_historical_items_remain_archival_and_do_not_claim_availability(self):
        data = catalog([("462", "饭")])
        data["items"][0].update(status="historical", available=False)
        result = build_menu_relations(data)
        self.assertEqual(set(result["item_membership"]), {"item-0"})
        self.assertNotIn("recommendable", result["menu_groups"][0])
        self.assertNotIn("available", result["menu_groups"][0])

    def test_orphans_and_duplicate_item_ids_fail_closed(self):
        data = catalog([("458", "面")])
        data["items"][0]["shop_id"] = "missing"
        with self.assertRaises(ValueError):
            build_menu_relations(data)
        data = catalog([("458", "面")])
        data["items"].append(copy.deepcopy(data["items"][0]))
        with self.assertRaises(ValueError):
            build_menu_relations(data)

    def test_empty_catalog_and_empty_shop_do_not_fabricate_menu(self):
        self.assertEqual(build_menu_relations({}), dict(menu_groups=[], outlets=[], item_membership={}, issues=[]))
        self.assertEqual(build_menu_relations(catalog([]))["menu_groups"], [])

    def test_all_twenty_confirmed_outlets_keep_source_item_and_shop_ids(self):
        third = catalog([(p, "测试饭") for p in ("458", "459", "460", "461", "462", "463", "464", "466")])
        fourth = catalog([(p, "测试饭") for p in ("471", "472", "473", "474", "477", "478", "479", "480", "481", "482", "484", "485", "486", "487")], "4")
        for item in fourth["items"]:
            item["id"] = "fourth-" + item["id"]
        data = {kind: third[kind] + fourth[kind] for kind in ("pois", "shops", "items")}
        before = copy.deepcopy(data)
        result = build_menu_relations(data)
        self.assertEqual(data, before)
        self.assertEqual(len(result["menu_groups"]), 20)
        self.assertEqual(len(result["outlets"]), 20)
        self.assertEqual(len({o["id"] for o in result["outlets"]}), 20)
        self.assertEqual(sum(o["floor"] == "3" for o in result["outlets"]), 8)
        self.assertEqual(sum(o["floor"] == "4" for o in result["outlets"]), 12)
        self.assertEqual(set(result["item_membership"]), {i["id"] for i in data["items"]})
        self.assertEqual({i["shop_id"] for i in data["items"]}, {s["id"] for s in data["shops"]})
        self.assertTrue(all(m["identity_status"] == "confirmed" for m in result["item_membership"].values()))
        self.assertNotIn("WINDOW_IDENTITY_UNCONFIRMED", {i["code"] for i in result["issues"]})

    def test_confirmed_identity_never_inherits_collection_or_venue_hours(self):
        data = catalog([("471", "招牌奶茶")], "4")
        for row in (data["pois"][0], data["shops"][0]):
            row.update(opening_hours=[["06:00", "22:00"]], opening_hours_text="06:00-22:00")
        before = copy.deepcopy(data)
        result = build_menu_relations(data)
        outlet = result["outlets"][0]
        self.assertEqual(outlet["identity_status"], "confirmed")
        self.assertEqual(outlet["source_collection_id"], "menu-collection-xinlequn-4")
        self.assertEqual(outlet["menu_group_id"], "menu-group-xinlequn-4-001")
        self.assertIsNone(outlet["opening_hours"])
        self.assertIsNone(outlet["opening_hours_text"])
        self.assertEqual(outlet["hours_label"], "尚未录入")
        self.assertEqual(outlet["operational_status"], "unknown")
        self.assertFalse(outlet["current_sale_verified"])
        self.assertFalse(outlet["signboard_name_verified"])
        self.assertIn("窗口名称待核", outlet["name"])
        self.assertEqual(outlet["identity_evidence"]["source"], "user_confirmation")
        self.assertEqual(outlet["identity_evidence"]["confirmed_at"], "2026-10-08")
        self.assertIsNone(outlet["identity_evidence"]["observed_at"])
        self.assertEqual(data, before)

    def test_confirmation_does_not_replace_existing_shop_hours_or_duplicate_huainan(self):
        data = dict(pois=[dict(id="canteen-4", name="学四", floor="4", source="published")],
                    shops=[dict(id="shop-huainan-xinlequn-4", poi_id="canteen-4", name="淮南牛肉汤", source="menu_photo",
                                opening_hours=[["10:00", "20:00"]], opening_hours_text="人工原时段")],
                    items=[dict(id="huainan", shop_id="shop-huainan-xinlequn-4", name="牛肉汤", source="menu_photo")])
        before = copy.deepcopy(data)
        result = build_menu_relations(data)
        self.assertEqual(result["outlets"], [])
        self.assertEqual(result["item_membership"]["huainan"]["outlet_id"], "shop-huainan-xinlequn-4")
        self.assertEqual(data, before)

    def test_canonical_shop_preserves_old_group_and_item_ids(self):
        data = dict(pois=[dict(id="laixifu", name="来喜福", source="published")],
                    shops=[dict(id="old-shop", poi_id="laixifu", name="原百度店名", source="published"),
                           dict(id="shop-laixifu", poi_id="laixifu", name="来喜福", source="published")],
                    items=[dict(id="old-item", shop_id="old-shop", name="酸奶", source="field_observation"),
                           dict(id="canonical-item", shop_id="shop-laixifu", name="鸡蛋仔", source="field_observation")])
        first = build_menu_relations(data)
        data["shops"][0].update(canonical_shop_id="shop-laixifu", source_poi_id="old-poi")
        before = copy.deepcopy(data)
        result = build_menu_relations(data)
        self.assertEqual(data, before)
        self.assertEqual(len(result["menu_groups"]), 2)
        self.assertEqual(result["item_membership"]["old-item"]["group_id"], first["item_membership"]["old-item"]["group_id"])
        self.assertEqual({m["outlet_id"] for m in result["item_membership"].values()}, {"shop-laixifu"})
        self.assertEqual(data["items"][0]["shop_id"], "old-shop")
        self.assertEqual(result["outlets"], [])

    def test_canonical_shop_valid_chain_resolves_final_existing_outlet(self):
        data = dict(pois=[dict(id="p", name="同店", source="published")],
                    shops=[dict(id="s1", poi_id="p", name="旧1", canonical_shop_id="s2"),
                           dict(id="s2", poi_id="p", name="旧2", canonical_shop_id="s3"),
                           dict(id="s3", poi_id="p", name="规范店")],
                    items=[dict(id="i", shop_id="s1", name="饭", source="field_observation")])
        self.assertEqual(build_menu_relations(data)["item_membership"]["i"]["outlet_id"], "s3")

    def test_canonical_shop_invalid_missing_cyclic_other_venue_and_mode_fail_closed(self):
        def make():
            return dict(pois=[dict(id="p", name="店", source="published"), dict(id="other", name="另一场所", source="published")],
                        shops=[dict(id="s1", poi_id="p", name="旧店", source="published", canonical_shop_id="s2"),
                               dict(id="s2", poi_id="p", name="规范店", source="published")],
                        items=[dict(id="i", shop_id="s1", name="饭", source="field_observation")])
        for target in ("missing", "", [], 42, "s1"):
            with self.subTest(target=target):
                data = make(); data["shops"][0]["canonical_shop_id"] = target
                with self.assertRaises(ValueError):
                    build_menu_relations(data)
        for patch in (dict(canonical_shop_id="s1"), dict(poi_id="other"),
                      dict(source="simulated"), dict(content_origin="inferred"),
                      dict(entity_type="floor_menu_collection"), dict(independent_merchant=False)):
            with self.subTest(patch=patch):
                data = make(); data["shops"][1].update(patch)
                with self.assertRaises(ValueError):
                    build_menu_relations(data)

    def test_simulated_or_inferred_alias_items_never_join_real_outlet(self):
        for mode in ("simulated", "inferred"):
            with self.subTest(mode=mode):
                data = dict(pois=[dict(id="p", name="店", source="published")],
                            shops=[dict(id="old", poi_id="p", name="旧店", source="published", canonical_shop_id="canonical"),
                                   dict(id="canonical", poi_id="p", name="规范店", source="published")],
                            items=[dict(id="i", shop_id="old", name="演示饭", source=mode)])
                result = build_menu_relations(data)
                self.assertIsNone(result["item_membership"]["i"]["outlet_id"])
                self.assertEqual(result["item_membership"]["i"]["data_mode"], mode)


if __name__ == "__main__":
    unittest.main()
