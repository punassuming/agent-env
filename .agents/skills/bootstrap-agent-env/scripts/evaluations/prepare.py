"""Create controlled, offline-capable projects for independent skill evaluations.

Usage: python .agents/skills/bootstrap-agent-env/scripts/evaluations/prepare.py [--output PATH]
Generated projects are disposable. Each contains an EVAL_ENV.md describing what
is provided to the agent; the script's summary records actual host capabilities.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


SKILL = Path(__file__).resolve().parents[5] / '.agents/skills/bootstrap-agent-env/SKILL.md'
DEFAULT_OUTPUT = Path(__file__).resolve().parents[5] / '.local/evals_controlled'


def project(root: Path, files: dict[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=Fixture',
                    '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture'], check=True)


def version(argv: list[str]) -> str:
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=10, check=True)
        return result.stdout.strip().splitlines()[0]
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return 'unavailable'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error(f'{output} is not empty; use a fresh directory to preserve prior agent outputs')
    output.mkdir(parents=True, exist_ok=True)
    tools = {'python': version([sys.executable, '--version']), 'node': version(['node', '--version']),
             'npm': version(['npm', '--version']), 'git': version(['git', '--version'])}
    required = {name: tools[name] for name in ('python', 'node', 'npm', 'git') if tools[name] == 'unavailable'}
    if required:
        parser.error('Required real toolchains unavailable: ' + ', '.join(required))
    common = ("This is a disposable evaluation checkout with a clean initial Git commit. "
              "Use the bootstrap skill to assess and adapt it. Toolchains are already present. "
              "Do not install replacement tools or fetch packages: every initial test/build is offline. "
              "Keep cache and temporary output inside this checkout when practical. "
              "Do not deploy to an external service. Record observed outcomes, not assumed passes.\n")
    py = {
        'pyproject.toml': '[project]\nname="eval-calc"\nversion="0.1.0"\nrequires-python=">=3.11"\n',
        'calc.py': 'def add(left: int, right: int) -> int:\n    return left + right\n',
        'tests/test_calc.py': 'import unittest\nfrom calc import add\n\nclass CalcTests(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n',
        'README.md': 'Python library. Run `python -m unittest discover -s tests`. No deployment target.\n',
        'EVAL_ENV.md': '# Evaluation environment\n\n' + common + 'Python stdlib and unittest are available. No third-party lint dependency is declared.\n',
    }
    project(output / 'python-library', py)
    node = {
        'package.json': '{"name":"eval-node","private":true,"scripts":{"test":"node --test","lint":"node --check src/index.js","build":"node scripts/build.js"}}\n',
        'package-lock.json': '{"name":"eval-node","lockfileVersion":3,"requires":true,"packages":{"":{"name":"eval-node"}}}\n',
        'src/index.js': 'export const double = (value) => value * 2;\n',
        'test/index.test.js': "import test from 'node:test';\nimport assert from 'node:assert/strict';\nimport { double } from '../src/index.js';\ntest('double', () => assert.equal(double(4), 8));\n",
        'scripts/build.js': "import { mkdirSync, copyFileSync } from 'node:fs';\nmkdirSync('dist', { recursive: true });\ncopyFileSync('src/index.js', 'dist/index.js');\n",
        'README.md': 'Node app. `npm test`, `npm run lint`, and `npm run build` require no downloads.\n',
        'EVAL_ENV.md': '# Evaluation environment\n\n' + common + 'Node and npm are available. The build writes `dist/`; inspect whether it should be ignored.\n',
    }
    project(output / 'node-app', node)
    mono = {
        'package.json': '{"name":"eval-workspace","private":true,"workspaces":["packages/*"],"scripts":{"test":"node --test packages/*/test/*.test.js"}}\n',
        'package-lock.json': '{"name":"eval-workspace","lockfileVersion":3,"requires":true,"packages":{"":{"name":"eval-workspace","workspaces":["packages/*"]},"packages/ui":{"name":"eval-ui","version":"1.0.0"}}}\n',
        'packages/ui/package.json': '{"name":"eval-ui","version":"1.0.0","type":"module","scripts":{"test":"node --test","lint":"node --check src/index.js"}}\n',
        'packages/ui/src/index.js': 'export const label = (name) => `Hello ${name}`;\n',
        'packages/ui/test/ui.test.js': "import test from 'node:test';\nimport assert from 'node:assert/strict';\nimport { label } from '../src/index.js';\ntest('label', () => assert.equal(label('Ada'), 'Hello Ada'));\n",
        'services/api/pyproject.toml': '[project]\nname="eval-api"\nversion="0.1.0"\n',
        'services/api/api.py': 'def status():\n    return 200\n',
        'services/api/tests/test_api.py': 'import unittest\nfrom api import status\n\nclass ApiTests(unittest.TestCase):\n    def test_status(self):\n        self.assertEqual(status(), 200)\n',
        'README.md': 'Node workspace plus a Python service. Validate both components.\n',
        'EVAL_ENV.md': '# Evaluation environment\n\n' + common + 'Both Node and Python are installed. The Python service is in `services/api`.\n',
    }
    project(output / 'mixed-monorepo', mono)
    space = output / 'split-workspace'
    space.mkdir()
    (space / 'workspace.json').write_text('{"projects":{"backend":"backend","frontend":"frontend"}}\n')
    (space / 'EVAL_ENV.md').write_text('# Evaluation environment\n\n' + common + 'The child paths are distinct Git repositories. Coordinate checks from this parent only when needed.\n')
    project(space / 'backend', py)
    project(space / 'frontend', node)
    entries = {}
    for name in ('python-library', 'node-app', 'mixed-monorepo', 'split-workspace'):
        target = output / name
        entries[name] = {'target': str(target), 'prompt': f'Use the skill at {SKILL} to bootstrap {target}. Read EVAL_ENV.md. Assess actual project capabilities, scaffold a repo-owned environment, verify meaningful checks, and document gaps. Only edit this target and its child repositories.'}
    (output / 'run_manifest.json').write_text(json.dumps({
        'schema_version': 1, 'skill': str(SKILL), 'host_tools': tools,
        'host_path': os.environ.get('PATH', ''),
        'isolation': 'shared agent runtime; project inputs and Git state controlled, filesystem/network policy not isolated',
        'cases': entries,
    }, indent=2) + '\n')
    print(json.dumps({'output': str(output), 'cases': list(entries), 'host_tools': tools,
                      'isolation': 'no per-agent filesystem or network isolation'}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
