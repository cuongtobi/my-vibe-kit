import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.py"


class InstallerTests(unittest.TestCase):
    def run_installer(self, target, *extra):
        return subprocess.run(
            [
                sys.executable,
                str(INSTALLER),
                "--target",
                str(target),
                "--agents",
                "codex",
                "claude",
                "antigravity",
            ]
            + list(extra),
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

    def test_project_install_materializes_all_agent_layouts(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "project"
            target.mkdir()
            (target / "package.json").write_text(
                json.dumps(
                    {
                        "scripts": {
                            "lint": "eslint .",
                            "test": "vitest run",
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = self.run_installer(target)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            self.assertTrue((target / ".agents/skills/vibe/SKILL.md").exists())
            self.assertTrue((target / ".agents/skills/vibe/reference/frontend-policy.md").exists())
            self.assertTrue((target / ".claude/skills/vibe/SKILL.md").exists())
            self.assertTrue((target / ".claude/skills/vibe/reference/frontend-policy.md").exists())
            self.assertTrue((target / ".agents/workflows/vibe.md").exists())
            self.assertTrue((target / ".agents/rules/vibe-project.md").exists())
            self.assertTrue((target / ".vibe/tools/vibe.py").exists())
            self.assertTrue((target / ".vibe/tools/vibe_retrieval.py").exists())
            self.assertTrue((target / ".vibe/tools/vibe_tasks.py").exists())
            self.assertTrue((target / "AGENTS.md").exists())
            self.assertTrue((target / "CLAUDE.md").exists())
            installed_agents = (target / "AGENTS.md").read_text(encoding="utf-8")
            installed_claude = (target / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn("## Behavioral coding policy", installed_agents)
            self.assertIn("Changed-line traceability", installed_agents)
            self.assertIn("@AGENTS.md", installed_claude)
            self.assertIn("behavioral coding policy", installed_claude.lower())

            config = json.loads(
                (target / ".vibe/config.json").read_text(encoding="utf-8")
            )
            self.assertIn(["npm", "run", "lint"], config["verification"]["commands"])
            self.assertIn(["npm", "run", "test"], config["verification"]["commands"])
            self.assertEqual(config["architecture"]["profile"], "auto")
            self.assertEqual(config["architecture"]["default_profile"], "standard")
            self.assertEqual(config["architecture"]["module_style"], "feature-first")
            self.assertEqual(config["architecture"]["default_pattern"], "modular-layered")
            self.assertEqual(config["architecture"]["strict_pattern"], "hexagonal")
            self.assertEqual(config["version"], 3)
            self.assertEqual(config["context"]["strategy"], "persistent-incremental")
            self.assertEqual(config["context"]["max_dependency_depth"], 2)
            self.assertEqual(config["context"]["max_source_files"], 20)
            self.assertEqual(config["context"]["max_test_files"], 10)
            self.assertEqual(config["index"]["backend"], "json")
            self.assertTrue(config["index"]["use_git_delta"])
            self.assertFalse(config["tasks"]["auto_load_history"])
            self.assertEqual(config["tasks"]["retention"]["policy"], "bounded")
            self.assertEqual(config["tasks"]["retention"]["cleanup"], "manual")
            self.assertEqual(config["context"]["retrieval"]["min_index_score"], 6)
            self.assertEqual(config["context"]["retrieval"]["fallback_max_scan_files"], 20000)
            vibe_gitignore = (target / ".vibe/.gitignore").read_text(encoding="utf-8")
            self.assertIn("runtime/", vibe_gitignore)
            self.assertIn("state/", vibe_gitignore)
            self.assertTrue((target / ".vibe/tools/vibe_state.py").exists())
            self.assertTrue((target / ".vibe/tools/vibe_contracts.py").exists())
            self.assertTrue((target / ".vibe/tools/vibe_security.py").exists())
            self.assertTrue((target / ".vibe/tools/vibe_workflow.py").exists())
            self.assertTrue((target / ".vibe/schemas/contracts-v1.json").exists())
            self.assertTrue((target / ".vibe/adapters/languages/python.json").exists())
            self.assertTrue((target / ".vibe/adapters/languages/typescript.json").exists())
            self.assertFalse((target / ".vibe/adapters/python.json").exists())
            self.assertFalse((target / ".vibe/adapters/typescript.json").exists())
            self.assertFalse((target / ".vibe/adapters/generic.json").exists())
            manifest = json.loads(
                (target / ".vibe/install-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["schema_version"], 2)
            self.assertEqual(manifest["kit_version"], "0.9.2")
            self.assertIn(".vibe/tools/vibe.py", manifest["managed_files"])
            self.assertIn(".agents/skills/vibe/SKILL.md", manifest["managed_files"])
            self.assertIn(".claude/skills/vibe/SKILL.md", manifest["managed_files"])

    def test_laravel_install_detects_stack_and_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "laravel-app"
            target.mkdir()
            (target / "composer.json").write_text(
                json.dumps({"require": {"laravel/framework": "^12.0"}}),
                encoding="utf-8",
            )
            (target / "artisan").write_text("", encoding="utf-8")

            result = self.run_installer(target)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            config = json.loads(
                (target / ".vibe/config.json").read_text(encoding="utf-8")
            )
            self.assertEqual(config["stack"]["primary"], "php")
            self.assertIn("laravel", config["stack"]["frameworks"])
            self.assertIn(["php", "artisan", "test"], config["verification"]["commands"])
            self.assertTrue((target / ".vibe/adapters/languages/php.json").exists())
            self.assertTrue((target / ".vibe/adapters/frameworks/laravel.json").exists())

    def test_rails_install_detects_stack_adapters_and_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "rails-app"
            target.mkdir()
            (target / "Gemfile").write_text(
                "source 'https://rubygems.org'\ngem 'rails', '~> 8.0'\ngem 'rspec-rails'\ngem 'rubocop-rails'\n",
                encoding="utf-8",
            )
            (target / "bin").mkdir()
            (target / "bin" / "rails").write_text("#!/usr/bin/env ruby\n", encoding="utf-8")

            result = self.run_installer(target)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            config = json.loads((target / ".vibe/config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["stack"]["primary"], "ruby")
            self.assertIn("rails", config["stack"]["frameworks"])
            self.assertIn(["bundle", "exec", "rubocop"], config["verification"]["commands"])
            self.assertIn(["bundle", "exec", "rspec"], config["verification"]["commands"])
            self.assertTrue((target / ".vibe/adapters/languages/ruby.json").exists())
            self.assertTrue((target / ".vibe/adapters/frameworks/rails.json").exists())

    def test_existing_project_instructions_are_preserved_even_with_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "project"
            target.mkdir()
            custom = "# My custom project rules\n"
            (target / "AGENTS.md").write_text(custom, encoding="utf-8")

            result = self.run_installer(target, "--force")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                (target / "AGENTS.md").read_text(encoding="utf-8"),
                custom,
            )
            self.assertTrue((target / ".agents/skills/plan/SKILL.md").exists())

    def test_force_upgrade_prunes_obsolete_kit_files_but_preserves_custom_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "project"
            target.mkdir()
            first = self.run_installer(target)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)

            obsolete_runtime = target / ".vibe/tools/obsolete_runtime.py"
            obsolete_runtime.write_text("old = True\n", encoding="utf-8")
            obsolete_skill = target / ".agents/skills/vibe/obsolete.md"
            obsolete_skill.write_text("old\n", encoding="utf-8")
            custom_skill = target / ".agents/skills/custom/SKILL.md"
            custom_skill.parent.mkdir(parents=True)
            custom_skill.write_text("# Custom\n", encoding="utf-8")

            # Simulate the pre-v2 manifest used by 0.9.1 installations.
            manifest_path = target / ".vibe/install-manifest.json"
            legacy_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            legacy_manifest.pop("schema_version", None)
            legacy_manifest.pop("managed_files", None)
            legacy_manifest["kit_version"] = "0.9.1"
            manifest_path.write_text(json.dumps(legacy_manifest), encoding="utf-8")

            upgraded = self.run_installer(target, "--force")
            self.assertEqual(upgraded.returncode, 0, upgraded.stdout + upgraded.stderr)
            self.assertFalse(obsolete_runtime.exists())
            self.assertFalse(obsolete_skill.exists())
            self.assertTrue(custom_skill.exists())
            manifest = json.loads((target / ".vibe/install-manifest.json").read_text(encoding="utf-8"))
            self.assertNotIn(".vibe/tools/obsolete_runtime.py", manifest["managed_files"])

    def test_force_upgrade_rejects_manifest_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "project"
            target.mkdir()
            first = self.run_installer(target)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)

            protected = target / "do-not-delete.txt"
            protected.write_text("keep\n", encoding="utf-8")
            manifest_path = target / ".vibe/install-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["managed_files"].append(".vibe/tools/../../do-not-delete.txt")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            upgraded = self.run_installer(target, "--force")
            self.assertEqual(upgraded.returncode, 0, upgraded.stdout + upgraded.stderr)
            self.assertEqual(protected.read_text(encoding="utf-8"), "keep\n")

    def test_dry_run_does_not_create_project_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "project"
            target.mkdir()
            result = self.run_installer(target, "--dry-run")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse((target / ".vibe").exists())
            self.assertFalse((target / ".agents").exists())

    def test_claude_bundles_are_self_contained_and_rebuilt_when_stale(self):
        result = subprocess.run(
            [sys.executable, str(INSTALLER), "--bundle-claude", "--force"],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        out_dir = ROOT / "dist" / "claude-skills"
        vibe_archive = out_dir / "vibe.zip"
        self.assertTrue(vibe_archive.exists())
        with zipfile.ZipFile(str(vibe_archive), "r") as bundle:
            self.assertIn("SKILL.md", bundle.namelist())
            self.assertIn("reference/frontend-policy.md", bundle.namelist())

        for name in ("plan", "build", "verify"):
            archive = out_dir / (name + ".zip")
            self.assertTrue(archive.exists())
            with zipfile.ZipFile(str(archive), "r") as bundle:
                self.assertIn("SKILL.md", bundle.namelist())
                self.assertIn("reference/frontend-policy.md", bundle.namelist())
                skill = bundle.read("SKILL.md").decode("utf-8")
                self.assertIn("reference/frontend-policy.md", skill)
                self.assertNotIn("../vibe/reference/frontend-policy.md", skill)

        # Generated bundles must not remain silently stale just because a ZIP exists.
        stale = out_dir / "plan.zip"
        stale.write_bytes(b"stale")
        rebuilt = subprocess.run(
            [sys.executable, str(INSTALLER), "--bundle-claude"],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(rebuilt.returncode, 0, rebuilt.stdout + rebuilt.stderr)
        with zipfile.ZipFile(str(stale), "r") as bundle:
            self.assertIn("reference/frontend-policy.md", bundle.namelist())

if __name__ == "__main__":
    unittest.main()
