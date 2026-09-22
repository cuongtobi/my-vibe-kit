import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
sys.path.insert(0, str(ROOT))

import install
import vibe_core as core
import vibe_state as state


class RuntimeRegressionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.write("a.py", "import b\n")
        self.write("b.py", "value = 1\n")
        self.configure()

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def configure(self, commands=None, **settings):
        settings["verification"] = {"commands": commands if commands is not None else [[sys.executable, "-c", "print('ok')"]]}
        self.write(".vibe/config.json", json.dumps(settings))

    def git(self, *args):
        result = subprocess.run(["git", *args], cwd=self.root, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def init_git(self):
        self.git("init")
        self.git("config", "user.name", "Vibe Test")
        self.git("config", "user.email", "vibe@example.com")
        self.git("config", "core.quotepath", "true")
        self.git("add", ".")
        self.git("commit", "-m", "baseline")

    def test_every_cache_artifact_is_validated_before_hit_and_incremental_refresh(self):
        self.init_git()
        for artifact in (name for name in state.CACHE_FILES if name != "hashes"):
            for dirty in (False, True):
                with self.subTest(artifact=artifact, dirty=dirty):
                    self.write("b.py", "value = 1\n")
                    core.dependency_graph(self.root, force=True)
                    # Alternate parse errors and valid JSON missing required data.
                    self.write(".vibe/state/" + state.CACHE_FILES[artifact], "{}" if dirty else "{broken")
                    if dirty:
                        self.write("b.py", "import a\n")
                    graph = core.dependency_graph(self.root)
                    self.assertEqual(graph["cache"]["mode"], "FULL_REBUILD")
                    self.assertEqual(graph["nodes"], ["a.py", "b.py"])
                    self.assertEqual(graph["cycles"], [["a.py", "b.py"]] if dirty else [])
                    self.assertEqual(core.project_context(self.root)["source_file_count"], 2)
                    self.assertEqual(core.dependency_graph(self.root)["cache"]["mode"], "CACHE_HIT")

    def test_corrupt_file_index_cannot_hide_cycle_during_verification(self):
        self.init_git()
        core.start_task(self.root, "bug_fix", "cache corruption")
        core.snapshot_dependencies(self.root, "before")
        self.write(".vibe/state/file-index.json", "{broken")
        self.write("b.py", "import a\n")
        report = core.verify(self.root)
        self.assertEqual(report["status"], "FAIL_VERIFICATION")
        self.assertEqual(report["new_cycles"], [["a.py", "b.py"]])

    def test_invalid_index_metadata_and_non_utf8_cache_rebuild(self):
        self.init_git()
        core.dependency_graph(self.root)
        index = state.load_index_state(self.root)
        index["artifacts"] = []
        self.write(".vibe/state/index-state.json", json.dumps(index))
        self.assertEqual(core.project_context(self.root)["cache"]["mode"], "FULL_REBUILD")
        (self.root / ".vibe/state/last-context.json").write_bytes(b"\xff")
        self.assertEqual(core.project_context(self.root)["source_file_count"], 2)

    def test_verification_fingerprint_reuses_content_hash_cache(self):
        for index in range(20):
            self.write("pkg/file_{:02d}.py".format(index), "value = {}\n".format(index))
        self.init_git()

        first = core.verification_fingerprint(self.root)
        self.assertTrue((self.root / ".vibe/state/content-hashes.json").exists())

        original = state._file_sha256
        with mock.patch("vibe_state._file_sha256", wraps=original) as hashed:
            second = core.verification_fingerprint(self.root)
            self.assertEqual(first, second)
            # Cache validation/config checks may hash a few control files, but not all sources again.
            self.assertLess(hashed.call_count, 10)

        self.write("pkg/file_07.py", "value = 700\n")
        with mock.patch("vibe_state._file_sha256", wraps=original) as hashed:
            third = core.verification_fingerprint(self.root)
            self.assertNotEqual(first, third)
            self.assertLess(hashed.call_count, 10)

    def test_unicode_paths_are_hashed_on_each_dirty_edit(self):
        self.write("a.py", "import té\n")
        self.write("té.py", "value = 1\n")
        self.init_git()
        core.dependency_graph(self.root)
        self.write("té.py", "import a\n")
        first = state.current_repo_state(self.root)
        self.assertIn("té.py", core.changed_files(self.root))
        record = next(item for item in first["dirty"] if item["path"] == "té.py")
        self.assertIsNotNone(record["sha256"])
        self.assertEqual(core.dependency_graph(self.root)["cycles"], [["a.py", "té.py"]])
        self.write("té.py", "value = 2\n")
        self.assertNotEqual(first["fingerprint"], state.current_repo_state(self.root)["fingerprint"])
        self.assertEqual(core.dependency_graph(self.root)["cycles"], [])

    def test_unicode_rename_in_worktree_and_committed_delta(self):
        self.write("a.py", "import té\nimport été\n")
        self.write("té.py", "value = 1\n")
        self.init_git()
        core.dependency_graph(self.root)
        self.git("mv", "té.py", "été.py")
        self.assertTrue({"té.py", "été.py"}.issubset(core.changed_files(self.root)))
        graph = core.dependency_graph(self.root)
        self.assertIn(("a.py", "été.py"), core.edge_set(graph))
        self.git("commit", "-m", "rename")
        core.dependency_graph(self.root)
        self.git("mv", "été.py", "té.py")
        self.git("commit", "-m", "rename back")
        graph = core.dependency_graph(self.root)
        self.assertEqual(graph["cache"]["mode"], "INCREMENTAL_REFRESH")
        self.assertIn(("a.py", "té.py"), core.edge_set(graph))
        self.assertNotIn("été.py", graph["nodes"])

    def test_nul_git_parsers_preserve_literal_path_characters(self):
        name = ' leading -> té\t\n".py '
        parsed = state._parse_status("?? " + name + "\0R  new.py\0" + name + "\0")
        self.assertEqual(parsed[0]["path"], name)
        self.assertEqual(parsed[1]["old_path"], name)
        self.assertEqual(state._parse_name_status("R100\0" + name + "\0new.py\0"), {name, "new.py"})

    def test_git_ignored_sources_are_excluded_but_tracked_ignored_sources_remain(self):
        self.write(".gitignore", "generated.py\ngenerated.js\n")
        self.write("a.py", "import generated\n")
        self.write("main.js", "import './generated.js';\n")
        self.write("generated.py", "value = 1\n")
        self.write("generated.js", "import './main.js';\n")
        self.init_git()
        graph = core.dependency_graph(self.root)
        self.assertNotIn("generated.py", graph["nodes"])
        self.assertNotIn("generated.js", graph["nodes"])
        self.assertEqual(graph["edges"], [])
        self.write("generated.py", "import a\n")
        self.assertEqual(core.dependency_graph(self.root)["cache"]["mode"], "CACHE_HIT")
        self.assertEqual(core.dependency_graph(self.root, force=True)["edges"], [])
        self.git("add", "-f", "generated.py")
        self.assertEqual(core.dependency_graph(self.root)["cycles"], [["a.py", "generated.py"]])

    def test_ignore_rule_changes_update_index_and_graph(self):
        self.write(".gitignore", "generated.py\n")
        self.write("a.py", "import generated\n")
        self.write("generated.py", "import a\n")
        self.init_git()
        core.dependency_graph(self.root)
        self.write(".gitignore", "")
        self.assertEqual(core.dependency_graph(self.root)["cycles"], [["a.py", "generated.py"]])
        self.write(".gitignore", "generated.py\n")
        self.assertNotIn("generated.py", core.dependency_graph(self.root)["nodes"])

    def test_verification_compares_graph_after_command_mutates_source(self):
        self.configure([[sys.executable, "-c", "from pathlib import Path; Path('b.py').write_text('import a\\n', encoding='utf-8')"]])
        core.start_task(self.root, "change", "command creates cycle")
        core.snapshot_dependencies(self.root, "before")
        report = core.verify(self.root)
        self.assertEqual(report["command_results"][0]["returncode"], 0)
        self.assertEqual(report["status"], "FAIL_VERIFICATION")
        self.assertEqual(report["new_cycles"], [["a.py", "b.py"]])
        self.assertTrue(report["rerun_required"])

    def test_mutating_commands_require_stable_rerun_and_evidence_is_bound_to_task(self):
        commands = [[sys.executable, "-c", "from pathlib import Path; Path('b.py').write_text('value = 2\\n', encoding='utf-8')"]]
        self.configure(commands)
        task = core.start_task(self.root, "change", "format")
        core.snapshot_dependencies(self.root, "before")
        report = core.verify(self.root)
        self.assertEqual(report["status"], "FAIL_VERIFICATION")
        self.assertEqual(report["rerun_commands"], commands)
        self.assertEqual(report["task_id"], task["id"])
        self.assertEqual(report["source_fingerprint"], core.verification_fingerprint(self.root))
        self.assertNotEqual(report["input_fingerprint_before"], report["source_fingerprint"])
        report = core.verify(self.root)
        self.assertEqual(report["status"], "PASS_VERIFIED")
        self.assertFalse(report["rerun_required"])
        self.write("b.py", "value = 3\n")
        self.assertNotEqual(report["source_fingerprint"], core.verification_fingerprint(self.root))

    def test_task_creation_cannot_reuse_baseline_with_same_timestamp_and_slug(self):
        with mock.patch.object(core, "datetime") as clock:
            clock.now.return_value = datetime(2026, 9, 22, tzinfo=timezone.utc)
            first = core.start_task(self.root, "change", "fix task!")
            core.snapshot_dependencies(self.root, "before")
            second = core.start_task(self.root, "change", "fix task?")
        self.assertNotEqual(first["id"], second["id"])
        self.assertFalse((self.root / second["path"] / "dependency-before.json").exists())
        self.assertEqual(core.json_load(self.root / first["path"] / "task.json")["request"], "fix task!")

    def test_status_distinguishes_stale_source_and_different_task_evidence(self):
        core.start_task(self.root, "change", "first")
        core.verify(self.root)
        self.assertTrue(core.status(self.root)["verification_current"])
        self.write("b.py", "value = 2\n")
        self.assertFalse(core.status(self.root)["verification_current"])
        core.verify(self.root)
        self.assertTrue(core.status(self.root)["verification_current"])
        core.start_task(self.root, "change", "second")
        self.assertFalse(core.status(self.root)["verification_current"])

    def test_commands_that_restore_initial_source_still_require_rerun(self):
        self.configure([
            [sys.executable, "-c", "from pathlib import Path; Path('b.py').write_text('value = 2\\n', encoding='utf-8')"],
            [sys.executable, "-c", "from pathlib import Path; Path('b.py').write_text('value = 1\\n', encoding='utf-8')"],
        ])
        report = core.verify(self.root)
        self.assertEqual(report["input_fingerprint_before"], report["source_fingerprint"])
        self.assertEqual(report["status"], "FAIL_VERIFICATION")
        self.assertTrue(report["rerun_required"])

    def test_ignored_runtime_configuration_changes_invalidate_cache(self):
        self.write(".gitignore", ".vibe/\n")
        self.init_git()
        core.dependency_graph(self.root)
        self.configure(context={"max_files": 1})
        context = core.project_context(self.root)
        self.assertEqual(context["cache"]["mode"], "FULL_REBUILD")
        self.assertLessEqual(context["source_file_count"], 1)

    def test_impact_refreshes_dependencies_and_new_tests(self):
        self.write("a.py", "value = 1\n")
        self.init_git()
        core.dependency_graph(self.root)
        self.write("a.py", "import b\n")
        self.write("test_a.py", "import a\n")
        impact = core.impact_analysis(self.root, ["b.py"])
        self.assertIn("a.py", impact["affected_reverse_dependencies"])
        self.assertIn("test_a.py", impact["affected_tests"])

    def test_deep_chain_and_large_cycle_do_not_use_python_recursion(self):
        nodes = [str(index) for index in range(2000)]
        edges = list(zip(nodes, nodes[1:]))
        self.assertEqual(core.strongly_connected_components(nodes, edges), [])
        edges.append((nodes[-1], nodes[0]))
        self.assertEqual(core.strongly_connected_components(nodes, edges), [sorted(nodes)])
        self.assertEqual(core.strongly_connected_components(
            ["a", "b", "c", "d", "e"], [("a", "b"), ("b", "a"), ("b", "c"), ("c", "d"), ("d", "c"), ("d", "e")],
        ), [["a", "b"], ["c", "d"]])

    def test_disabling_git_delta_rebuilds_after_edit_but_reuses_unchanged_cache(self):
        self.configure(index={"use_git_delta": False})
        self.init_git()
        core.dependency_graph(self.root)
        self.assertEqual(core.dependency_graph(self.root)["cache"]["mode"], "CACHE_HIT")
        self.write("b.py", "import a\n")
        graph = core.dependency_graph(self.root)
        self.assertEqual(graph["cache"]["mode"], "FULL_REBUILD")
        self.assertEqual(graph["cycles"], [["a.py", "b.py"]])

    def test_unsupported_history_opt_out_is_explicit_and_not_installed(self):
        self.assertNotIn("keep_history", install.default_config(self.root)["tasks"])
        self.configure(tasks={"keep_history": False})
        with self.assertRaisesRegex(RuntimeError, "keep_history=false is unsupported"):
            core.start_task(self.root, "change", "no history")
        self.assertFalse((self.root / ".vibe/tasks").exists())

    def test_run_process_resolves_executable_without_enabling_shell(self):
        with mock.patch.object(core.shutil, "which", return_value=sys.executable) as which:
            result = core.run_process(["project-python", "-c", "print('resolved')"], cwd=self.root)
        which.assert_called_once_with("project-python")
        self.assertEqual(result["returncode"], 0, result)
        self.assertEqual(result["stdout"].strip(), "resolved")

    @unittest.skipUnless(os.name == "nt", "Windows command shim resolution")
    def test_windows_cmd_shim_is_resolved_from_path(self):
        self.write("bin/test-runner.CMD", "@echo off\necho shim-ok\n")
        with mock.patch.dict(os.environ, {"PATH": str(self.root / "bin") + os.pathsep + os.environ["PATH"]}):
            result = core.run_process(["test-runner"], cwd=self.root)
        self.assertEqual(result["returncode"], 0, result)
        self.assertIn("shim-ok", result["stdout"])


class InstallerRegressionTests(unittest.TestCase):
    def test_bundle_dry_run_neither_creates_nor_overwrites_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skills/vibe"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("skill", encoding="utf-8")
            with mock.patch.object(install, "ROOT", root), mock.patch.object(sys, "argv", ["install.py", "--bundle-claude", "--dry-run", "--force"]):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(install.main(), 0)
                self.assertIn("would-bundle", output.getvalue())
                self.assertFalse((root / "dist").exists())
                archive = root / "dist/claude-skills/vibe.zip"
                archive.parent.mkdir(parents=True)
                archive.write_bytes(b"existing")
                install.bundle_claude(force=True, dry_run=True)
                self.assertEqual(archive.read_bytes(), b"existing")

    def test_install_manifest_conflict_requires_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install.install_project(root, ["codex"], dry_run=False, force=False)
            manifest = root / ".vibe/install-manifest.json"
            custom = '{"kit_version":"user-custom"}'
            manifest.write_text(custom, encoding="utf-8")
            events = install.install_project(root, ["codex"], dry_run=False, force=False)
            self.assertEqual(manifest.read_text(encoding="utf-8"), custom)
            self.assertIn({"path": str(manifest), "status": "conflict"}, events)
            install.install_project(root, ["codex"], dry_run=False, force=True)
            self.assertEqual(json.loads(manifest.read_text(encoding="utf-8"))["kit_version"], install.VERSION)

    def test_copy_and_bundle_exclude_bytecode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "skills/vibe"
            (source / "__pycache__").mkdir(parents=True)
            for name in ("SKILL.md", "helper.py", "helper.pyc", "helper.pyo", "__pycache__/helper.pyc"):
                (source / name).write_text("fixture", encoding="utf-8")
            events = []
            target = root / "target"
            install.copy_tree_safe(source, target, dry_run=False, force=False, events=events)
            self.assertEqual(sorted(path.name for path in target.iterdir()), ["SKILL.md", "helper.py"])
            with mock.patch.object(install, "ROOT", root):
                archives = install.bundle_claude()
            with install.zipfile.ZipFile(archives[0]) as archive:
                self.assertEqual(sorted(archive.namelist()), ["SKILL.md", "helper.py"])


if __name__ == "__main__":
    unittest.main()
