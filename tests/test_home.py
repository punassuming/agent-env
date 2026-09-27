import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from agent_env.home import sync
from agent_env import VERSION


class HomeSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.source, self.home = base / "source", base / "user" / ".agents"
        self.source.mkdir()
        skill = self.source / ".agents" / "skills" / "bootstrap-agent-env"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: bootstrap-agent-env\n---\n")
        (self.source / "README.md").write_text("initial\n")
        subprocess.run(["git", "init", "-q", str(self.source)], check=True)
        subprocess.run(["git", "-C", str(self.source), "add", "."], check=True)

    def test_plan_sync_repeat_update_and_conflict(self):
        plan = sync(self.source, self.home)
        self.assertEqual(len(plan["changes"]), 3)
        self.assertFalse(self.home.exists())
        self.assertFalse(sync(self.source, self.home, write=True)["conflicts"])
        self.assertEqual((self.home / "skills" / "bootstrap-agent-env" / "SKILL.md").read_text(),
                         (self.source / ".agents" / "skills" / "bootstrap-agent-env" / "SKILL.md").read_text())
        self.assertEqual(sync(self.source, self.home)["changes"], [])
        self.assertEqual(sync(self.home / "agent-env", self.home)["changes"], [])
        (self.source / "README.md").write_text("updated upstream\n")
        report = sync(self.source, self.home, write=True)
        self.assertEqual(len(report["changes"]), 1)
        self.assertEqual((self.home / "agent-env" / "README.md").read_text(), "updated upstream\n")
        (self.home / "agent-env" / "README.md").write_text("local edit\n")
        (self.source / "README.md").write_text("another upstream edit\n")
        report = sync(self.source, self.home, write=True)
        self.assertEqual(len(report["conflicts"]), 1)
        self.assertEqual((self.home / "agent-env" / "README.md").read_text(), "local edit\n")
        self.assertEqual(json.loads((self.home / "agent-env-sync.json").read_text())["source_version"], VERSION)

    def test_unknown_existing_skill_is_not_overwritten(self):
        skill = self.home / "skills" / "bootstrap-agent-env" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("user owned\n")
        report = sync(self.source, self.home, write=True)
        self.assertIn(str(skill), report["conflicts"])
        self.assertFalse((self.home / "agent-env" / "README.md").exists())

    def test_optional_claude_skill_copy(self):
        report = sync(self.source, self.home, claude=True, write=True)
        self.assertFalse(report["conflicts"])
        claude = self.home.parent / ".claude" / "skills" / "bootstrap-agent-env" / "SKILL.md"
        self.assertEqual(claude.read_bytes(), (self.source / ".agents" / "skills" / "bootstrap-agent-env" / "SKILL.md").read_bytes())


if __name__ == "__main__":
    unittest.main()
