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
            self.assertTrue((target / ".claude/skills/vibe/SKILL.md").exists())
            self.assertTrue((target / ".agents/workflows/vibe.md").exists())
            self.assertTrue((target / ".agents/rules/vibe-project.md").exists())
            self.assertTrue((target / ".vibe/tools/vibe.py").exists())
            self.assertTrue((target / "AGENTS.md").exists())
            self.assertTrue((target / "CLAUDE.md").exists())

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

    def test_dry_run_does_not_create_project_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "project"
            target.mkdir()
            result = self.run_installer(target, "--dry-run")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse((target / ".vibe").exists())
            self.assertFalse((target / ".agents").exists())

    def test_claude_bundle_contains_skill_definition(self):
        result = subprocess.run(
            [sys.executable, str(INSTALLER), "--bundle-claude", "--force"],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        archive = ROOT / "dist" / "claude-skills" / "vibe.zip"
        self.assertTrue(archive.exists())
        with zipfile.ZipFile(str(archive), "r") as bundle:
            self.assertIn("SKILL.md", bundle.namelist())

if __name__ == "__main__":
    unittest.main()
