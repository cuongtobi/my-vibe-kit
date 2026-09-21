import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))

import vibe_core  # noqa: E402


class VibeCoreTests(unittest.TestCase):
    def make_repo(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        (root / ".vibe").mkdir(parents=True)
        (root / ".vibe" / "config.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "context": {"max_dependency_depth": 3, "max_files": 1000},
                    "dependency": {"fail_on_new_cycles": True},
                    "verification": {"require_commands": True, "commands": []},
                    "tasks": {"keep_history": True},
                }
            ),
            encoding="utf-8",
        )
        return temp, root

    def test_python_dependency_graph_and_reverse_impact(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        pkg = root / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "a.py").write_text("from pkg.b import value\n", encoding="utf-8")
        (pkg / "b.py").write_text("value = 1\n", encoding="utf-8")
        tests = root / "tests"
        tests.mkdir()
        (tests / "test_a.py").write_text("from pkg.a import value\n", encoding="utf-8")

        vibe_core.project_context(root)
        graph = vibe_core.dependency_graph(root)

        edges = {(item["from"], item["to"]) for item in graph["edges"]}
        self.assertIn(("pkg/a.py", "pkg/b.py"), edges)
        self.assertIn(("tests/test_a.py", "pkg/a.py"), edges)

        impact = vibe_core.impact_analysis(root, ["pkg/b.py"])
        self.assertIn("pkg/a.py", impact["affected_reverse_dependencies"])
        self.assertIn("tests/test_a.py", impact["affected_tests"])

    def test_package_init_relative_import_is_resolved(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        pkg = root / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("from .a import value\n", encoding="utf-8")
        (pkg / "a.py").write_text("value = 1\n", encoding="utf-8")

        graph = vibe_core.dependency_graph(root)
        edges = {(item["from"], item["to"]) for item in graph["edges"]}
        self.assertIn(("pkg/__init__.py", "pkg/a.py"), edges)

    def test_new_cycle_is_detected_in_dependency_diff(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        pkg = root / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "a.py").write_text("from pkg.b import value\n", encoding="utf-8")
        (pkg / "b.py").write_text("value = 1\n", encoding="utf-8")

        vibe_core.start_task(root, "refactor", "introduce cycle for test")
        vibe_core.dependency_graph(root)
        vibe_core.snapshot_dependencies(root, "before")

        (pkg / "b.py").write_text("from pkg.a import value\nvalue = 1\n", encoding="utf-8")
        vibe_core.dependency_graph(root)
        vibe_core.snapshot_dependencies(root, "after")

        diff = vibe_core.dependency_diff(root)
        self.assertEqual(len(diff["new_cycles"]), 1)
        self.assertEqual(set(diff["new_cycles"][0]), {"pkg/a.py", "pkg/b.py"})

    def test_verify_requires_configured_commands_by_default(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)

        report = vibe_core.verify(root)
        self.assertEqual(report["status"], "NEEDS_VERIFICATION_CONFIG")
        self.assertEqual(report["commands_run"], 0)

    def test_verify_passes_only_after_real_command_runs(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)

        config = json.loads((root / ".vibe" / "config.json").read_text(encoding="utf-8"))
        config["verification"]["commands"] = [
            [sys.executable, "-c", "print('verification-ok')"]
        ]
        (root / ".vibe" / "config.json").write_text(
            json.dumps(config), encoding="utf-8"
        )

        report = vibe_core.verify(root)
        self.assertEqual(report["status"], "PASS_VERIFIED")
        self.assertEqual(report["commands_run"], 1)
        self.assertEqual(report["command_results"][0]["returncode"], 0)


if __name__ == "__main__":
    unittest.main()
