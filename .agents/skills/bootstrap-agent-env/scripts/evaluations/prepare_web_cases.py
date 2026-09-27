"""Four deterministic FastAPI + pnpm/React evaluation starting states.

The application dependencies are declared but deliberately not installed in the
agent runtime. This exercises assessment of a real dependency boundary without
pretending a static check is an application integration test.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


REPO = Path(__file__).resolve().parents[5]
SKILL = REPO / '.agents/skills/bootstrap-agent-env/SKILL.md'
DEFAULT_OUTPUT = REPO / '.local/evals_web'


def files(root: Path, content: dict[str, str], *, git: bool = False) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for relative, text in content.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    if git:
        subprocess.run(['git', 'init', '-q', str(root)], check=True)
        subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(root), '-c', 'user.name=Fixture',
                        '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture'], check=True)


def backend() -> dict[str, str]:
    return {
        'backend/pyproject.toml': '''[project]
name = "eval-api"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["fastapi>=0.115,<1", "uvicorn>=0.30,<1"]
[dependency-groups]
dev = ["pytest>=8,<10", "httpx>=0.27,<1", "ruff>=0.9,<1"]
[tool.pytest.ini_options]
testpaths = ["tests"]
''',
        'backend/app/__init__.py': '',
        'backend/app/main.py': 'from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get("/health")\ndef health() -> dict[str, str]:\n    return {"status": "ok"}\n',
        'backend/tests/test_health.py': 'from fastapi.testclient import TestClient\nfrom app.main import app\n\ndef test_health():\n    response = TestClient(app).get("/health")\n    assert response.status_code == 200\n',
        'backend/scripts/static_check.py': 'import ast\nfrom pathlib import Path\nast.parse(Path("app/main.py").read_text())\nprint("Python source parses; integration tests require declared dependencies")\n',
    }


def web(*, at: str = '', placeholder: bool = False) -> dict[str, str]:
    prefix = f'{at}/' if at else ''
    out = {
        prefix + 'pnpm-workspace.yaml': 'packages:\n  - "apps/*"\n  - "packages/*"\n',
        prefix + 'package.json': json.dumps({'name': 'eval-web', 'private': True,
            'packageManager': 'pnpm@9.15.9', 'scripts': {'test': 'pnpm -r test',
            'lint': 'pnpm -r lint', 'build': 'pnpm -r build'}}, indent=2) + '\n',
        prefix + 'packages/ui/package.json': '{"name":"@eval/ui","version":"0.1.0","type":"module","exports":"./src/index.js","scripts":{"lint":"node --check src/index.js"}}\n',
        prefix + 'packages/ui/src/index.js': 'export const title = (name) => `Welcome ${name}`;\n',
    }
    for site in ('admin', 'store'):
        scripts = {'test': 'vitest run', 'lint': 'eslint .', 'build': 'vite build'}
        if placeholder and site == 'store':
            scripts['test'] = 'echo tests pass'
        out[prefix + f'apps/{site}/package.json'] = json.dumps({
            'name': f'@eval/{site}', 'private': True, 'type': 'module', 'scripts': scripts,
            'dependencies': {'react': '^19.0.0', 'react-dom': '^19.0.0', '@eval/ui': 'workspace:*'},
            'devDependencies': {'vite': '^6.0.0', 'vitest': '^3.0.0', 'eslint': '^9.0.0'}}, indent=2) + '\n'
        out[prefix + f'apps/{site}/index.html'] = f'<div id="root"></div><script type="module" src="/src/main.jsx"></script>\n'
        out[prefix + f'apps/{site}/src/main.jsx'] = f'''import React from 'react';
import {{ createRoot }} from 'react-dom/client';
import {{ title }} from '@eval/ui';
createRoot(document.getElementById('root')).render(<h1>{{title('{site}')}}</h1>);
'''
        out[prefix + f'apps/{site}/src/App.test.jsx'] = "import { test, expect } from 'vitest';\ntest('smoke', () => expect(2 + 2).toBe(4));\n"
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    base = args.output.resolve()
    if base.exists() and any(base.iterdir()):
        parser.error(f'{base} is not empty; use a fresh directory')
    base.mkdir(parents=True, exist_ok=True)
    environment = '''# Evaluation environment

Linux bash agent runtime. Available host CLIs: Python 3.12.14, uv, Node 24.19.0,
pnpm, npm 11.9.0, Git 2.51.1. FastAPI, React, Vite, Vitest, ESLint and Ruff
are declared by the project but **not installed locally**. The project starts
with a clean Git commit and an empty project cache. Do not fetch packages in
this evaluation; this is an instruction rather than an enforced network block.
Host-wide package caches may already contain packages. CI may provision dependencies.
Project files are writable. Each agent shares the host filesystem and network
policy; the restriction to this target is an evaluation instruction, not OS
isolation. Static checks are available but do not substitute for integration tests.
Work from repository evidence and report what could not be validated.
'''
    baseline = backend() | web()
    baseline['README.md'] = 'FastAPI in backend/. pnpm workspace has React admin and store apps plus shared UI.\n'
    baseline['EVAL_ENV.md'] = environment
    files(base / 'baseline', baseline, git=True)
    stale = dict(baseline)
    stale['apps/store/package.json'] = web(placeholder=True)['apps/store/package.json']
    stale['.github/workflows/test.yml'] = 'name: old-test\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - run: pnpm --filter @eval/admin test\n'
    stale['.agents/commands.json'] = '{"schema_version":1,"components":{"root":{"path":".","tools":["node"],"commands":{"validate":[{"argv":["pnpm","--filter","@eval/admin","test"]}]}}}}\n'
    stale['README.md'] = 'Existing partial CI and command registry. Check coverage of admin, store and backend.\n'
    files(base / 'stale-config', stale, git=True)
    nested = backend() | web(at='frontend')
    nested['compose.yaml'] = 'services:\n  backend:\n    build: ./backend\n  admin:\n    build: ./frontend/apps/admin\n  store:\n    build: ./frontend/apps/store\n'
    nested['Makefile'] = 'check:\n\tcd backend && python scripts/static_check.py\n'
    nested['README.md'] = 'Backend and separate frontend workspace under frontend/. Compose lists services.\n'
    nested['EVAL_ENV.md'] = environment
    files(base / 'nested-frontends', nested, git=True)
    split = base / 'split-repos'
    split.mkdir()
    (split / 'workspace.json').write_text('{"projects":{"api":"api","web":"web"}}\n')
    (split / 'EVAL_ENV.md').write_text(environment + '\napi/ and web/ are distinct Git repositories.\n')
    files(split / 'api', {p.removeprefix('backend/'): v for p, v in backend().items()} |
          {'README.md': 'FastAPI repository; the web checkout is a sibling.\n'}, git=True)
    files(split / 'web', web() | {'README.md': 'Two React sites and shared UI; API is a sibling checkout.\n'}, git=True)
    cases = {}
    for name in ('baseline', 'stale-config', 'nested-frontends', 'split-repos'):
        root = base / name
        cases[name] = {'target': str(root), 'prompt': f'Use the bootstrap-agent-env skill at {SKILL} to bootstrap {root}. Read EVAL_ENV.md first. Assess the actual FastAPI and pnpm React projects, adapt commands/skills/CI, validate what is possible, and report remaining gaps. Only edit this target and its child repositories.'}
    (base / 'run_manifest.json').write_text(json.dumps({'schema_version': 1, 'cases': cases,
        'skill': str(SKILL), 'host_python': sys.version.split()[0], 'host_path': os.environ.get('PATH', ''),
        'sandbox': 'shared agent tool runtime; path/network scope cannot be isolated by prompt'}, indent=2) + '\n')
    print(json.dumps({'output': str(base), 'cases': list(cases)}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
