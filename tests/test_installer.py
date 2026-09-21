import json
import subprocess
import sys
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
