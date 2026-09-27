import json
from pathlib import Path
import tempfile
import unittest

from agent_env.registry import deploy


class RegistryTests(unittest.TestCase):
    def test_additional_skill_and_agent_safe_upgrade(self):
        with tempfile.TemporaryDirectory() as root:
            source, target = Path(root) / "source", Path(root) / "target"
            source.mkdir()
            target.mkdir()
            skill = source / ".agents/skills/new-tool/SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("---\nname: new-tool\ndescription: Demo\n---\n", encoding="utf-8")
            agent = source / "registry/agents/helper.md"
            agent.parent.mkdir(parents=True)
            agent.write_text("agent instructions\n", encoding="utf-8")
            manifest = source / ".agents/registry.json"
            manifest.write_text(json.dumps({"schema_version": 1, "skills": {"new-tool": {
                "source": ".agents/skills/new-tool", "version": "1.0.0", "default": True,
                "destinations": [".agents/skills/new-tool"]}}, "agents": {"helper": {
                "source": "registry/agents/helper.md", "version": "1.0.0", "default": True,
                "destinations": [".claude/agents/helper.md"]}}}))
            self.assertEqual(len(deploy(source, target)["changes"]), 3)
            self.assertEqual(len(deploy(source, target, write=True)["changes"]), 3)
            self.assertFalse(deploy(source, target, write=True)["changes"])
            skill.write_text("upstream revision\n")
            self.assertEqual(len(deploy(source, target, write=True)["changes"]), 1)
            installed = target / ".agents/skills/new-tool/SKILL.md"
            installed.write_text("local revision\n")
            skill.write_text("second revision\n")
            report = deploy(source, target, write=True)
            self.assertEqual(report["conflicts"], [".agents/skills/new-tool/SKILL.md"])
            self.assertEqual(installed.read_text(), "local revision\n")
            self.assertEqual((target / ".claude/agents/helper.md").read_text(), "agent instructions\n")
            self.assertEqual(deploy(source, target, selected={"helper"})["selected"], ["helper"])
            with self.assertRaisesRegex(ValueError, "Unknown registry items"):
                deploy(source, target, selected={"absent"})

    def test_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            source, target = Path(root) / "source", Path(root) / "target"
            source.mkdir()
            target.mkdir()
            (source / ".agents").mkdir()
            (source / ".agents/registry.json").write_text(json.dumps({"schema_version": 1,
                "skills": {"bad": {"source": "../outside", "destinations": [".agents/skills/bad"]}}, "agents": {}}))
            with self.assertRaisesRegex(ValueError, "Unsafe registry path"):
                deploy(source, target)

class AutoDiscoveryTests(unittest.TestCase):
    def test_new_skill_and_provider_agent_deploy_without_manifest_entry(self):
        with tempfile.TemporaryDirectory() as root:
            source, target = Path(root) / "source", Path(root) / "target"
            (source / ".agents/skills/custom").mkdir(parents=True)
            (source / ".agents/skills/custom/SKILL.md").write_text("---\nname: custom\n---\n")
            (source / ".agents/agents/claude").mkdir(parents=True)
            (source / ".agents/agents/claude/inspect.md").write_text("inspect\n")
            (source / ".agents/registry.json").write_text(json.dumps({
                "schema_version": 1, "skills": {}, "agents": {}}))
            target.mkdir()
            report = deploy(source, target, write=True)
            self.assertEqual(len(report["changes"]), 4)
            self.assertTrue((target / ".agents/skills/custom/SKILL.md").is_file())
            self.assertEqual((target / ".claude/agents/inspect.md").read_text(), "inspect\n")
