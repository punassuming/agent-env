from pathlib import Path
import unittest

from agent_env import VERSION


class SkillContractTests(unittest.TestCase):
    def test_version_and_discovery_files(self):
        repo = Path(__file__).resolve().parents[1]
        canonical = repo / ".agents" / "skills" / "bootstrap-agent-env" / "SKILL.md"
        text = canonical.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\nname: bootstrap-agent-env\n"))
        self.assertIn("description:", text.split("---", 2)[1])
        self.assertIn(f"Current version: **{VERSION}**", text)
        for relative in ("references/recipes.md", "references/contract.md", "references/infrastructure.md", "references/sandbox.md", "references/evaluation.md", "references/evaluation-loop.md", "scripts/evaluations/loop.py"):
            self.assertTrue((canonical.parent / relative).is_file())
        self.assertIn("bootstrap-agent-env", (repo / ".claude" / "skills" / "bootstrap-agent-env" / "SKILL.md").read_text())
