"""Building content is identity-bound and cannot mutate operational facts."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from backend.campus_content import SEED_PATH, area_descriptions, enrich_buildings


def fixture():
    return {
        "version": "test-v1",
        "sources": {"official": {
            "title": "学校公开介绍", "url": "https://news.bnu.edu.cn/example.htm",
            "retrieved_at": "2026-10-08", "published_at": None,
            "private_path": "never copied", "token": "never copied",
        }},
        "buildings": [{"building_id": "1", "identity_name": "图书馆",
                       "description": "文献阅读空间。", "content_origin": "official_public_source",
                       "source_ids": ["official"], "function_tags": ["library"],
                       "height": 999, "opening_hours": "bad injected value"}],
        "areas": [{"id": "reading", "name": "阅读区", "description": "阅读空间分组。",
                   "content_origin": "official_public_source", "source_ids": ["official"],
                   "geometry": {"coordinates": [1, 2]}, "private_path": "not public"}],
    }


class CampusContentTests(unittest.TestCase):
    def test_exact_id_and_name_required(self):
        records = [{"id": "1", "name": "图书馆"}, {"id": "2", "name": "图书馆"},
                   {"id": "1", "name": "其他图书馆"}]
        output = enrich_buildings(records, fixture())
        self.assertEqual(output[0]["description_status"], "official_summary")
        self.assertEqual(output[1]["review_state"], "identity_pending")
        self.assertEqual(output[2]["review_state"], "identity_mismatch")
        self.assertEqual(output[2]["source_links"], [])

    def test_no_mutation_no_geometry_hours_or_name_overwrite(self):
        records = [{"osm_id": 1, "name": "图书馆", "height": 12, "floors": 3,
                    "coords": [[4, 5]], "opening_hours": None, "shops": ["x"]}]
        original, document = deepcopy(records), fixture()
        before_document = deepcopy(document)
        output = enrich_buildings(records, document)
        self.assertEqual(records, original)
        self.assertEqual(document, before_document)
        for key, value in original[0].items():
            self.assertEqual(output[0][key], value)
        output[0]["coords"][0][0] = 999
        self.assertEqual(records[0]["coords"], [[4, 5]])

    def test_conflicting_ids_do_not_match(self):
        output = enrich_buildings([{"id": "1", "osm_id": "2", "name": "图书馆"}], fixture())[0]
        self.assertEqual(output["review_state"], "identity_mismatch")

    def test_existing_description_wins(self):
        original = {"id": "1", "name": "图书馆", "description": "人工修订的介绍。",
                    "content_origin": "field_observation", "source_links": [{"title": "现场"}]}
        output = enrich_buildings([original], fixture())[0]
        for key, value in original.items():
            self.assertEqual(output[key], value)
        self.assertEqual(output["review_state"], "existing_description_preserved")

    def test_deliberately_cleared_description_wins(self):
        for flags in ({"field_evidence": {"description": {"source": "manual"}}},
                      {"description_manually_edited": True}):
            row = {"id": "1", "name": "图书馆", "description": "", **flags}
            self.assertEqual(enrich_buildings([row], fixture())[0]["description"], "")

    def test_only_known_generated_placeholder_may_be_replaced(self):
        row = {"id": "1", "name": "图书馆", "description_status": "仅有基础名录，详细介绍待补充",
               "description": "图书馆的建筑位置。选择美食、饮品等分类可查看已关联的店铺。"}
        self.assertEqual(enrich_buildings([row], fixture())[0]["description"], "文献阅读空间。")
        row["description"] = "即使旧状态未更新，也必须保留这段人工修改。"
        self.assertEqual(enrich_buildings([row], fixture())[0]["description"], row["description"])

    def test_unknown_model_part_is_not_invented(self):
        row = enrich_buildings([{"osm_id": 88, "name": None}], fixture())[0]
        self.assertIsNone(row["name"])
        self.assertEqual(row["review_state"], "unnamed_model_part")
        self.assertEqual(row["source_links"], [])
        self.assertEqual(row["function_tags"], [])

    def test_inference_is_visible_even_if_seed_omits_prefix(self):
        doc = fixture()
        doc["buildings"][0].update(content_origin="inferred", description="可能用于阅读。")
        row = enrich_buildings([{"id": "1", "name": "图书馆"}], doc)[0]
        self.assertTrue(row["description"].startswith("推测："))
        self.assertEqual(row["description_status"], "inferred")
        self.assertEqual(row["review_state"], "inference_pending")

    def test_sources_have_safe_explicit_fields_and_unknown_date(self):
        row = enrich_buildings([{"id": "1", "name": "图书馆"}], fixture())[0]
        source = row["source_links"][0]
        self.assertIsNone(source["published_at"])
        self.assertNotIn("private_path", source)
        self.assertNotIn("token", source)
        self.assertEqual(set(source), {"title", "url", "published_at", "retrieved_at", "temporal_note"})

    def test_unsafe_or_non_university_links_do_not_certify_claim(self):
        for url in ("file:///C:/private/photo.jpg", "https://bnu.edu.cn.evil.test/info",
                    "https://user:secret@bnu.edu.cn/info", "javascript:alert(1)",
                    "https://example.org/info", "https://bnu.edu.cn:bad/info"):
            with self.subTest(url=url):
                doc = fixture()
                doc["sources"]["official"]["url"] = url
                row = enrich_buildings([{"id": "1", "name": "图书馆"}], doc)[0]
                self.assertEqual(row["review_state"], "source_pending")
                self.assertEqual(row["source_links"], [])
                self.assertNotIn("文献阅读空间", row["description"])

    def test_idempotent_enrichment(self):
        first = enrich_buildings([{"id": "1", "name": "图书馆"}], fixture())
        self.assertEqual(enrich_buildings(first, fixture()), first)

    def test_edit_to_an_enriched_description_is_not_overwritten(self):
        first = enrich_buildings([{"id": "1", "name": "图书馆"}], fixture())
        first[0]["description"] = "人工在已补充记录上继续修订。"
        self.assertEqual(enrich_buildings(first, fixture())[0]["description"], first[0]["description"])

    def test_areas_are_content_not_geometry(self):
        area = area_descriptions(fixture())[0]
        self.assertIsNone(area["geometry"])
        self.assertEqual(area["area_type"], "narrative_area")
        self.assertIn("不是测绘边界", area["content_scope"])
        self.assertNotIn("private_path", area)

    def test_duplicate_ids_are_rejected(self):
        doc = fixture()
        doc["buildings"].append(deepcopy(doc["buildings"][0]))
        with self.assertRaises(ValueError):
            enrich_buildings([], doc)

    def test_checked_in_seed_covers_every_named_model_id(self):
        root = Path(__file__).resolve().parents[1]
        raw = json.loads((root / "assets/campus_assets_white_v6.json").read_text(encoding="utf-8"))["buildings"]
        doc = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        expected = {(str(row["osm_id"]), row["name"]) for row in raw if row.get("name")}
        actual = {(row["building_id"], row["identity_name"]) for row in doc["buildings"]}
        self.assertEqual(expected, actual)
        self.assertEqual(len(actual), 83)
        output = enrich_buildings(raw)
        self.assertEqual(len(output), 234)
        for before, after in zip(raw, output):
            for key in ("osm_id", "name", "height", "floors", "coords"):
                self.assertEqual(before.get(key), after.get(key))
            self.assertTrue(after["description"])
            self.assertTrue(after["review_state"])
            if after["content_origin"] == "official_public_source":
                self.assertTrue(after["source_links"])
            if after["content_origin"] == "inferred":
                self.assertTrue(after["description"].startswith("推测："))
        self.assertEqual(len(area_descriptions()), 7)

    def test_second_batch_official_summaries_have_direct_sources_and_boundaries(self):
        document = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        names = {
            "267946192": "乐育1楼", "267944900": "乐育2楼", "267944902": "乐育4楼",
            "499427391": "生态学研究所", "1388502966": "南航空厨",
        }
        records = [dict(id=ident, name=name) for ident, name in names.items()]
        output = enrich_buildings(records, document)
        self.assertEqual(len(output), 5)
        for row in output:
            self.assertEqual(row["content_origin"], "official_public_source")
            self.assertEqual(row["description_status"], "official_summary")
            self.assertTrue(row["content_limitations"])
            self.assertTrue(row["source_links"])
            self.assertNotIn("opening_hours", row)
            self.assertNotIn("location", row)
            self.assertNotIn("geometry", row)
            for source in row["source_links"]:
                self.assertEqual(source["retrieved_at"], "2026-10-08")
                self.assertIn("published_at", source)
                self.assertTrue(source["temporal_note"])
        indexed = {row["id"]: row for row in output}
        self.assertIn("2021年", indexed["267944900"]["description"])
        self.assertIn("历史", indexed["267944900"]["description"])
        self.assertIn("2025年", indexed["267946192"]["description"])
        self.assertIsNone(indexed["267944902"]["source_links"][0]["published_at"])
        self.assertIn("不代表当前状态", " ".join(indexed["1388502966"]["content_limitations"]))

    def test_second_batch_does_not_promote_unresolved_building_names(self):
        names = {
            "179358288": "北楼", "657006466": "B教学楼", "1327982493": "B教学楼",
            "267946199": "乐育3楼", "267944897": "乐育9楼", "1459447295": "工程实践中心",
        }
        output = enrich_buildings([dict(id=ident, name=name) for ident, name in names.items()])
        self.assertTrue(all(row["content_origin"] != "official_public_source" for row in output))


if __name__ == "__main__":
    unittest.main()
