"""Isolated exports; notebook cells use sequential Python exec, not a Jupyter kernel."""
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from backend.catalog_exports import export_snapshot
from backend.life_relations import PROJECTION_VERSION, fingerprint


def small_snapshot(item_names=None):
    names = item_names if item_names is not None else ["番茄炒蛋", "演示小面"]
    items = [{"ref": {"kind": "item", "id": f"item-{i}"}, "name": name,
              "poi_id": "canteen-3", "group_id": "menu-1", "outlet_id": None,
              "price": 8.5 if i == 0 else None, "price_unit": "元/份",
              "source": {"kind": "fixture", "note": "隔离测试"},
              "is_simulated": i != 0, "availability": "unknown"}
             for i, name in enumerate(names)]
    ids = [x["ref"]["id"] for x in items]
    return {
        "snapshot_id": "fixture-1.20.0-data.1",
        "summary": {"source_counts": {"pois": 1, "shops": 1, "items": len(items), "buildings": 1}},
        "entities": [{"ref": {"kind": "building", "id": "b1"}, "name": "样例楼",
                      "description": "仅供隔离测试。", "content_origin": "inferred",
                      "description_status": "inferred", "review_state": "inference_pending",
                      "source_links": []},
                     {"ref": {"kind": "poi", "id": "canteen-3"}, "name": "三层入口"},
                     *items],
        "relations": [{"type": "contains", "from": {"kind": "building", "id": "b1"},
                       "to": {"kind": "poi", "id": "canteen-3"}}],
        "menu_groups": [{"id": "menu-1", "poi_id": "canteen-3", "name": "菜单组|待核",
                         "identity_status": "menu_collection", "item_ids": ids}],
        "item_membership": {item_id: "menu-1" for item_id in ids},
        "roster": {
            "summary": {"present_count": 1, "expected_roster_count": 1,
                        "displayable_count": 0, "without_display_point_count": 1},
            "rows": [{"id": "poi-1", "name": "样例店", "roster_name": "名录店名",
                      "group": "fixture", "order": 1, "present": True,
                      "category": "food", "floor": "3", "building_id": "b1",
                      "has_display_point": False, "location_mode": "unknown",
                      "operational_status": "unknown"}],
        },
        "issues": [{"code": "window_identity_pending", "item_id": "item-0"}],
    }


