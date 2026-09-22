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
