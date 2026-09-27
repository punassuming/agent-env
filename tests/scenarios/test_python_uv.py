"""End-to-end uv workspace bootstrap scenario with a synthetic uv executable.

Run from the agent-env checkout with:
    python -m unittest discover -s tests/scenarios -v

The fake executable makes the scenario deterministic on hosts without uv and
records the exact invocations made by the installed runner.
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
from agent_env import VERSION


@unittest.skipIf(os.name == "nt", "synthetic uv shim uses a POSIX shebang")
class PythonUvMonorepoScenario(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.repo = self.work / "service-repo"
        self.repo.mkdir()
        self.bin = self.work / "bin"
        self.bin.mkdir()
        self.log = self.work / "uv-calls.jsonl"

        # A uv workspace with one installable service package and a root-level
        # lint configuration. The lockfile belongs at the workspace root.
        (self.repo / "pyproject.toml").write_text(
            "[tool.uv.workspace]\nmembers = [\"packages/*\"]\n\n"
            "[tool.ruff]\nline-length = 100\n", encoding="utf-8")
        (self.repo / "uv.lock").write_text("version = 1\n", encoding="utf-8")
        service = self.repo / "packages" / "api"
        (service / "tests").mkdir(parents=True)
        (service / "pyproject.toml").write_text(
            "[project]\nname = \"example-api\"\nversion = \"0.1.0\"\n"
            "requires-python = \">=3.11\"\n", encoding="utf-8")
        (service / "tests" / "test_smoke.py").write_text("def test_smoke():\n    assert True\n", encoding="utf-8")

        uv = self.bin / "uv"
        uv.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "with open(os.environ['UV_SCENARIO_LOG'], 'a', encoding='utf-8') as f:\n"
            "    f.write(json.dumps({'cwd': os.getcwd(), 'argv': sys.argv[1:]}) + '\\n')\n"
            "raise SystemExit(int(os.environ.get('UV_SCENARIO_EXIT', '0')))\n",
            encoding="utf-8")
        uv.chmod(uv.stat().st_mode | 0o111)
        self.env = os.environ.copy()
        self.env["PATH"] = str(self.bin) + os.pathsep + self.env.get("PATH", "")
        self.env["UV_SCENARIO_LOG"] = str(self.log)

    def run_cli(self, mode, *args):
        return subprocess.run([sys.executable, "-m", "agent_env", mode, *map(str, args)],
                              cwd=SOURCE, env=self.env, capture_output=True, text=True, check=False)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()] if self.log.exists() else []

    def test_assess_install_validate_and_finalize_workspace(self):
        assessed = self.run_cli("assess", self.repo)
        self.assertEqual(assessed.returncode, 0, assessed.stderr)
        report = json.loads(assessed.stdout)
        components = report["components"]
        self.assertEqual(set(components), {"root", "packages-api"})
        root = components["root"]
        self.assertIn("uv.lock", root["evidence"])
        self.assertIn("uv", root["tools"])
        self.assertEqual(root["commands"]["bootstrap"][0]["argv"], ["uv", "sync", "--locked"])
        service = components["packages-api"]
        self.assertEqual(service["bootstrap_from"], "root")
        self.assertEqual(service["commands"]["test"][0]["argv"], ["uv", "run", "--locked", "pytest"])

        installed = self.run_cli("install", self.repo)
        self.assertEqual(installed.returncode, 0, installed.stderr)
        registry_path = self.repo / ".agents" / "commands.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        self.assertEqual(set(registry["components"]), {"root", "packages-api"})

        # Exercise the copied, repository-owned runner, not the source package.
        runner = self.repo / ".agents" / "bin" / "runtime.py"
        bootstrapped = subprocess.run([sys.executable, str(runner), "bootstrap", "--component", "root"],
                                      cwd=self.repo, env=self.env, capture_output=True, text=True, check=False)
        self.assertEqual(bootstrapped.returncode, 0, bootstrapped.stderr)
        validated = subprocess.run([sys.executable, str(runner), "validate", "--component", "root"],
                                   cwd=self.repo, env=self.env, capture_output=True, text=True, check=False)
        self.assertEqual(validated.returncode, 0, validated.stderr)
        invocations = self.calls()
        self.assertIn(["sync", "--locked"], [item["argv"] for item in invocations])
        self.assertIn(["run", "--locked", "ruff", "check", "."], [item["argv"] for item in invocations])
        all_validated = subprocess.run([sys.executable, str(runner), "validate", "--all"],
                                       cwd=self.repo, env=self.env, capture_output=True, text=True, check=False)
        self.assertEqual(all_validated.returncode, 0, all_validated.stderr)
        self.assertTrue((self.repo / ".local" / "cache" / "uv").is_dir())

        finalized = self.run_cli("finalize", self.repo)
        self.assertEqual(finalized.returncode, 0, finalized.stderr)
        record = json.loads((self.repo / ".agents" / "bootstrap.json").read_text(encoding="utf-8"))
        self.assertEqual(record["applied_version"], VERSION)
        self.assertNotIn("pending_version", record)

    def test_validation_propagates_synthetic_uv_failure(self):
        installed = self.run_cli("install", self.repo)
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.env["UV_SCENARIO_EXIT"] = "9"
        runner = self.repo / ".agents" / "bin" / "runtime.py"
        result = subprocess.run([sys.executable, str(runner), "validate", "--component", "root"],
                                cwd=self.repo, env=self.env, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertIn("FAILED root:validate", result.stderr)


if __name__ == "__main__":
    unittest.main()