@contextmanager
def working_directory(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def run_notebook_cells(directory):
    """Run saved code cells in order with one namespace, using only fixture files."""
    notebook = json.loads((directory / "inspect.ipynb").read_text(encoding="utf-8"))
    namespace, output = {"__name__": "__notebook_test__"}, io.StringIO()
    with working_directory(directory), redirect_stdout(output):
        for index, cell in enumerate(notebook["cells"]):
            if cell["cell_type"] == "code":
                code = "".join(cell["source"])
                exec(compile(code, f"inspect.ipynb:cell-{index + 1}", "exec"), namespace)
    return namespace, output.getvalue()


class CatalogExportTests(unittest.TestCase):
    def test_export_roundtrip_manifest_and_input_immutability(self):
        snapshot, input_hashes = small_snapshot(), {"fixture.json": "a" * 64}
        original = deepcopy(snapshot)
        with tempfile.TemporaryDirectory() as temporary:
            output = export_snapshot(snapshot, temporary, "test-20261008", input_hashes)
            self.assertEqual(output, Path(temporary).resolve() / "test-20261008")
            reopened = json.loads((output / "snapshot.json").read_text(encoding="utf-8"))
            self.assertEqual(reopened, snapshot)
            self.assertEqual(fingerprint(reopened), fingerprint(snapshot))
            self.assertEqual(snapshot, original)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["run_id"], "test-20261008")
            self.assertEqual(manifest["snapshot_id"], snapshot["snapshot_id"])
            self.assertEqual(manifest["projection_version"], PROJECTION_VERSION)
            self.assertEqual(manifest["input_hashes"], input_hashes)
            self.assertIs(manifest["source_mutated"], False)
            self.assertEqual(set(manifest["files"]), {p.name for p in output.iterdir()} - {"manifest.json"})
            for name, expected_hash in manifest["files"].items():
                with self.subTest(name=name):
                    self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), expected_hash)
            self.assertEqual(json.loads((output / "items.json").read_text(encoding="utf-8")),
                             [x for x in snapshot["entities"] if x["ref"]["kind"] == "item"])
            self.assertEqual(json.loads((output / "relations.json").read_text(encoding="utf-8")), snapshot["relations"])
            self.assertEqual(json.loads((output / "review-issues.json").read_text(encoding="utf-8")), snapshot["issues"])

    def test_existing_run_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = export_snapshot(small_snapshot(), temporary, "same-run")
            before = {p.name: p.read_bytes() for p in output.iterdir()}
            changed = small_snapshot(["不应覆盖"])
            with self.assertRaises(FileExistsError):
                export_snapshot(changed, temporary, "same-run")
            after = {p.name: p.read_bytes() for p in output.iterdir()}
            self.assertEqual(after, before)
            self.assertEqual([p.name for p in Path(temporary).iterdir()], ["same-run"])

    def test_new_run_keeps_previous_run_intact(self):
        with tempfile.TemporaryDirectory() as temporary:
            first = export_snapshot(small_snapshot(), temporary, "run-1")
            old_bytes = (first / "snapshot.json").read_bytes()
            second = export_snapshot(small_snapshot(["第二版"]), temporary, "run-2")
            self.assertEqual((first / "snapshot.json").read_bytes(), old_bytes)
            self.assertNotEqual((second / "snapshot.json").read_bytes(), old_bytes)

    def test_run_id_cannot_escape_or_create_arbitrary_paths(self):
        invalid_ids = ["", ".", "..", "../escape", "..\\escape", "a/child", "a\\child",
                       "/absolute", "C:\\temp\\escape", "C:escape", "run..name", "x" * 102,
                       " run", "run\n", "run:stream", "run%2Fchild"]
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary) / "exports"
            base.mkdir()
            sentinel = Path(temporary) / "keep.txt"
            sentinel.write_text("unchanged", encoding="utf-8")
            for run_id in invalid_ids:
                with self.subTest(run_id=repr(run_id)), self.assertRaises(ValueError):
                    export_snapshot(small_snapshot(), base, run_id)
            self.assertEqual(list(base.iterdir()), [])
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "unchanged")
            self.assertEqual({p.name for p in Path(temporary).iterdir()}, {"exports", "keep.txt"})

    def test_csv_formula_values_are_neutralized_without_changing_snapshot(self):
        dangerous = ["=1+1", "+SUM(1,2)", "-2+3", "@SUM(A1)", "\t=1", "\r=1", "\n=1"]
        names = dangerous + ["普通菜单", "含逗号,和换行\n的说明"]
        snapshot = small_snapshot(names)
        snapshot["roster"]["rows"][0]["name"] = "=ROSTER()"
        snapshot["entities"][0]["description"] = "@BUILDING"
        with tempfile.TemporaryDirectory() as temporary:
            output = export_snapshot(snapshot, temporary, "csv-fixture")
            with (output / "menus.csv").open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([r["name"] for r in rows], ["'" + s for s in dangerous] + names[len(dangerous):])
            self.assertEqual(rows[0]["price"], "8.5")
            self.assertEqual(rows[1]["price"], "")
            self.assertEqual(json.loads(rows[0]["source"]), {"kind": "fixture", "note": "隔离测试"})
            with (output / "shops-roster.csv").open(encoding="utf-8-sig", newline="") as stream:
                self.assertEqual(next(csv.DictReader(stream))["name"], "'=ROSTER()")
            with (output / "buildings.csv").open(encoding="utf-8-sig", newline="") as stream:
                self.assertEqual(next(csv.DictReader(stream))["description"], "'@BUILDING")
            self.assertTrue((output / "menus.csv").read_bytes().startswith(b"\xef\xbb\xbf"))
            saved = json.loads((output / "snapshot.json").read_text(encoding="utf-8"))
            self.assertEqual([e["name"] for e in saved["entities"] if e["ref"]["kind"] == "item"], names)

    def test_notebook_structure_and_sequential_python_cells(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = export_snapshot(small_snapshot(), temporary, "notebook-fixture")
            notebook = json.loads((output / "inspect.ipynb").read_text(encoding="utf-8"))
            self.assertEqual((notebook["nbformat"], notebook["nbformat_minor"]), (4, 5))
            self.assertEqual(notebook["metadata"]["data_snapshot_id"], "fixture-1.20.0-data.1")
            self.assertEqual(notebook["metadata"]["kernelspec"]["language"], "python")
            cells = notebook["cells"]
            self.assertEqual(len({c["id"] for c in cells}), len(cells))
            for cell in cells:
                self.assertIsInstance(cell["metadata"], dict)
                self.assertIsInstance(cell["source"], list)
                self.assertTrue(all(isinstance(line, str) for line in cell["source"]))
                if cell["cell_type"] == "code":
                    self.assertIsNone(cell["execution_count"])
                    self.assertEqual(cell["outputs"], [])
            self.assertGreaterEqual(sum(c["cell_type"] == "code" for c in cells), 3)
            namespace, report = run_notebook_cells(output)
            self.assertEqual(namespace["snapshot"]["snapshot_id"], "fixture-1.20.0-data.1")
            self.assertEqual(len(namespace["items"]), 2)
            self.assertIn("Item IDs preserved: 2", report)
            self.assertIn("window_identity_pending", report)
            # Execution is deliberately in-memory; saved notebook remains unexecuted.
            self.assertEqual(json.loads((output / "inspect.ipynb").read_text(encoding="utf-8")), notebook)

    def test_notebook_detects_missing_membership(self):
        snapshot = small_snapshot()
        snapshot["item_membership"].pop("item-1")
        with tempfile.TemporaryDirectory() as temporary:
            output = export_snapshot(snapshot, temporary, "bad-membership-fixture")
            with self.assertRaises(AssertionError):
                run_notebook_cells(output)

    def test_network_exports_are_consistent_and_companion_rechecks_edges(self):
        from tests.test_life_relations import project
        snapshot = project()
        with tempfile.TemporaryDirectory() as temporary:
            output = export_snapshot(snapshot, temporary, 'network-fixture')
            network = json.loads((output / 'network.json').read_text(encoding='utf-8'))
            self.assertEqual(network, snapshot['network'])
            with (output / 'network-edges.csv').open(encoding='utf-8-sig', newline='') as stream:
                edges = list(csv.DictReader(stream))
            self.assertEqual({e['id'] for e in edges}, {e['id'] for e in network['edges']})
            self.assertTrue((output / 'network-examples.json').exists())
            namespace, report = run_notebook_cells(output)
            self.assertEqual(namespace['network']['summary']['edge_count'], len(edges))
            self.assertIn('Network:', report)


if __name__ == "__main__":
    unittest.main()
