import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
sys.path.insert(0, str(ROOT / "benchmarks"))

import benchmark_runtime  # noqa: E402
import vibe_architecture  # noqa: E402
import vibe_core  # noqa: E402
import vibe_workflow  # noqa: E402
from vibe_contracts import ContractError  # noqa: E402


class CompletionContractTests(unittest.TestCase):
    def make_repo(self, request="add value"):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        (root / ".vibe").mkdir()
        (root / ".vibe/config.json").write_text(
            json.dumps(
                {
                    "version": 3,
                    "verification": {
                        "require_commands": True,
                        "commands": [[sys.executable, "-c", "print('checked')"]],
                    },
                }
            ),
            encoding="utf-8",
        )
        (root / "a.py").write_text("value = 1\n", encoding="utf-8")
        self.git(root, "init")
        self.git(root, "config", "user.email", "vibe@example.com")
        self.git(root, "config", "user.name", "Vibe Test")
        self.git(root, "add", ".")
        self.git(root, "commit", "-m", "baseline")
        task = vibe_core.start_task(root, "change", request)
        return temp, root, task

    def git(self, root, *args):
        proc = subprocess.run(
            ["git"] + list(args),
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def acceptance(self):
        return {
            "criteria": [
                {
                    "id": "AC1",
                    "expected": "Requested behavior is verified.",
                    "evidence": ["unit test"],
                    "result": "met",
                }
            ]
        }

    def non_sensitive_security(self, **extra):
        data = {
            "classification": "not-security-sensitive",
            "surfaces": [],
            "trust_boundaries": [],
            "abuse_cases": [],
            "controls_reviewed": [],
            "targeted_checks": [],
            "diff_review": {"status": "not-applicable", "evidence": []},
            "scanner": {"status": "not-applicable", "reason": "Task is not security-sensitive."},
            "dependency_vulnerability": {"status": "not-applicable", "reason": "No dependency change or dependency-sensitive surface."},
            "limitations": [],
        }
        data.update(extra)
        return data

    def test_legacy_current_task_is_migrated_without_losing_identity(self):
        temp, root, task = self.make_repo()
        self.addCleanup(temp.cleanup)
        current_path = root / ".vibe/runtime/current-task.json"
        legacy = dict(task)
        legacy.pop("artifact_type")
        legacy.pop("schema_version")
        current_path.write_text(json.dumps(legacy), encoding="utf-8")
        task_json = root / task["path"] / "task.json"
        task_json.write_text(json.dumps(legacy), encoding="utf-8")

        migrated = vibe_core.current_task(root)

        self.assertEqual(migrated["id"], task["id"])
        self.assertEqual(migrated["artifact_type"], "task")
        self.assertEqual(migrated["schema_version"], 1)
        self.assertEqual(
            json.loads(task_json.read_text(encoding="utf-8"))["schema_version"],
            1,
        )

    def test_runtime_artifacts_are_versioned_and_config_rejects_unknown_version(self):
        temp, root, _ = self.make_repo()
        self.addCleanup(temp.cleanup)

        context = vibe_core.project_context(root)
        graph = vibe_core.dependency_graph(root)
        relevant = vibe_core.relevant_context(root, ["a.py"])

        self.assertEqual(context["artifact_type"], "project-map")
        self.assertEqual(context["schema_version"], 1)
        self.assertEqual(graph["artifact_type"], "dependency-map")
        self.assertEqual(relevant["artifact_type"], "relevant-context")
        self.assertEqual(relevant["schema_version"], 1)

        (root / ".vibe/config.json").write_text(
            json.dumps({"version": 99, "verification": {"commands": []}}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ContractError, "Unsupported config version"):
            vibe_core.load_config(root)

    def test_completion_requires_acceptance_and_security_evidence(self):
        temp, root, task = self.make_repo()
        self.addCleanup(temp.cleanup)

        report = vibe_core.verify(root)
        self.assertEqual(report["status"], "PASS_VERIFIED")
        incomplete = vibe_core.workflow_completion(root)
        self.assertEqual(incomplete["status"], "INCOMPLETE_ACCEPTANCE")

        vibe_workflow.record_evidence(root, "acceptance", self.acceptance())
        vibe_workflow.record_evidence(root, "security", self.non_sensitive_security())
        complete = vibe_core.workflow_completion(root)

        self.assertEqual(complete["status"], "COMPLETE")
        self.assertTrue(complete["runtime_verification_ok"])
        self.assertTrue(complete["acceptance_ok"])
        self.assertTrue(complete["security_ok"])
        self.assertEqual(complete["task_id"], task["id"])

    def test_security_candidate_requires_override_rationale_for_non_sensitive_decision(self):
        temp, root, _ = self.make_repo("fix refresh token when session expires")
        self.addCleanup(temp.cleanup)

        vibe_core.verify(root)
        candidates = vibe_core.security_assessment(root)
        self.assertIn("session-token", candidates["surfaces"])
        vibe_workflow.record_evidence(root, "acceptance", self.acceptance())
        vibe_workflow.record_evidence(root, "security", self.non_sensitive_security())

        blocked = vibe_core.workflow_completion(root)
        self.assertEqual(blocked["status"], "INCOMPLETE_SECURITY")

        vibe_workflow.record_evidence(
            root,
            "security",
            self.non_sensitive_security(
                candidate_override_reason="The task text is a synthetic classifier test; no token/session code is changed."
            ),
        )
        self.assertEqual(vibe_core.workflow_completion(root)["status"], "COMPLETE")

    def test_sensitive_security_requires_passed_targeted_check(self):
        temp, root, _ = self.make_repo("change login authorization")
        self.addCleanup(temp.cleanup)

        vibe_core.verify(root)
        vibe_workflow.record_evidence(root, "acceptance", self.acceptance())
        evidence = {
            "classification": "security-sensitive",
            "surfaces": ["authentication-authorization"],
            "trust_boundaries": ["unauthenticated request -> protected handler"],
            "abuse_cases": ["unauthorized caller reaches protected behavior"],
            "controls_reviewed": ["authorization guard remains before protected handler"],
            "targeted_checks": [],
            "diff_review": {"status": "passed", "evidence": ["reviewed final auth diff"]},
            "scanner": {"status": "not-available", "reason": "No project-native security scanner is configured."},
            "dependency_vulnerability": {"status": "not-applicable", "reason": "No dependency change or dependency-sensitive surface."},
            "limitations": ["No project-native security scanner is configured."],
        }
        vibe_workflow.record_evidence(root, "security", evidence)
        self.assertEqual(vibe_core.workflow_completion(root)["status"], "INCOMPLETE_SECURITY")

        evidence["targeted_checks"] = [
            {"description": "unauthorized request is rejected", "result": "passed", "evidence": "focused test"}
        ]
        vibe_workflow.record_evidence(root, "security", evidence)
        self.assertEqual(vibe_core.workflow_completion(root)["status"], "COMPLETE")

    def test_sensitive_security_requires_abuse_controls_and_diff_review(self):
        temp, root, _ = self.make_repo("change login authorization")
        self.addCleanup(temp.cleanup)

        vibe_core.verify(root)
        vibe_workflow.record_evidence(root, "acceptance", self.acceptance())
        evidence = {
            "classification": "security-sensitive",
            "surfaces": ["authentication-authorization"],
            "trust_boundaries": ["request -> protected handler"],
            "abuse_cases": [],
            "controls_reviewed": [],
            "targeted_checks": [
                {"description": "unauthorized request is rejected", "result": "passed", "evidence": "focused test"}
            ],
            "diff_review": {"status": "unverified", "evidence": []},
            "scanner": {"status": "not-configured", "reason": "No project-native security scanner is configured."},
            "dependency_vulnerability": {"status": "not-applicable", "reason": "No dependency change or dependency-sensitive surface."},
            "limitations": ["No project-native security scanner is configured."],
        }
        vibe_workflow.record_evidence(root, "security", evidence)
        self.assertEqual(vibe_core.workflow_completion(root)["status"], "INCOMPLETE_SECURITY")

        evidence["abuse_cases"] = ["authorization bypass"]
        evidence["controls_reviewed"] = ["route authorization guard"]
        evidence["diff_review"] = {"status": "passed", "evidence": ["reviewed final diff against trust boundary"]}
        vibe_workflow.record_evidence(root, "security", evidence)
        self.assertEqual(vibe_core.workflow_completion(root)["status"], "COMPLETE")

    def test_nested_config_types_fail_with_contract_errors(self):
        temp, root, _ = self.make_repo()
        self.addCleanup(temp.cleanup)
        invalid_configs = [
            {"version": 3, "context": {"retrieval": {"fallback_read_bytes": "large"}}},
            {"version": 3, "architecture": {"strict_thresholds": {"source_files": "many"}}},
            {"version": 3, "tasks": {"retention": {"max_tasks": -1}}},
            {"version": 3, "index": {"use_git_delta": "yes"}},
        ]
        for config in invalid_configs:
            with self.subTest(config=config):
                (root / ".vibe/config.json").write_text(json.dumps(config), encoding="utf-8")
                with self.assertRaises(ContractError):
                    vibe_core.load_config(root)

    def test_security_classifier_reads_changed_diff_beyond_content_window(self):
        temp, root, _ = self.make_repo("ordinary refactor")
        self.addCleanup(temp.cleanup)
        large = root / "large_component.ts"
        large.write_text(("const filler = 'x';\n" * 5000) + "const safe = true;\n", encoding="utf-8")
        self.git(root, "add", "large_component.ts")
        self.git(root, "commit", "-m", "large baseline")
        large.write_text(
            ("const filler = 'x';\n" * 5000)
            + "const safe = true;\n"
            + "element.innerHTML = userMarkup;\n",
            encoding="utf-8",
        )

        report = vibe_core.security_assessment(root, ["large_component.ts"], request="ordinary refactor")
        self.assertIn("html-rendering", report["surfaces"])
        self.assertIn("large_component.ts", report["files_truncated"])
        sources = [item["source"] for item in report["evidence"]["html-rendering"]]
        self.assertIn("diff", sources)

    def test_completion_rejects_evidence_from_previous_verified_source(self):
        temp, root, _ = self.make_repo()
        self.addCleanup(temp.cleanup)

        vibe_core.verify(root)
        vibe_workflow.record_evidence(root, "acceptance", self.acceptance())
        vibe_workflow.record_evidence(root, "security", self.non_sensitive_security())
        self.assertEqual(vibe_core.workflow_completion(root)["status"], "COMPLETE")

        (root / "a.py").write_text("value = 2\n", encoding="utf-8")
        vibe_core.verify(root)
        stale = vibe_core.workflow_completion(root)
        self.assertFalse(stale["acceptance_ok"])
        self.assertFalse(stale["security_ok"])
        self.assertIn("acceptance-evidence-incomplete", stale["blocking_reasons"])

        vibe_workflow.record_evidence(root, "acceptance", self.acceptance())
        vibe_workflow.record_evidence(root, "security", self.non_sensitive_security())
        self.assertEqual(vibe_core.workflow_completion(root)["status"], "COMPLETE")

    def test_task_artifact_path_cannot_escape_task_storage(self):
        temp, root, task = self.make_repo()
        self.addCleanup(temp.cleanup)
        malicious = dict(task)
        malicious["path"] = "../../outside-task"
        (root / ".vibe/runtime/current-task.json").write_text(
            json.dumps(malicious),
            encoding="utf-8",
        )

        self.assertIsNone(vibe_core.current_task(root))
        self.assertIsNone(vibe_core.current_task_path(root))

    def test_security_classifier_ignores_paths_outside_repository(self):
        temp, root, _ = self.make_repo("ordinary change")
        self.addCleanup(temp.cleanup)

        report = vibe_core.security_assessment(
            root,
            ["../secret-token.py", "../../credentials.py"],
            request="ordinary change",
        )

        self.assertEqual(report["files_considered"], [])
        self.assertEqual(report["surfaces"], [])

    def test_architecture_auto_strict_uses_task_module_scope(self):
        temp, root, _ = self.make_repo()
        self.addCleanup(temp.cleanup)

        paths = ["packages/big/file_{:03d}.py".format(index) for index in range(150)]
        paths += ["packages/small/a.py", "packages/small/b.py"]
        config = {
            "architecture": {
                "profile": "auto",
                "default_profile": "standard",
                "strict_pattern": "hexagonal",
                "allow_auto_strict": True,
                "strict_thresholds": {"source_files": 100, "feature_roots": 99},
            }
        }

        repository_policy = vibe_architecture.architecture_policy(root, config, source_paths=paths)
        task_policy = vibe_architecture.architecture_policy(
            root,
            config,
            source_paths=paths,
            target_files=["packages/small/a.py"],
        )

        self.assertEqual(repository_policy["effective_profile"], "strict")
        self.assertEqual(task_policy["effective_profile"], "standard")
        self.assertEqual(task_policy["architecture_scope"]["mode"], "task-modules")
        self.assertEqual(task_policy["architecture_scope"]["modules"], ["packages/small"])
        self.assertEqual(task_policy["project_size"]["source_files"], 152)
        self.assertEqual(task_policy["evaluation_size"]["source_files"], 2)

    def test_retrieval_diagnostics_explain_dependency_and_consumer_selection(self):
        temp, root, _ = self.make_repo("change a")
        self.addCleanup(temp.cleanup)
        (root / "a.py").write_text("import b\n", encoding="utf-8")
        (root / "b.py").write_text("value = 1\n", encoding="utf-8")
        (root / "c.py").write_text("import a\n", encoding="utf-8")

        relevant = vibe_core.relevant_context(root, ["a.py"])
        diagnostics = {item["path"]: item for item in relevant["selection_diagnostics"]}

        self.assertIn("target", diagnostics["a.py"]["roles"])
        self.assertIn("dependency", diagnostics["b.py"]["roles"])
        self.assertEqual(diagnostics["b.py"]["dependency"]["depth"], 1)
        self.assertEqual(diagnostics["b.py"]["dependency"]["via"], "a.py")
        self.assertIn("reverse-dependency", diagnostics["c.py"]["roles"])
        self.assertEqual(diagnostics["c.py"]["reverse_dependency"]["via"], "a.py")

    def test_benchmark_comparison_reports_deltas_without_gating(self):
        baseline = {
            "environment": {"python": "3.11"},
            "results": [{"size": 1000, "context_rebuild_seconds": 2.0}],
        }
        current = {
            "results": [{"size": 1000, "context_rebuild_seconds": 2.5}],
        }
        comparison = benchmark_runtime.comparison_payload(current, baseline)
        self.assertTrue(comparison["available"])
        metric = comparison["sizes"][0]["metrics"]["context_rebuild_seconds"]
        self.assertEqual(metric["delta_percent"], 25.0)


if __name__ == "__main__":
    unittest.main()
