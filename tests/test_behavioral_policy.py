import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BehavioralPolicyTests(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_shared_policy_exists_in_source_and_project_template(self):
        for relative in ("AGENTS.md", "templates/AGENTS.md"):
            with self.subTest(relative=relative):
                text = self.read(relative)
                self.assertIn("## Behavioral coding policy", text)
                self.assertIn("Think before coding", text)
                self.assertIn("Simplicity first", text)
                self.assertIn("Surgical changes", text)
                self.assertIn("Goal-driven execution", text)
                self.assertIn("Changed-line traceability", text)

    def test_claude_files_delegate_shared_behavior_to_agents(self):
        for relative in ("CLAUDE.md", "templates/CLAUDE.md"):
            with self.subTest(relative=relative):
                text = self.read(relative)
                self.assertIn("@AGENTS.md", text)
                self.assertIn("behavioral coding policy", text.lower())
                self.assertNotIn("## Behavioral coding policy", text)

    def test_behavior_is_enforced_by_phase_skills(self):
        plan = self.read("skills/plan/SKILL.md")
        build = self.read("skills/build/SKILL.md")
        verify = self.read("skills/verify/SKILL.md")
        vibe = self.read("skills/vibe/SKILL.md")

        self.assertIn("## Behavioral planning rules", plan)
        self.assertIn("minor/reversible ambiguity", plan)
        self.assertIn("step -> verification evidence", plan)

        self.assertIn("## Behavioral implementation policy", build)
        self.assertIn("minimum code", build)
        self.assertIn("surgical changes", build.lower())
        self.assertIn("Every changed line", build)

        self.assertIn("every changed line traces", verify)
        self.assertIn("no speculative feature/configurability/abstraction", verify)

        self.assertIn("## Behavioral orchestration", vibe)
        self.assertIn("observable goals", vibe)
        self.assertIn("Keep retries evidence-driven", vibe)

    def test_lightweight_frontend_policy_uses_existing_skills(self):
        policy = self.read("skills/vibe/reference/frontend-policy.md")
        self.assertIn("Preserve versus redesign", policy)
        self.assertIn("DESIGN.md is optional", policy)
        self.assertIn("max_rounds", self.read("runtime/vibe_stacks.py"))
        self.assertIn("one primary visual inspection round", policy)

        for relative in ("skills/plan/SKILL.md", "skills/build/SKILL.md", "skills/verify/SKILL.md"):
            with self.subTest(relative=relative):
                self.assertIn("../vibe/reference/frontend-policy.md", self.read(relative))

        self.assertIn('"frontend": true', self.read("adapters/frameworks/react.json"))
        self.assertIn('"frontend": true', self.read("adapters/frameworks/nextjs.json"))

    def test_readmes_document_cross_agent_policy(self):
        english = self.read("README.md")
        vietnamese = self.read("README_vi.md")
        self.assertIn("## Behavioral coding policy", english)
        self.assertIn("Codex, Claude, and Antigravity", english)
        self.assertIn("## Behavioral Coding Policy", vietnamese)
        self.assertIn("Codex, Claude và Antigravity", vietnamese)


if __name__ == "__main__":
    unittest.main()
