import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))

import vibe_core  # noqa: E402


class VibeCoreTests(unittest.TestCase):
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
        commit = self.git(root, "commit", "-m", "baseline")
        self.assertEqual(commit.returncode, 0, commit.stdout + commit.stderr)

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
        self.assertTrue((root / ".vibe/runtime/architecture-policy.json").exists())
        self.assertEqual(
            json.loads((root / ".vibe/runtime/architecture-policy.json").read_text(encoding="utf-8"))["effective_profile"],
            "standard",
        )
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

    def test_detects_common_frameworks(self):
        cases = [
            ("flask", {"pyproject.toml": "[project]\ndependencies = [\"flask\"]\n"}),
            ("express", {"package.json": json.dumps({"dependencies": {"express": "^5.0.0"}})}),
            ("laravel", {"composer.json": json.dumps({"require": {"laravel/framework": "^12.0"}}), "artisan": ""}),
            ("spring", {"pom.xml": "<dependency>org.springframework.boot:spring-boot-starter-web</dependency>"}),
            ("gin", {"go.mod": "module example.com/app\nrequire github.com/gin-gonic/gin v1.10.0\n"}),
            ("actix-web", {"Cargo.toml": "[dependencies]\nactix-web = \"4\"\n"}),
        ]
        for expected, files in cases:
            with self.subTest(expected=expected):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    for name, content in files.items():
                        path = root / name
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(content, encoding="utf-8")
                    stack = vibe_core.detect_stack(root)
                    self.assertIn(expected, stack["frameworks"])

    def test_laravel_framework_context_and_php_dependency_graph(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        (root / "composer.json").write_text(
            json.dumps({"require": {"laravel/framework": "^12.0"}}),
            encoding="utf-8",
        )
        (root / "artisan").write_text("", encoding="utf-8")
        language_adapters = root / ".vibe" / "adapters" / "languages"
        framework_adapters = root / ".vibe" / "adapters" / "frameworks"
        language_adapters.mkdir(parents=True)
        framework_adapters.mkdir(parents=True)
        (language_adapters / "php.json").write_text(
            json.dumps({"id": "php", "kind": "language"}), encoding="utf-8"
        )
        (framework_adapters / "laravel.json").write_text(
            json.dumps({"id": "laravel", "kind": "framework"}), encoding="utf-8"
        )
        routes = root / "routes"
        routes.mkdir()
        (routes / "web.php").write_text(
            "<?php\nuse App\\Services\\OrderService;\nRoute::get('/orders', fn () => []);\n",
            encoding="utf-8",
        )
        service = root / "app" / "Services"
        service.mkdir(parents=True)
        (service / "OrderService.php").write_text(
            "<?php\nnamespace App\\Services;\nclass OrderService {}\n",
            encoding="utf-8",
        )

        context = vibe_core.project_context(root)
        self.assertIn("laravel", context["frameworks"])
        self.assertEqual(context["active_adapter"]["language"], "php")
        self.assertIn("laravel", context["active_adapter"]["frameworks"])
        active = json.loads(
            (root / ".vibe/runtime/active-adapter.json").read_text(encoding="utf-8")
        )
        self.assertEqual(active["language"]["id"], "php")
        self.assertEqual(active["frameworks"][0]["id"], "laravel")
        framework = json.loads(
            (root / ".vibe/runtime/framework-map.json").read_text(encoding="utf-8")
        )
        self.assertTrue(any(route["path"] == "/orders" for route in framework["routes"]))

        graph = vibe_core.dependency_graph(root)
        edges = {(item["from"], item["to"]) for item in graph["edges"]}
        self.assertIn(("routes/web.php", "app/Services/OrderService.php"), edges)
        self.assertIn("php-static", graph["scanners"])
        impact = vibe_core.impact_analysis(root, ["app/Services/OrderService.php"])
        self.assertTrue(any(route["path"] == "/orders" for route in impact["affected_routes"]))

    def test_java_go_and_rust_dependency_scanners(self):
        fixtures = []

        java_files = {
            "pom.xml": "<project></project>",
            "src/main/java/com/example/A.java": "package com.example;\nimport com.example.B;\nclass A {}\n",
            "src/main/java/com/example/B.java": "package com.example;\nclass B {}\n",
        }
        fixtures.append(("java-kotlin-imports", java_files, ("src/main/java/com/example/A.java", "src/main/java/com/example/B.java")))

        go_files = {
            "go.mod": "module example.com/app\n",
            "cmd/app/main.go": 'package main\nimport "example.com/app/internal/orders"\nfunc main() {}\n',
            "internal/orders/orders.go": "package orders\n",
        }
        fixtures.append(("go-module-imports", go_files, ("cmd/app/main.go", "internal/orders/orders.go")))

        rust_files = {
            "Cargo.toml": "[package]\nname=\"demo\"\nversion=\"0.1.0\"\n",
            "src/lib.rs": "mod orders;\n",
            "src/orders.rs": "pub fn run() {}\n",
        }
        fixtures.append(("rust-mod-use", rust_files, ("src/lib.rs", "src/orders.rs")))

        for scanner, files, expected_edge in fixtures:
            with self.subTest(scanner=scanner):
                temp, root = self.make_repo()
                try:
                    for name, content in files.items():
                        path = root / name
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(content, encoding="utf-8")
                    graph = vibe_core.dependency_graph(root)
                    edges = {(item["from"], item["to"]) for item in graph["edges"]}
                    self.assertIn(scanner, graph["scanners"])
                    self.assertIn(expected_edge, edges)
                finally:
                    temp.cleanup()

    def test_greenfield_architecture_defaults_to_standard_modular_layered(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        policy = vibe_core.architecture_policy(root)
        self.assertEqual(policy["effective_profile"], "standard")
        self.assertEqual(policy["pattern"], "modular-layered")
        self.assertEqual(policy["module_style"], "feature-first")
        self.assertFalse(policy["auto_strict_triggered"])
        self.assertTrue(policy["clean_code_rules"])

    def test_explicit_strict_profile_uses_hexagonal_policy(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        config = json.loads((root / ".vibe/config.json").read_text(encoding="utf-8"))
        config["architecture"] = {
            "profile": "strict",
            "module_style": "feature-first",
            "default_pattern": "modular-layered",
            "strict_pattern": "hexagonal",
        }
        (root / ".vibe/config.json").write_text(json.dumps(config), encoding="utf-8")
        policy = vibe_core.architecture_policy(root)
        self.assertEqual(policy["effective_profile"], "strict")
        self.assertEqual(policy["pattern"], "hexagonal")
        self.assertTrue(any("Domain is framework-independent" in rule for rule in policy["dependency_rules"]))

    def test_auto_profile_promotes_large_project_to_strict(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        src = root / "src"
        src.mkdir()
        (src / "a.py").write_text("a = 1\n", encoding="utf-8")
        (src / "b.py").write_text("b = 2\n", encoding="utf-8")
        config = json.loads((root / ".vibe/config.json").read_text(encoding="utf-8"))
        config["architecture"] = {
            "profile": "auto",
            "default_profile": "standard",
            "strict_pattern": "hexagonal",
            "allow_auto_strict": True,
            "strict_thresholds": {"source_files": 2, "feature_roots": 99},
        }
        (root / ".vibe/config.json").write_text(json.dumps(config), encoding="utf-8")
        policy = vibe_core.architecture_policy(root)
        self.assertTrue(policy["auto_strict_triggered"])
        self.assertEqual(policy["effective_profile"], "strict")
        self.assertEqual(policy["pattern"], "hexagonal")

    def test_laravel_architecture_prefers_framework_native_structure(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        (root / "composer.json").write_text(
            json.dumps({"require": {"laravel/framework": "^12.0"}}),
            encoding="utf-8",
        )
        (root / "artisan").write_text("", encoding="utf-8")
        policy = vibe_core.architecture_policy(root)
        self.assertEqual(policy["effective_profile"], "standard")
        self.assertIn("controllers/requests", policy["recommended_structure"])
        self.assertTrue(any("Laravel conventions" in note for note in policy["framework_guidance"][0]["notes"]))

    def test_persistent_context_cache_hits_when_repository_is_unchanged(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        pkg = root / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "service.py").write_text("value = 1\n", encoding="utf-8")
        self.init_git(root)

        first_context = vibe_core.project_context(root)
        first_graph = vibe_core.dependency_graph(root)
        second_context = vibe_core.project_context(root)
        second_graph = vibe_core.dependency_graph(root)

        self.assertEqual(first_context["cache"]["mode"], "FULL_REBUILD")
        self.assertEqual(first_graph["cache"]["mode"], "FULL_REBUILD")
        self.assertEqual(second_context["cache"]["mode"], "CACHE_HIT")
        self.assertEqual(second_graph["cache"]["mode"], "CACHE_HIT")
        self.assertTrue((root / ".vibe/state/last-context.json").exists())
        self.assertTrue((root / ".vibe/state/last-dependency.json").exists())
        self.assertTrue((root / ".vibe/state/index-state.json").exists())

    def test_python_dependency_refresh_is_incremental_after_single_file_change(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        pkg = root / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "a.py").write_text("from pkg.b import value\n", encoding="utf-8")
        (pkg / "b.py").write_text("value = 1\n", encoding="utf-8")
        (pkg / "c.py").write_text("value = 2\n", encoding="utf-8")
        self.init_git(root)

        vibe_core.project_context(root)
        before = vibe_core.dependency_graph(root)
        self.assertIn(
            ("pkg/a.py", "pkg/b.py"),
            {(item["from"], item["to"]) for item in before["edges"]},
        )

        (pkg / "a.py").write_text("from pkg.c import value\n", encoding="utf-8")
        context = vibe_core.project_context(root)
        after = vibe_core.dependency_graph(root)
        edges = {(item["from"], item["to"]) for item in after["edges"]}

        self.assertEqual(context["cache"]["mode"], "INCREMENTAL_REFRESH")
        self.assertEqual(after["cache"]["mode"], "INCREMENTAL_REFRESH")
        self.assertIn("pkg/a.py", after["cache"]["changed_files"])
        self.assertIn(("pkg/a.py", "pkg/c.py"), edges)
        self.assertNotIn(("pkg/a.py", "pkg/b.py"), edges)

    def test_relevant_context_is_bounded_and_does_not_auto_load_history(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        config = json.loads((root / ".vibe/config.json").read_text(encoding="utf-8"))
        config["context"].update({
            "max_dependency_depth": 2,
            "max_source_files": 2,
            "max_test_files": 1,
            "max_related_modules": 2,
        })
        config["tasks"]["auto_load_history"] = False
        (root / ".vibe/config.json").write_text(json.dumps(config), encoding="utf-8")

        orders = root / "src" / "orders"
        orders.mkdir(parents=True)
        (orders / "__init__.py").write_text("", encoding="utf-8")
        (orders / "service.py").write_text("from orders.repo import value\n", encoding="utf-8")
        (orders / "repo.py").write_text("value = 1\n", encoding="utf-8")
        (orders / "extra.py").write_text("value = 2\n", encoding="utf-8")
        tests = root / "tests"
        tests.mkdir()
        (tests / "test_orders.py").write_text("from orders.service import value\n", encoding="utf-8")
        self.init_git(root)

        vibe_core.start_task(root, "feature", "add orders workflow")
        data = vibe_core.relevant_context(root)

        self.assertLessEqual(len(data["source_files"]), 2)
        self.assertLessEqual(len(data["test_files"]), 1)
        self.assertFalse(data["history_policy"]["auto_load_history"])
        self.assertTrue((root / ".vibe/runtime/relevant-context.json").exists())

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
        self.assertEqual(report["architecture"]["profile"], "standard")
        self.assertEqual(report["architecture"]["pattern"], "modular-layered")


if __name__ == "__main__":
    unittest.main()
