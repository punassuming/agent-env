"""End-to-end pnpm workspace scenario for the agent-env bootstrap.

Run from the source checkout with:
    python tests/scenarios/test_node_pnpm.py -v

The temporary repo and synthetic pnpm executable keep the scenario offline.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE))

from agent_env.bootstrap import discover, install  # noqa: E402


@unittest.skipIf(os.name == "nt", "synthetic pnpm shim uses a POSIX shebang")
class PnpmWorkspaceScenario(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self.bin = Path(self.temp.name) / "bin"
        self.bin.mkdir()
        self.log = Path(self.temp.name) / "pnpm.jsonl"
        self._write("pnpm-workspace.yaml", "packages:\n  - 'packages/*'\n")
        self._write("pnpm-lock.yaml", "lockfileVersion: '9.0'\n")
        self._write("package.json", json.dumps({"name": "workspace", "private": True,
                                                "scripts": {"build": "echo root-build"}}))
        self._package("packages/web", "web", {"test": "echo web-test", "build": "echo web-build"})
        self._package("packages/api", "api", {"test": "echo api-test"})

        shim = self.bin / "pnpm"
        shim.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            "with open(os.environ['PNPM_SCENARIO_LOG'], 'a') as f:\n"
            " f.write(json.dumps({'cwd': os.getcwd(), 'argv': sys.argv[1:]})+'\\n')\n"
            "raise SystemExit(int(os.environ.get('PNPM_SCENARIO_EXIT', '0')))\n"
        )
        shim.chmod(0o755)
        self.env = os.environ.copy()
        self.env["PATH"] = str(self.bin) + os.pathsep + self.env.get("PATH", "")
        self.env["PNPM_SCENARIO_LOG"] = str(self.log)

    def _write(self, relative, content):
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def _package(self, relative, name, scripts):
        self._write(f"{relative}/package.json", json.dumps({"name": name, "scripts": scripts}))

    def _runner(self, command, *args, env=None):
        return subprocess.run([sys.executable, str(self.repo / ".agents/bin/runtime.py"), command, *args],
                              cwd=self.repo, env=env or self.env, capture_output=True, text=True)

    def _calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_assess_install_and_validate_root_lockfile_workspace(self):
        proposed = discover(self.repo)
        self.assertEqual(set(proposed), {"root", "packages-api", "packages-web"})
        for name in proposed:
            self.assertIn("pnpm", proposed[name]["tools"], name)
        self.assertEqual(proposed["root"]["commands"]["bootstrap"][0]["argv"],
                         ["pnpm", "install", "--frozen-lockfile"])
        # Child bootstrap delegates to the root lockfile workspace.
        self.assertNotIn("bootstrap", proposed["packages-api"]["commands"])
        self.assertEqual(proposed["packages-api"]["bootstrap_from"], "root")
        self.assertEqual(proposed["packages-api"]["commands"]["test"][0]["argv"],
                         ["pnpm", "run", "test"])
        self.assertEqual(proposed["packages-web"]["commands"]["build"][0]["argv"],
                         ["pnpm", "run", "build"])

        install(self.repo, proposed)
        installed = json.loads((self.repo / ".agents/commands.json").read_text())
        self.assertEqual(set(installed["components"]), set(proposed))
        self.assertEqual(self._runner("doctor", "--json").returncode, 0)

        # Install dependencies once from workspace root, then run each
        # deterministic script. This verifies nested package cwd handling and
        # preserves pnpm's argv without a shell.
        result = self._runner("bootstrap", "--all")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self._runner("validate", "--all")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self._calls()
        self.assertEqual(sum(c["argv"] == ["install", "--frozen-lockfile"] for c in calls), 1)
        script_calls = [c for c in calls if len(c["argv"]) >= 2 and c["argv"][0] == "run"]
        self.assertEqual({Path(c["cwd"]).relative_to(self.repo).as_posix() for c in script_calls},
                         {".", "packages/api", "packages/web"})
        self.assertEqual({tuple(c["argv"]) for c in script_calls},
                         {("run", "build"), ("run", "test")})



if __name__ == "__main__":
    unittest.main()
