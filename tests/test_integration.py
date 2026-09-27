import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from agent_env.bootstrap import discover, finalize, install
from agent_env.runtime import load_registry, run_command
from agent_env import VERSION


class BootstrapIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)

    def test_monorepo_detection_and_preserved_edits(self):
        api = self.repo / "apps" / "api"
        api.mkdir(parents=True)
        (api / "go.mod").write_text("module example.com/api\n\ngo 1.22\n")
        web = self.repo / "apps" / "web"
        web.mkdir()
        (web / "package.json").write_text('{"scripts":{"test":"node test.js"}}')
        (web / "package-lock.json").write_text("{}")
        self.assertEqual(set(discover(self.repo)), {"apps-api", "apps-web"})
        install(self.repo, discover(self.repo))
        self.assertTrue((self.repo / ".agents" / "skills" / "repo-agent-workflow" / "SKILL.md").is_file())
        record = json.loads((self.repo / ".agents" / "bootstrap.json").read_text())
        self.assertEqual(record["pending_version"], VERSION)
        self.assertNotIn("applied_version", record)
        path = self.repo / ".agents" / "commands.json"
        registry = json.loads(path.read_text())
        registry["components"]["apps-api"]["commands"]["test"] = [{"argv": [sys.executable, "-c", "print('local')"]}]
        path.write_text(json.dumps(registry))
        install(self.repo, discover(self.repo))
        self.assertEqual(load_registry(self.repo)["components"]["apps-api"]["commands"]["test"][0]["argv"][1], "-c")
        self.assertIn("/.local/", (self.repo / ".gitignore").read_text())

    def test_runtime_upgrade_preserves_edits_and_uses_managed_receipt(self):
        install(self.repo, {})
        runner = self.repo / '.agents/bin/runtime.py'
        receipt = self.repo / '.agents/runtime-deployment.json'
        original = runner.read_bytes()
        self.assertEqual(json.loads(receipt.read_text())['source_version'], VERSION)
        # Simulate an older unchanged managed runner and its receipt.
        runner.write_text('# old managed runner\n')
        import hashlib
        receipt.write_text(json.dumps({'schema_version': 1, 'source_version': 'old',
                                       'installed_sha256': hashlib.sha256(runner.read_bytes()).hexdigest()}))
        actions = install(self.repo, {})
        self.assertIn('Updated unchanged .agents/bin/runtime.py', actions)
        self.assertEqual(runner.read_bytes(), original)
        runner.write_text('# local adaptation\n')
        actions = install(self.repo, {})
        self.assertIn('Review .agents/bin/runtime.py: local or untracked changes preserved', actions)
        self.assertEqual(runner.read_text(), '# local adaptation\n')

    def test_failures_and_finalize(self):
        (self.repo / "go.mod").write_text("module example.com/test\n\ngo 1.22\n")
        install(self.repo, discover(self.repo))
        registry = load_registry(self.repo)
        component = registry["components"]["root"]
        component["tools"] = ["go"]
        component["commands"] = {"validate": [{"argv": [sys.executable, "-c", "raise SystemExit(7)"]}]}
        (self.repo / ".agents" / "commands.json").write_text(json.dumps(registry))
        self.assertEqual(run_command(self.repo, registry, "validate", None, True), 7)
        with self.assertRaisesRegex(ValueError, "doctor failed|validate failed"):
            finalize(self.repo)
        self.assertNotIn("applied_version", json.loads((self.repo / ".agents" / "bootstrap.json").read_text()))
        component["commands"]["validate"] = [{"argv": [sys.executable, "-c", "print('passed')"]}]
        (self.repo / ".agents" / "commands.json").write_text(json.dumps(registry))
        finalize(self.repo)
        record = json.loads((self.repo / ".agents" / "bootstrap.json").read_text())
        self.assertEqual(record["applied_version"], VERSION)
        self.assertNotIn("pending_version", record)
        self.assertTrue((self.repo / ".local" / "cache" / "go-build").is_dir())

    def test_tracked_local_is_preserved(self):
        (self.repo / "go.mod").write_text("module example.com/test\n\ngo 1.22\n")
        tracked = self.repo / ".local" / "config.json"
        tracked.parent.mkdir()
        tracked.write_text("{}")
        subprocess.run(["git", "-C", str(self.repo), "add", ".local/config.json"], check=True)
        install(self.repo, discover(self.repo))
        record = json.loads((self.repo / ".agents" / "bootstrap.json").read_text())
        self.assertEqual(record["local_root"], ".agent-local")
        self.assertTrue(tracked.exists())
        self.assertNotIn("/.local/", (self.repo / ".gitignore").read_text())

    def test_unknown_toolchain_can_be_adapted_but_not_finalized_empty(self):
        (self.repo / "justfile").write_text("test:\n    echo placeholder\n")
        self.assertEqual(discover(self.repo), {})
        install(self.repo, {})
        self.assertTrue((self.repo / ".agents/skills/bootstrap-agent-env/SKILL.md").is_file())
        with self.assertRaisesRegex(ValueError, "real validate steps"):
            finalize(self.repo)
        record = json.loads((self.repo / ".agents/bootstrap.json").read_text())
        self.assertEqual(record["pending_version"], VERSION)
        registry = load_registry(self.repo)
        registry["components"]["root"] = {"path": ".", "tools": ["python"], "evidence": ["justfile"],
            "commands": {"validate": [{"argv": [sys.executable, "-c", "print('custom check')"]}]}}
        (self.repo / ".agents/commands.json").write_text(json.dumps(registry))
        finalize(self.repo)
        self.assertEqual(json.loads((self.repo / ".agents/bootstrap.json").read_text())["applied_version"], VERSION)

    def test_polyglot_component_keeps_each_toolchain(self):
        (self.repo / "Cargo.toml").write_text("[package]\nname='example'\nversion='0.1.0'\n")
        (self.repo / "go.mod").write_text("module example.com/test\n\ngo 1.22\n")
        candidate = discover(self.repo)["root"]["commands"]
        self.assertEqual(len(candidate["test"]), 2)
        self.assertEqual(len(candidate["validate"]), 7)

    def test_pnpm_workspace_children_use_parent_manager(self):
        (self.repo / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n")
        (self.repo / "package.json").write_text('{"scripts":{"build":"echo root"}}')
        child = self.repo / "packages" / "client"
        child.mkdir(parents=True)
        (child / "package.json").write_text('{"scripts":{"test":"echo child"}}')
        found = discover(self.repo)
        self.assertEqual(found["packages-client"]["commands"]["test"][0]["argv"][0], "pnpm")
        self.assertNotIn("bootstrap", found["packages-client"]["commands"])

    def test_cli_end_to_end_from_clean_target(self):
        (self.repo / "package.json").write_text('{"scripts":{"test":"node test.js"}}')
        (self.repo / "package-lock.json").write_text("{}")
        source = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, "-m", "agent_env", "install", str(self.repo)], cwd=source,
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        runner = self.repo / ".agents" / "bin" / "runtime.py"
        help_result = subprocess.run([sys.executable, str(runner), "list", "--json"], cwd=self.repo,
                                     capture_output=True, text=True, check=False)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("root", json.loads(help_result.stdout)["components"])
        # Installed skill remains runnable without the source package on PYTHONPATH.
        standalone = self.repo / ".agents/skills/bootstrap-agent-env/scripts/bootstrap.py"
        isolated_env = os.environ.copy()
        isolated_env.pop("PYTHONPATH", None)
        assessed = subprocess.run([sys.executable, str(standalone), "assess", str(self.repo)],
                                  cwd=self.repo, env=isolated_env, capture_output=True, text=True)
        self.assertEqual(assessed.returncode, 0, assessed.stderr)
        self.assertIn("root", json.loads(assessed.stdout)["components"])
        installed_registry = self.repo / ".agents/skills/bootstrap-agent-env/scripts/registry.py"
        extra = self.repo / ".agents/skills/new-tool/SKILL.md"
        extra.parent.mkdir(parents=True)
        extra.write_text("---\nname: new-tool\ndescription: Local addition\n---\n")
        registry_result = subprocess.run([sys.executable, str(installed_registry), "install", str(self.repo)],
                                         cwd=self.repo, env=isolated_env, capture_output=True, text=True)
        self.assertEqual(registry_result.returncode, 0, registry_result.stderr)
        self.assertIn("new-tool", json.loads(registry_result.stdout)["selected"])
        if os.name == "nt" and shutil.which("pwsh"):
            wrapper = ["pwsh", "-NoProfile", "-File", str(self.repo / "scripts" / "agent-env.ps1")]
        elif os.name != "nt":
            wrapper = ["bash", str(self.repo / "scripts" / "agent-env.sh")]
        else:
            return
        wrapped = subprocess.run(wrapper + ["list", "--json"], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(wrapped.returncode, 0, wrapped.stderr)
        self.assertIn("root", json.loads(wrapped.stdout)["components"])

    def test_missing_command_is_failure_and_no_shell_interpolation(self):
        (self.repo / "go.mod").write_text("module example.com/test\n\ngo 1.22\n")
        install(self.repo, discover(self.repo))
        registry = load_registry(self.repo)
        self.assertEqual(run_command(self.repo, registry, "deploy", None, True), 2)
        marker = self.repo / "bad-file"
        registry["components"]["root"]["commands"]["test"] = [{"argv": [sys.executable, "-c", "print('x')", ";touch bad-file"]}]
        self.assertEqual(run_command(self.repo, registry, "test", None, True), 0)
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
