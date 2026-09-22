import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))

import vibe_core  # noqa: E402


class WorkflowRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / ".vibe").mkdir()
        self.configure([[sys.executable, "-c", "print('checked')"]])
        (self.root / "a.py").write_text("import b\n", encoding="utf-8")
        (self.root / "b.py").write_text("value = 1\n", encoding="utf-8")

    def configure(self, commands):
        (self.root / ".vibe/config.json").write_text(
            json.dumps({"verification": {"commands": commands}}), encoding="utf-8",
        )

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "runtime/vibe.py"), "--root", str(self.root), *args],
            capture_output=True, text=True, check=False,
        )

    def read_artifact(self, name):
        return json.loads((self.root / ".vibe/runtime" / name).read_text(encoding="utf-8"))

    def test_summary_keeps_full_graph_on_disk_and_output_bounded(self):
        for number in range(60):
            (self.root / ("extra_{}.py".format(number))).write_text("import a\n", encoding="utf-8")
        result = self.cli("deps", "--summary")
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        graph = self.read_artifact("dependency-map.json")
        self.assertEqual(summary["node_count"], 62)
        self.assertEqual(summary["edge_count"], 61)
        self.assertEqual(summary["cycle_count"], 0)
        self.assertEqual(summary["artifact"], ".vibe/runtime/dependency-map.json")
        self.assertLess(len(result.stdout), 1000)
        self.assertNotIn("extra_0.py", result.stdout)
        self.assertEqual(len(graph["nodes"]), 62)
        self.assertIn({"from": "extra_0.py", "to": "a.py"}, graph["edges"])

    def test_context_summary_and_quiet_still_materialize_artifacts(self):
        result = self.cli("context", "--summary")
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["source_file_count"], 2)
        self.assertEqual(summary["artifact"], ".vibe/runtime/project-map.json")
        (self.root / "c.py").write_text("value = 3\n", encoding="utf-8")
        result = self.cli("context", "--quiet")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.read_artifact("project-map.json")["source_file_count"], 3)
        result = self.cli("deps", "--quiet")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn("c.py", self.read_artifact("dependency-map.json")["nodes"])

    def test_default_output_remains_full_and_modes_are_exclusive(self):
        result = self.cli("deps")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), self.read_artifact("dependency-map.json"))
        result = self.cli("deps", "--summary", "--quiet")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")

    def test_verify_output_modes_preserve_status_exit_code_and_evidence(self):
        cases = [
            ([[sys.executable, "-c", "print('checked')"]], "PASS_VERIFIED", 0, 0),
            ([[sys.executable, "-c", "raise SystemExit(7)"]], "FAIL_VERIFICATION", 1, 1),
            ([], "NEEDS_VERIFICATION_CONFIG", 3, 0),
        ]
        for commands, status, exit_code, failures in cases:
            for mode in ("--summary", "--quiet"):
                with self.subTest(status=status, mode=mode):
                    self.configure(commands)
                    result = self.cli("verify", mode)
                    self.assertEqual(result.returncode, exit_code, result.stderr)
                    report = self.read_artifact("verification.json")
                    self.assertEqual(report["status"], status)
                    self.assertEqual(len(report["command_results"]), len(commands))
                    if mode == "--quiet":
                        self.assertEqual(result.stdout, "")
                    else:
                        summary = json.loads(result.stdout)
                        self.assertEqual(summary["status"], status)
                        self.assertEqual(summary["failed_command_count"], failures)
                        self.assertFalse(summary["dependency_comparison_available"])
                        self.assertNotIn("command_results", summary)

    def test_resuming_plan_preserves_task_and_original_baseline(self):
        task = vibe_core.start_task(self.root, "feature", "add b dependency")
        before = vibe_core.snapshot_dependencies(self.root, "before")
        baseline_path = self.root / task["path"] / "dependency-before.json"
        original_bytes = baseline_path.read_bytes()
        (self.root / "b.py").write_text("import a\n", encoding="utf-8")

        result = self.cli("deps", "--summary")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.cli("snapshot", "before")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(vibe_core.current_task(self.root)["id"], task["id"])
        self.assertEqual(baseline_path.read_bytes(), original_bytes)
        self.assertEqual(before["cycles"], [])
        result = self.cli("verify", "--summary")
        self.assertEqual(result.returncode, 1, result.stderr)
        summary = json.loads(result.stdout)
        self.assertTrue(summary["dependency_comparison_available"])
        self.assertEqual(summary["new_cycle_count"], 1)
        report = self.read_artifact("verification.json")
        self.assertEqual(report["new_cycles"], [["a.py", "b.py"]])
        self.assertEqual(report["status"], "FAIL_VERIFICATION")

    def test_snapshot_after_refreshes_graph_without_separate_deps_call(self):
        vibe_core.start_task(self.root, "feature", "add cycle")
        vibe_core.snapshot_dependencies(self.root, "before")
        (self.root / "b.py").write_text("import a\n", encoding="utf-8")
        after = vibe_core.snapshot_dependencies(self.root, "after")
        self.assertEqual(after["cycles"], [["a.py", "b.py"]])
        self.assertEqual(vibe_core.dependency_diff(self.root)["new_cycles"], [["a.py", "b.py"]])

    def test_missing_baseline_is_not_replaced_with_an_empty_graph(self):
        task = vibe_core.start_task(self.root, "feature", "late verification")
        with self.assertRaisesRegex(RuntimeError, "baseline"):
            vibe_core.snapshot_dependencies(self.root, "after")
        with self.assertRaisesRegex(RuntimeError, "baseline"):
            vibe_core.dependency_diff(self.root)
        self.assertFalse((self.root / task["path"] / "dependency-before.json").exists())
        self.assertFalse((self.root / task["path"] / "dependency-after.json").exists())
        result = self.cli("verify", "--summary")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["dependency_comparison_available"])

    def test_invalid_baseline_is_preserved_and_reported(self):
        task = vibe_core.start_task(self.root, "feature", "invalid baseline")
        baseline_path = self.root / task["path"] / "dependency-before.json"
        baseline_path.write_text("{broken", encoding="utf-8")
        for when in ("before", "after"):
            with self.subTest(when=when):
                with self.assertRaisesRegex(RuntimeError, "baseline"):
                    vibe_core.snapshot_dependencies(self.root, when)
        self.assertEqual(baseline_path.read_text(encoding="utf-8"), "{broken")
        self.assertFalse((self.root / task["path"] / "dependency-after.json").exists())
        result = self.cli("verify", "--quiet")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("baseline", result.stderr)


if __name__ == "__main__":
    unittest.main()
