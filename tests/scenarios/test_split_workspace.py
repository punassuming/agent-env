"""End-to-end scenario for two independently bootstrapped workspace repositories.

Run from the agent-env checkout with:
    python -m unittest discover -s tests -v
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from agent_env.bootstrap import discover, finalize, install


SOURCE = Path(__file__).resolve().parents[2]
COORDINATOR = SOURCE / "scripts" / "workspace.py"


class SplitWorkspaceScenario(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.go_repo = self._repo("go-service", "go.mod", "module example.com/service\n\ngo 1.22\n")
        self.rust_repo = self._repo("rust-tool", "Cargo.toml", "[package]\nname='tool'\nversion='0.1.0'\n")
        self.trace = self.workspace / "trace.jsonl"
        self._bootstrap(self.go_repo, "go")
        self._bootstrap(self.rust_repo, "rust")
        self.manifest = self.workspace / "workspace.json"
        self.manifest.write_text(json.dumps({"projects": {
            "service": "go-service",
            "tool": "rust-tool",
        }}))

    def _repo(self, name, marker, content):
        repo = self.workspace / name
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / marker).write_text(content)
        return repo

    def _bootstrap(self, repo, expected_tool):
        found = discover(repo)
        self.assertEqual(set(found), {"root"})
        component = found["root"]
        self.assertEqual(component["tools"], [expected_tool])
        install(repo, found)
        # Use a deterministic fake command so this scenario does not depend on
        # a local Go/Rust installation or run project code.
        recorder = (
            "import json, os; "
            "p=os.environ.get('TRACE_FILE'); "
            "p and open(p, 'a').write(json.dumps({"
            "'cwd': os.getcwd(), 'root': os.environ['AGENT_ENV_ROOT'], "
            "'cache': os.environ.get('GOCACHE') or os.environ.get('CARGO_TARGET_DIR')})+'\\n')"
        )
        registry_path = repo / ".agents" / "commands.json"
        registry = json.loads(registry_path.read_text())
        registry["components"]["root"]["commands"] = {
            "doctor": [{"argv": [sys.executable, "-c", "pass"]}],
            "validate": [{"argv": [sys.executable, "-c", recorder]}],
            "test": [
                {"argv": [sys.executable, "-c", recorder]},
                {"argv": [sys.executable, "-c", "pass"]},
            ],
            "build": [{"argv": [sys.executable, "-c", "pass"]}],
            "lint": [{"argv": [sys.executable, "-c", "pass"]}],
        }
        registry_path.write_text(json.dumps(registry))
        finalize(repo)

    def _run_coordinator(self, command, *projects):
        env = os.environ.copy()
        env["TRACE_FILE"] = str(self.trace)
        argv = [sys.executable, str(COORDINATOR), command, "--manifest", str(self.manifest)]
        for project in projects:
            argv += ["--project", project]
        return subprocess.run(argv, cwd=self.workspace, env=env, capture_output=True, text=True)

    def test_separate_repositories_bootstrap_and_validate_independently(self):
        for repo in (self.go_repo, self.rust_repo):
            record = json.loads((repo / ".agents" / "bootstrap.json").read_text())
            self.assertTrue(record.get("applied_version"))
            self.assertNotIn("pending_version", record)
            registry = json.loads((repo / ".agents" / "commands.json").read_text())
            self.assertEqual(set(registry["components"]), {"root"})

        result = self._run_coordinator("validate")
        self.assertEqual(result.returncode, 0, result.stderr)
        records = [json.loads(line) for line in self.trace.read_text().splitlines()]
        self.assertEqual({Path(r["cwd"]) for r in records}, {self.go_repo, self.rust_repo})
        self.assertEqual({Path(r["root"]) for r in records}, {self.go_repo, self.rust_repo})
        self.assertTrue(all(r["cache"] for r in records))
        self.assertEqual({Path(r["cache"]) for r in records}, {
            self.go_repo / ".local" / "cache" / "go-build",
            self.rust_repo / ".local" / "cache" / "cargo-target",
        })

    def test_malformed_manifest_reports_error(self):
        self.manifest.write_text('{"projects": ["wrong-shape"]}')
        result = self._run_coordinator("validate")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("projects mapping", result.stderr)

    def test_project_selection_and_command_failure_propagate(self):
        result = self._run_coordinator("test", "tool")
        self.assertEqual(result.returncode, 0, result.stderr)
        records = [json.loads(line) for line in self.trace.read_text().splitlines()]
        self.assertEqual({Path(r["cwd"]) for r in records}, {self.rust_repo})

        # A missing runner in one project should be reported while the other
        # project still runs, with the coordinator returning failure.
        (self.go_repo / ".agents" / "bin" / "runtime.py").unlink()
        self.trace.write_text("")
        result = self._run_coordinator("validate")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing runner", result.stderr)
        records = [json.loads(line) for line in self.trace.read_text().splitlines()]
        self.assertEqual({Path(r["cwd"]) for r in records}, {self.rust_repo})


if __name__ == "__main__":
    unittest.main()
