import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))

import vibe_core  # noqa: E402
import vibe_retrieval  # noqa: E402
import vibe_stacks  # noqa: E402
import vibe_tasks  # noqa: E402


class RetrievalAndLifecycleTests(unittest.TestCase):
    def git(self, root, *args):
        return subprocess.run(
            ["git"] + list(args),
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

    def init_git(self, root):
        self.assertEqual(self.git(root, "init").returncode, 0)
        self.assertEqual(self.git(root, "config", "user.email", "vibe@example.com").returncode, 0)
        self.assertEqual(self.git(root, "config", "user.name", "Vibe Test").returncode, 0)
        self.assertEqual(self.git(root, "add", ".").returncode, 0)
        result = self.git(root, "commit", "-m", "baseline")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def make_repo(self, retrieval=None):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        (root / ".vibe").mkdir(parents=True)
        context = {
            "max_dependency_depth": 2,
            "max_files": 1000,
            "max_source_files": 20,
            "max_test_files": 10,
            "max_related_modules": 8,
        }
        if retrieval is not None:
            context["retrieval"] = retrieval
        (root / ".vibe/config.json").write_text(
            json.dumps(
                {
                    "version": 3,
                    "context": context,
                    "dependency": {"fail_on_new_cycles": True},
                    "verification": {"require_commands": True, "commands": []},
                    "tasks": {
                        "auto_load_history": False,
                        "retention": {
                            "policy": "bounded",
                            "max_tasks": 100,
                            "max_age_days": 90,
                            "cleanup": "manual",
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        return temp, root

    def test_unicode_query_keeps_vietnamese_and_expands_common_code_terms(self):
        profile = vibe_retrieval.query_profile(
            "Sửa đăng nhập khi phiên hết hạn và làm mới mã thông báo"
        )

        self.assertIn("đăng", profile["tokens"])
        self.assertIn("dang", profile["tokens"])
        self.assertIn("login", profile["tokens"])
        self.assertIn("session", profile["tokens"])
        self.assertIn("expired", profile["tokens"])
        self.assertIn("refresh", profile["tokens"])
        self.assertIn("token", profile["tokens"])

    def test_vietnamese_task_finds_english_identifier_content(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        (root / "manager.py").write_text(
            "def refresh_access_token(session):\n"
            "    if session.expired:\n"
            "        return rotate_token(session)\n",
            encoding="utf-8",
        )
        (root / "billing.py").write_text(
            "def calculate_invoice(total):\n    return total\n",
            encoding="utf-8",
        )
        self.init_git(root)

        vibe_core.start_task(root, "bug_fix", "Sửa đăng nhập khi phiên hết hạn")
        data = vibe_core.relevant_context(root)

        self.assertIn("manager.py", data["targets"])
        self.assertIn(data["retrieval_confidence"], {"medium", "high"})
        self.assertIn("session", data["query_tokens"])
        self.assertFalse(data["needs_scoped_search"])

    def test_low_index_score_uses_controlled_content_fallback(self):
        temp, root = self.make_repo(
            {
                "min_index_score": 6,
                "fallback_max_scan_files": 1000,
                "fallback_read_bytes": 262144,
                "query_aliases": {},
            }
        )
        self.addCleanup(temp.cleanup)
        noisy = "\n".join("alpha{:03d} = {}".format(i, i) for i in range(260))
        (root / "worker.py").write_text(noisy + "\nzzzneedle = 1\n", encoding="utf-8")
        (root / "other.py").write_text("ordinary_value = 1\n", encoding="utf-8")
        self.init_git(root)

        vibe_core.start_task(root, "change", "update zzzneedle behavior")
        data = vibe_core.relevant_context(root)

        self.assertTrue(data["fallback"]["used"])
        self.assertEqual(data["retrieval_mode"], "fallback-content-scan")
        self.assertEqual(data["targets"][0], "worker.py")
        self.assertFalse(data["fallback"]["truncated"])

    def test_truncated_fallback_marks_scoped_search_required(self):
        temp, root = self.make_repo(
            {
                "min_index_score": 100,
                "fallback_max_scan_files": 1,
                "fallback_read_bytes": 4096,
                "query_aliases": {},
            }
        )
        self.addCleanup(temp.cleanup)
        (root / "a.py").write_text("alpha = 1\n", encoding="utf-8")
        (root / "z.py").write_text("hidden_needle = 1\n", encoding="utf-8")
        self.init_git(root)

        vibe_core.start_task(root, "change", "find completely_missing_term")
        data = vibe_core.relevant_context(root)

        self.assertTrue(data["fallback"]["used"])
        self.assertTrue(data["fallback"]["truncated"])
        self.assertTrue(data["needs_scoped_search"])
        self.assertEqual(data["retrieval_confidence"], "low")

    def test_task_aware_primary_language_prefers_framework_evidence(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        (root / "pyproject.toml").write_text(
            '[project]\ndependencies = ["fastapi"]\n',
            encoding="utf-8",
        )
        (root / "package.json").write_text(
            json.dumps({"dependencies": {"react": "^19.0.0"}}),
            encoding="utf-8",
        )
        (root / "tsconfig.json").write_text("{}", encoding="utf-8")
        stack = vibe_stacks.detect_stack(root)

        backend = vibe_stacks.task_aware_stack(stack, "Sửa API FastAPI đăng nhập")
        frontend = vibe_stacks.task_aware_stack(stack, "Fix React component rendering")

        self.assertEqual(backend["primary"], "python")
        self.assertEqual(frontend["primary"], "typescript")
        self.assertEqual(backend["repository_primary"], "typescript")
        self.assertEqual(backend["frameworks"][0], "fastapi")
        self.assertEqual(frontend["frameworks"][0], "react")
        self.assertEqual(frontend["repository_frameworks"][0], "fastapi")

    def test_framework_names_require_token_boundaries(self):
        stack = {
            "primary": "python",
            "languages": ["python", "go"],
            "frameworks": ["gin"],
        }
        view = vibe_stacks.task_aware_stack(stack, "fix login flow")
        self.assertEqual(view["primary"], "python")
        self.assertEqual(view["task_primary_reason"], "repository-primary-fallback")

    def test_invalid_explicit_target_is_low_confidence(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        (root / "actual.py").write_text("value = 1\n", encoding="utf-8")
        self.init_git(root)

        vibe_core.start_task(root, "change", "generic change")
        data = vibe_core.relevant_context(root, ["missing.py"])

        self.assertEqual(data["targets"], [])
        self.assertEqual(data["retrieval_confidence"], "low")
        self.assertTrue(data["needs_scoped_search"])

    def test_relevant_context_materializes_task_specific_adapter(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        (root / "pyproject.toml").write_text(
            '[project]\ndependencies = ["fastapi"]\n',
            encoding="utf-8",
        )
        (root / "package.json").write_text(
            json.dumps({"dependencies": {"react": "^19.0.0"}}),
            encoding="utf-8",
        )
        (root / "tsconfig.json").write_text("{}", encoding="utf-8")
        (root / "api.py").write_text(
            "def login_session():\n    return True\n",
            encoding="utf-8",
        )
        (root / "view.tsx").write_text(
            "export const View = () => null;\n",
            encoding="utf-8",
        )
        self.init_git(root)

        vibe_core.start_task(root, "bug_fix", "Sửa FastAPI login session")
        data = vibe_core.relevant_context(root, ["api.py"])
        adapter = json.loads(
            (root / ".vibe/runtime/active-adapter.json").read_text(encoding="utf-8")
        )

        self.assertEqual(data["task_primary_stack"]["task_primary"], "python")
        self.assertEqual(adapter["primary_language"]["id"], "python")

    def test_task_target_stack_survives_later_dependency_refresh(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        (root / "pyproject.toml").write_text(
            '[project]\ndependencies = ["fastapi"]\n',
            encoding="utf-8",
        )
        (root / "package.json").write_text(
            json.dumps({"dependencies": {"react": "^19.0.0"}}),
            encoding="utf-8",
        )
        (root / "tsconfig.json").write_text("{}", encoding="utf-8")
        (root / "api.py").write_text("def endpoint():\n    return True\n", encoding="utf-8")
        (root / "view.tsx").write_text("export const View = () => null;\n", encoding="utf-8")
        self.init_git(root)

        vibe_core.start_task(root, "bug_fix", "fix bug")
        vibe_core.relevant_context(root, ["api.py"])
        vibe_core.dependency_graph(root)
        adapter = json.loads(
            (root / ".vibe/runtime/active-adapter.json").read_text(encoding="utf-8")
        )

        self.assertEqual(adapter["primary_language"]["id"], "python")

    def test_task_gc_is_preview_first_and_never_deletes_current_task(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        first = vibe_tasks.start_task(root, "change", "first")
        second = vibe_tasks.start_task(root, "change", "second")
        current = vibe_tasks.start_task(root, "change", "current")

        old = (datetime.now(timezone.utc) - timedelta(days=120)).replace(microsecond=0).isoformat()
        for task in (first, second):
            path = root / task["path"] / "task.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["created_at"] = old
            path.write_text(json.dumps(data), encoding="utf-8")

        config = vibe_core.load_config(root)
        config["tasks"]["retention"].update({"max_tasks": 1, "max_age_days": 30})

        preview = vibe_tasks.task_lifecycle(root, config, apply=False)
        self.assertEqual(preview["candidate_count"], 2)
        self.assertEqual(vibe_core.status(root)["task_history"]["candidate_count"], 2)
        self.assertTrue((root / first["path"]).exists())
        self.assertTrue((root / second["path"]).exists())
        self.assertTrue((root / current["path"]).exists())

        applied = vibe_tasks.task_lifecycle(root, config, apply=True)
        self.assertEqual(applied["deleted_count"], 2)
        self.assertFalse((root / first["path"]).exists())
        self.assertFalse((root / second["path"]).exists())
        self.assertTrue((root / current["path"]).exists())


if __name__ == "__main__":
    unittest.main()
