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
            ("react", {"package.json": json.dumps({"dependencies": {"react": "^19.0.0"}})}),
            ("vue", {"package.json": json.dumps({"dependencies": {"vue": "^3.5.0"}})}),
            ("nuxt", {"package.json": json.dumps({"dependencies": {"nuxt": "^4.0.0", "vue": "^3.5.0"}})}),
            ("svelte", {"package.json": json.dumps({"dependencies": {"svelte": "^5.0.0"}})}),
            ("sveltekit", {"package.json": json.dumps({"dependencies": {"@sveltejs/kit": "^2.0.0", "svelte": "^5.0.0"}})}),
            ("vite", {"package.json": json.dumps({"devDependencies": {"vite": "^7.0.0"}})}),
            ("nextjs", {"package.json": json.dumps({"dependencies": {"next": "^16.0.0", "react": "^19.0.0"}})}),
            ("wordpress", {"sample-plugin.php": "<?php\n/*\nPlugin Name: Sample Plugin\n*/\n"}),
            ("laravel", {"composer.json": json.dumps({"require": {"laravel/framework": "^12.0"}}), "artisan": ""}),
            ("rails", {"Gemfile": "source 'https://rubygems.org'\ngem 'rails', '~> 8.0'\n", "bin/rails": "#!/usr/bin/env ruby\n"}),
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

    def test_frontend_framework_context_includes_components_and_file_routes(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        (root / "package.json").write_text(
            json.dumps({
                "dependencies": {
                    "react": "^19.0.0",
                    "next": "^16.0.0",
                    "vue": "^3.5.0",
                    "nuxt": "^4.0.0",
                    "svelte": "^5.0.0",
                    "@sveltejs/kit": "^2.0.0"
                },
                "devDependencies": {"vite": "^7.0.0"}
            }),
            encoding="utf-8",
        )
        app = root / "app"
        app.mkdir()
        (app / "page.tsx").write_text(
            "'use client'\nexport function HomePage() { return null }\n",
            encoding="utf-8",
        )
        pages = root / "pages"
        pages.mkdir()
        (pages / "about.vue").write_text("<template><div>About</div></template>\n", encoding="utf-8")
        routes = root / "src" / "routes" / "dashboard"
        routes.mkdir(parents=True)
        (routes / "+page.svelte").write_text("<h1>Dashboard</h1>\n", encoding="utf-8")

        context = vibe_core.project_context(root)
        frameworks = set(context["frameworks"])
        self.assertTrue({"react", "vue", "nuxt", "svelte", "sveltekit", "vite", "nextjs"}.issubset(frameworks))

        framework = json.loads((root / ".vibe/runtime/framework-map.json").read_text(encoding="utf-8"))
        self.assertIn("app/page.tsx", framework["components"]["react_components"])
        self.assertIn("pages/about.vue", framework["components"]["vue_components"])
        self.assertIn("src/routes/dashboard/+page.svelte", framework["components"]["svelte_components"])
        self.assertTrue(any(route["framework"] == "nextjs" and route["path"] == "/" for route in framework["routes"]))
        self.assertTrue(any(route["framework"] == "nuxt" and route["path"] == "/about" for route in framework["routes"]))
        self.assertTrue(any(route["framework"] == "sveltekit" and route["path"] == "/dashboard" for route in framework["routes"]))

        graph = vibe_core.dependency_graph(root)
        self.assertIn("pages/about.vue", graph["nodes"])
        self.assertIn("src/routes/dashboard/+page.svelte", graph["nodes"])

    def test_wordpress_plugin_context_and_architecture_guidance(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        plugin = root / "sample-plugin.php"
        plugin.write_text(
            "<?php\n/*\nPlugin Name: Sample Plugin\n*/\n"
            "add_action('init', 'sample_init');\n"
            "register_rest_route('sample/v1', '/items', []);\n",
            encoding="utf-8",
        )

        stack = vibe_core.detect_stack(root)
        self.assertEqual(stack["primary"], "php")
        self.assertIn("wordpress", stack["frameworks"])

        context = vibe_core.project_context(root)
        framework = json.loads((root / ".vibe/runtime/framework-map.json").read_text(encoding="utf-8"))
        self.assertIn("sample-plugin.php", framework["components"]["wordpress_hook_files"])
        self.assertTrue(any(route["framework"] == "wordpress" and route["path"] == "/sample/v1/items" for route in framework["routes"]))

        policy = vibe_core.architecture_policy(root)
        wordpress_guidance = [item for item in policy["framework_guidance"] if item["framework"] == "wordpress"]
        self.assertTrue(wordpress_guidance)
        self.assertTrue(any("WordPress core" in note for note in wordpress_guidance[0]["notes"]))

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

    def test_rails_framework_context_ruby_dependency_graph_and_architecture(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        (root / "Gemfile").write_text(
            "source 'https://rubygems.org'\ngem 'rails', '~> 8.0'\ngem 'rspec-rails'\ngem 'rubocop-rails'\n",
            encoding="utf-8",
        )
        language_adapters = root / ".vibe" / "adapters" / "languages"
        framework_adapters = root / ".vibe" / "adapters" / "frameworks"
        language_adapters.mkdir(parents=True)
        framework_adapters.mkdir(parents=True)
        (language_adapters / "ruby.json").write_text(
            json.dumps({"id": "ruby", "kind": "language"}), encoding="utf-8"
        )
        (framework_adapters / "rails.json").write_text(
            json.dumps({"id": "rails", "kind": "framework"}), encoding="utf-8"
        )
        (root / "bin").mkdir()
        (root / "bin" / "rails").write_text("#!/usr/bin/env ruby\n", encoding="utf-8")
        (root / "config").mkdir()
        (root / "config" / "application.rb").write_text(
            "class Application < Rails::Application\nend\n", encoding="utf-8"
        )
        (root / "config" / "routes.rb").write_text(
            "get '/orders', to: 'orders#index'\nresources :accounts\n", encoding="utf-8"
        )
        controllers = root / "app" / "controllers"
        services = root / "app" / "services"
        models = root / "app" / "models"
        controllers.mkdir(parents=True)
        services.mkdir(parents=True)
        models.mkdir(parents=True)
        (controllers / "orders_controller.rb").write_text(
            "require_relative '../services/order_service'\nclass OrdersController\nend\n",
            encoding="utf-8",
        )
        (services / "order_service.rb").write_text("class OrderService\nend\n", encoding="utf-8")
        (models / "order.rb").write_text("class Order < ApplicationRecord\nend\n", encoding="utf-8")

        context = vibe_core.project_context(root)
        self.assertEqual(context["stack"]["primary"], "ruby")
        self.assertIn("rails", context["frameworks"])
        self.assertEqual(context["active_adapter"]["language"], "ruby")
        self.assertIn("rails", context["active_adapter"]["frameworks"])

        framework = json.loads((root / ".vibe/runtime/framework-map.json").read_text(encoding="utf-8"))
        self.assertIn("app/controllers/orders_controller.rb", framework["components"]["rails_controllers"])
        self.assertIn("app/models/order.rb", framework["components"]["rails_models"])
        self.assertIn("app/services/order_service.rb", framework["components"]["rails_services"])
        self.assertTrue(any(route["framework"] == "rails" and route["path"] == "/orders" for route in framework["routes"]))
        self.assertTrue(any(route["framework"] == "rails" and route["path"] == "/accounts" for route in framework["routes"]))

        graph = vibe_core.dependency_graph(root)
        edges = {(item["from"], item["to"]) for item in graph["edges"]}
        self.assertIn("ruby-require", graph["scanners"])
        self.assertIn(("app/controllers/orders_controller.rb", "app/services/order_service.rb"), edges)

        policy = vibe_core.architecture_policy(root)
        rails_guidance = [item for item in policy["framework_guidance"] if item["framework"] == "rails"]
        self.assertTrue(rails_guidance)
        self.assertTrue(any("Rails conventions" in note for note in rails_guidance[0]["notes"]))

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

    def test_relevant_context_ranks_symbol_and_content_matches(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        (root / "manager.py").write_text(
            "def refresh_access_token(session):\n"
            "    if session.expired:\n"
            "        return rotate_token(session)\n",
            encoding="utf-8",
        )
        (root / "unrelated.py").write_text("def calculate_invoice():\n    return 1\n", encoding="utf-8")
        self.init_git(root)

        vibe_core.start_task(root, "bug_fix", "fix refresh token logic after session expires")
        data = vibe_core.relevant_context(root)

        self.assertIn("manager.py", data["targets"])
        evidence = next(item for item in data["retrieval_evidence"] if item["path"] == "manager.py")
        self.assertIn("refresh", evidence["symbol_matches"])
        self.assertIn("session", evidence["content_matches"])
        index = json.loads((root / ".vibe/state/file-index.json").read_text(encoding="utf-8"))
        self.assertIn("refresh_access_token", index["manager.py"]["symbols"])

    def test_js_dependency_graph_resolves_paths_and_workspace_exports(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        (root / "package.json").write_text(
            json.dumps({"workspaces": ["packages/*"]}),
            encoding="utf-8",
        )
        (root / "tsconfig.json").write_text(
            json.dumps({"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}),
            encoding="utf-8",
        )
        src = root / "src"
        (src / "services").mkdir(parents=True)
        (src / "services" / "auth.ts").write_text("export const auth = 1\n", encoding="utf-8")
        (src / "main.ts").write_text("import { auth } from '@/services/auth'\n", encoding="utf-8")

        ui = root / "packages" / "ui"
        (ui / "src").mkdir(parents=True)
        (ui / "package.json").write_text(
            json.dumps({
                "name": "@acme/ui",
                "exports": {"./button": "./src/button.ts"},
            }),
            encoding="utf-8",
        )
        (ui / "src" / "button.ts").write_text("export const Button = 1\n", encoding="utf-8")
        (src / "consumer.ts").write_text("import { Button } from '@acme/ui/button'\n", encoding="utf-8")

        graph = vibe_core.dependency_graph(root)
        edges = {(item["from"], item["to"]) for item in graph["edges"]}
        self.assertIn(("src/main.ts", "src/services/auth.ts"), edges)
        self.assertIn(("src/consumer.ts", "packages/ui/src/button.ts"), edges)

    def test_js_resolution_manifest_change_rescans_unchanged_importers(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        (root / "package.json").write_text(json.dumps({"workspaces": ["packages/*"]}), encoding="utf-8")
        (root / "tsconfig.json").write_text(
            json.dumps({"compilerOptions": {"paths": {"@/*": ["src/*"]}}}),
            encoding="utf-8",
        )
        (root / "src").mkdir()
        (root / "alt").mkdir()
        (root / "src" / "auth.ts").write_text("export const auth = 'src'\n", encoding="utf-8")
        (root / "alt" / "auth.ts").write_text("export const auth = 'alt'\n", encoding="utf-8")
        (root / "main.ts").write_text("import { auth } from '@/auth'\n", encoding="utf-8")

        package = root / "packages" / "ui"
        (package / "src").mkdir(parents=True)
        (package / "package.json").write_text(
            json.dumps({"name": "@acme/ui", "exports": ".\/src\/a.ts".replace("\\/", "/")}),
            encoding="utf-8",
        )
        (package / "src" / "a.ts").write_text("export const value = 'a'\n", encoding="utf-8")
        (package / "src" / "b.ts").write_text("export const value = 'b'\n", encoding="utf-8")
        (root / "consumer.ts").write_text("import { value } from '@acme/ui'\n", encoding="utf-8")
        self.init_git(root)

        before = vibe_core.dependency_graph(root)
        before_edges = {(item["from"], item["to"]) for item in before["edges"]}
        self.assertIn(("main.ts", "src/auth.ts"), before_edges)
        self.assertIn(("consumer.ts", "packages/ui/src/a.ts"), before_edges)

        (root / "tsconfig.json").write_text(
            json.dumps({"compilerOptions": {"paths": {"@/*": ["alt/*"]}}}),
            encoding="utf-8",
        )
        (package / "package.json").write_text(
            json.dumps({"name": "@acme/ui", "exports": "./src/b.ts"}),
            encoding="utf-8",
        )
        after = vibe_core.dependency_graph(root)
        after_edges = {(item["from"], item["to"]) for item in after["edges"]}
        self.assertEqual(after["cache"]["mode"], "INCREMENTAL_REFRESH")
        self.assertIn(("main.ts", "alt/auth.ts"), after_edges)
        self.assertNotIn(("main.ts", "src/auth.ts"), after_edges)
        self.assertIn(("consumer.ts", "packages/ui/src/b.ts"), after_edges)
        self.assertNotIn(("consumer.ts", "packages/ui/src/a.ts"), after_edges)

    def test_polyglot_active_adapter_exposes_all_languages_and_primary(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        (root / "package.json").write_text(
            json.dumps({"dependencies": {"next": "^16.0.0", "react": "^19.0.0"}}),
            encoding="utf-8",
        )
        (root / "tsconfig.json").write_text("{}", encoding="utf-8")
        (root / "pyproject.toml").write_text(
            "[project]\ndependencies = [\"fastapi\"]\n",
            encoding="utf-8",
        )
        (root / "app.py").write_text("from fastapi import FastAPI\n", encoding="utf-8")
        (root / "page.tsx").write_text("export const Page = () => null\n", encoding="utf-8")

        # Source-tree adapters are used directly when testing the kit repository runtime.
        adapters = root / "adapters"
        (adapters / "languages").mkdir(parents=True)
        for language in ("python", "javascript", "typescript"):
            (adapters / "languages" / (language + ".json")).write_text(
                json.dumps({"id": language, "kind": "language"}),
                encoding="utf-8",
            )
        (adapters / "frameworks").mkdir()
        for framework in ("fastapi", "nextjs", "react"):
            (adapters / "frameworks" / (framework + ".json")).write_text(
                json.dumps({"id": framework, "kind": "framework"}),
                encoding="utf-8",
            )

        context = vibe_core.project_context(root)
        self.assertEqual(context["active_adapter"]["primary"], "typescript")
        self.assertTrue({"python", "javascript", "typescript"}.issubset(set(context["active_adapter"]["languages"])))
        active = json.loads((root / ".vibe/runtime/active-adapter.json").read_text(encoding="utf-8"))
        self.assertEqual(active["primary_language"]["id"], "typescript")
        self.assertTrue({"python", "javascript", "typescript"}.issubset({item["id"] for item in active["languages"]}))

    def test_dependency_graph_declares_static_advisory_authority(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        (root / "a.py").write_text("value = 1\n", encoding="utf-8")
        graph = vibe_core.dependency_graph(root)
        self.assertEqual(graph["authority"]["level"], "advisory")
        self.assertEqual(graph["authority"]["model"], "static-best-effort")
        relevant = vibe_core.relevant_context(root, ["a.py"])
        self.assertEqual(relevant["dependency_authority"]["level"], "advisory")

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

    def test_verify_cli_requires_evidence_even_when_commands_are_optional(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        config_path = root / ".vibe/config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["verification"] = {"require_commands": False, "commands": []}
        config_path.write_text(json.dumps(config), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(ROOT / "runtime/vibe.py"), "--root", str(root), "verify"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "NEEDS_VERIFICATION_CONFIG")
        self.assertEqual(report["commands_run"], 0)

        config["verification"]["commands"] = [[sys.executable, "-c", "print('checked')"]]
        config_path.write_text(json.dumps(config), encoding="utf-8")
        report = vibe_core.verify(root)
        self.assertEqual(report["status"], "PASS_VERIFIED")
        self.assertEqual(report["commands_run"], 1)

    def test_python_import_statement_records_every_module(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        for name, content in {
            "main.py": "import a as first, b as second\n",
            "a.py": "value = 1\n",
            "b.py": "value = 2\n",
        }.items():
            (root / name).write_text(content, encoding="utf-8")

        graph = vibe_core.dependency_graph(root)
        self.assertEqual(
            vibe_core.edge_set(graph), {("main.py", "a.py"), ("main.py", "b.py")},
        )
        impact = vibe_core.impact_analysis(root, ["b.py"])
        self.assertIn("main.py", impact["affected_reverse_dependencies"])

    def test_python_from_import_records_package_and_all_submodules(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        pkg = root / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("from . import a, b\n", encoding="utf-8")
        (pkg / "a.py").write_text("value = 1\n", encoding="utf-8")
        (pkg / "b.py").write_text("value = 2\n", encoding="utf-8")
        (root / "consumer.py").write_text("from pkg import a as first, b\n", encoding="utf-8")
        (root / "symbols.py").write_text("from pkg.a import value\n", encoding="utf-8")
        (root / "wildcard.py").write_text("from pkg import *\n", encoding="utf-8")

        graph = vibe_core.dependency_graph(root)
        self.assertEqual(vibe_core.edge_set(graph), {
            ("pkg/__init__.py", "pkg/a.py"),
            ("pkg/__init__.py", "pkg/b.py"),
            ("consumer.py", "pkg/__init__.py"),
            ("consumer.py", "pkg/a.py"),
            ("consumer.py", "pkg/b.py"),
            ("symbols.py", "pkg/a.py"),
            ("wildcard.py", "pkg/__init__.py"),
        })

    def test_incremental_new_module_detects_cycle_and_fails_verification(self):
        for extension, imports in (
            ("py", ("import b\n", "import a\n")),
            ("js", ("import './b';\n", "import './a';\n")),
        ):
            with self.subTest(extension=extension):
                temp, root = self.make_repo()
                self.addCleanup(temp.cleanup)
                a, b = "a." + extension, "b." + extension
                (root / a).write_text(imports[0], encoding="utf-8")
                config_path = root / ".vibe/config.json"
                config = json.loads(config_path.read_text(encoding="utf-8"))
                config["verification"]["commands"] = [[sys.executable, "-c", "print('checked')"]]
                config_path.write_text(json.dumps(config), encoding="utf-8")
                self.init_git(root)
                vibe_core.start_task(root, "feature", "add missing module")
                vibe_core.dependency_graph(root)
                vibe_core.snapshot_dependencies(root, "before")

                (root / b).write_text(imports[1], encoding="utf-8")
                graph = vibe_core.dependency_graph(root)
                self.assertEqual(graph["cache"]["mode"], "INCREMENTAL_REFRESH")
                self.assertEqual(vibe_core.edge_set(graph), {(a, b), (b, a)})
                self.assertEqual(graph["cycles"], [[a, b]])
                report = vibe_core.verify(root)
                self.assertEqual(report["status"], "FAIL_VERIFICATION")
                self.assertEqual(report["new_cycles"], [[a, b]])
                rebuilt = vibe_core.dependency_graph(root, force=True)
                self.assertEqual(graph["edges"], rebuilt["edges"])

    def test_incremental_module_deletion_resolves_existing_imports_again(self):
        cases = [
            ("main.py", "import pkg.child\n", "pkg/child.py", "pkg/__init__.py"),
            ("main.js", "import './child';\n", "child.ts", "child.js"),
        ]
        for consumer, statement, removed, fallback in cases:
            with self.subTest(consumer=consumer):
                temp, root = self.make_repo()
                self.addCleanup(temp.cleanup)
                for name, content in {consumer: statement, removed: "", fallback: ""}.items():
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content, encoding="utf-8")
                self.init_git(root)
                before = vibe_core.dependency_graph(root)
                self.assertIn((consumer, removed), vibe_core.edge_set(before))

                (root / removed).unlink()
                graph = vibe_core.dependency_graph(root)
                self.assertEqual(graph["cache"]["mode"], "INCREMENTAL_REFRESH")
                self.assertEqual(vibe_core.edge_set(graph), {(consumer, fallback)})
                self.assertNotIn(removed, graph["nodes"])

    def test_incremental_module_rename_resolves_unchanged_consumer(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        (root / "main.py").write_text("import old\nimport new\n", encoding="utf-8")
        (root / "old.py").write_text("value = 1\n", encoding="utf-8")
        self.init_git(root)
        vibe_core.dependency_graph(root)

        (root / "old.py").rename(root / "new.py")
        self.assertEqual(self.git(root, "add", "old.py", "new.py").returncode, 0)
        graph = vibe_core.dependency_graph(root)
        self.assertEqual(graph["cache"]["mode"], "INCREMENTAL_REFRESH")
        self.assertEqual(vibe_core.edge_set(graph), {("main.py", "new.py")})
        self.assertNotIn("old.py", graph["nodes"])

    def test_invalid_dependency_cache_rebuilds_with_or_without_git_changes(self):
        for corrupt in ("{invalid-json", "{}", "[]", '{"nodes": [], "edges": "invalid"}'):
            for dirty in (False, True):
                with self.subTest(corrupt=corrupt, dirty=dirty):
                    temp, root = self.make_repo()
                    self.addCleanup(temp.cleanup)
                    (root / "a.py").write_text("import b\n", encoding="utf-8")
                    (root / "b.py").write_text("import c\n", encoding="utf-8")
                    (root / "c.py").write_text("value = 1\n", encoding="utf-8")
                    self.init_git(root)
                    vibe_core.dependency_graph(root)
                    (root / ".vibe/state/last-dependency.json").write_text(corrupt, encoding="utf-8")
                    if dirty:
                        (root / "a.py").write_text("import c\n", encoding="utf-8")

                    graph = vibe_core.dependency_graph(root)
                    self.assertEqual(graph["cache"]["mode"], "FULL_REBUILD")
                    self.assertEqual(vibe_core.edge_set(graph), {
                        ("a.py", "c.py" if dirty else "b.py"), ("b.py", "c.py"),
                    })
                    self.assertEqual(graph["nodes"], ["a.py", "b.py", "c.py"])
                    self.assertEqual(vibe_core.dependency_graph(root)["cache"]["mode"], "CACHE_HIT")

    def test_empty_dependency_graph_is_a_valid_cache(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        self.init_git(root)
        vibe_core.dependency_graph(root)
        graph = vibe_core.dependency_graph(root)
        self.assertEqual(graph["cache"]["mode"], "CACHE_HIT")
        self.assertEqual(graph["nodes"], [])
        self.assertEqual(graph["edges"], [])

    def test_old_scanner_cache_is_rebuilt_after_upgrade(self):
        temp, root = self.make_repo()
        self.addCleanup(temp.cleanup)
        (root / "a.py").write_text("value = 1\n", encoding="utf-8")
        self.init_git(root)
        vibe_core.dependency_graph(root)
        index_path = root / ".vibe/state/index-state.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["scanner_version"] = "incremental-v1"
        index_path.write_text(json.dumps(index), encoding="utf-8")

        graph = vibe_core.dependency_graph(root)
        self.assertEqual(graph["cache"]["mode"], "FULL_REBUILD")
        self.assertEqual(graph["nodes"], ["a.py"])


if __name__ == "__main__":
    unittest.main()
