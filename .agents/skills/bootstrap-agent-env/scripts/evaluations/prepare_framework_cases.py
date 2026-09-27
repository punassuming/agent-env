"""Create realistic framework combinations for agent bootstrap trials."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


ENV = '''# Evaluation environment

Linux bash; Python 3.12, Node 24, npm 11 and Git are on PATH. Django, Angular CLI,
Express, Sails, React Router and Vite packages are not installed in the projects.
No network/package downloads or external deployment during this trial. This is an
instruction, not a process sandbox; host caches may have unrelated packages.
All fixture Git repositories start clean and writable. Inspect manifests before
choosing commands. CI may install declared dependencies. Distinguish syntax/static
checks from actual framework tests and builds; record blocked capabilities.
'''


def create(path: Path, files: dict[str, str]) -> None:
    path.mkdir(parents=True)
    for name, content in files.items():
        dest = path / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding='utf-8')
    subprocess.run(['git', 'init', '-q', str(path)], check=True)
    subprocess.run(['git', '-C', str(path), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(path), '-c', 'user.name=Fixture',
                    '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture'], check=True)


DJANGO_ANGULAR = {
    'EVAL_ENV.md': ENV,
    'README.md': 'Django API and Angular browser app in one Git repository. No lockfiles yet.\n',
    'backend/pyproject.toml': '[project]\nname="catalog-api"\nversion="0.1.0"\nrequires-python=">=3.11"\ndependencies=["Django>=5,<6"]\n',
    'backend/manage.py': 'import os\nimport sys\nif __name__ == "__main__":\n    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "catalog.settings")\n    from django.core.management import execute_from_command_line\n    execute_from_command_line(sys.argv)\n',
    'backend/catalog/__init__.py': '',
    'backend/catalog/settings.py': 'SECRET_KEY = "fixture-only"\nROOT_URLCONF = "catalog.urls"\nINSTALLED_APPS = []\nDATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}\n',
    'backend/catalog/urls.py': 'from django.http import JsonResponse\nfrom django.urls import path\n\ndef health(request):\n    return JsonResponse({"ok": True})\n\nurlpatterns = [path("health/", health)]\n',
    'backend/tests/__init__.py': '',
    'backend/tests/test_health.py': 'from django.test import SimpleTestCase\n\nclass HealthTests(SimpleTestCase):\n    def test_health(self):\n        response = self.client.get("/health/")\n        self.assertEqual(response.status_code, 200)\n',
    'frontend/package.json': json.dumps({'name': 'catalog-web', 'private': True, 'scripts': {'build': 'ng build', 'test': 'ng test --watch=false'}, 'dependencies': {'@angular/common': '^20.2.0', '@angular/compiler': '^20.2.0', '@angular/core': '^20.2.0', '@angular/platform-browser': '^20.2.0', 'rxjs': '^7.8.0', 'zone.js': '^0.15.0'}, 'devDependencies': {'@angular/cli': '^20.2.0', '@angular-devkit/build-angular': '^20.2.0', '@angular/compiler-cli': '^20.2.0', 'typescript': '~5.8.0', '@types/jasmine': '^5.0.0', 'jasmine-core': '^5.0.0', 'karma': '^6.0.0', 'karma-chrome-launcher': '^3.0.0', 'karma-jasmine': '^5.0.0'}}, indent=2) + '\n',
    'frontend/angular.json': json.dumps({'$schema': './node_modules/@angular/cli/lib/config/schema.json', 'version': 1, 'projects': {'catalog-web': {'projectType': 'application', 'root': '', 'sourceRoot': 'src', 'architect': {'build': {'builder': '@angular-devkit/build-angular:application', 'options': {'outputPath': 'dist/catalog-web', 'index': 'src/index.html', 'browser': 'src/main.ts', 'tsConfig': 'tsconfig.json'}}, 'test': {'builder': '@angular-devkit/build-angular:karma', 'options': {'main': 'src/test.ts', 'polyfills': ['zone.js', 'zone.js/testing'], 'tsConfig': 'tsconfig.json'}}}}}}, indent=2) + '\n',
    'frontend/tsconfig.json': '{"compilerOptions":{"target":"ES2022","module":"ES2022","moduleResolution":"bundler","experimentalDecorators":true,"strict":true,"types":["jasmine"]},"include":["src/**/*.ts"]}\n',
    'frontend/src/index.html': '<!doctype html><html><head><title>Catalog</title></head><body><app-root></app-root></body></html>\n',
    'frontend/src/main.ts': 'import { bootstrapApplication } from "@angular/platform-browser";\nimport { Component } from "@angular/core";\n@Component({selector: "app-root", standalone: true, template: "<h1>Catalog</h1>"})\nclass App {}\nbootstrapApplication(App);\n',
    'frontend/src/test.ts': 'import "zone.js/testing";\n',
    'frontend/src/app.spec.ts': 'describe("catalog", () => { it("starts", () => expect(2 + 2).toBe(4)); });\n',
}

EXPRESS_REACT = {
    'EVAL_ENV.md': ENV,
    'README.md': 'npm workspaces: Express API and React Router declarative-mode browser app. No lockfile yet.\n',
    'package.json': json.dumps({'name': 'express-react-workspace', 'private': True, 'workspaces': ['api', 'web'], 'scripts': {'test': 'npm run test --workspaces', 'build': 'npm run build --workspace=web'}}, indent=2) + '\n',
    'api/package.json': json.dumps({'name': 'catalog-api', 'private': True, 'type': 'module', 'scripts': {'test': 'node --test', 'build': 'node --check server.mjs'}, 'dependencies': {'express': '^5.0.0'}}, indent=2) + '\n',
    'api/server.mjs': 'import express from "express";\nconst app = express();\napp.get("/health", (_req, res) => res.json({ok: true}));\nexport default app;\n',
    'api/test/health.test.mjs': 'import { test } from "node:test";\nimport assert from "node:assert/strict";\nimport app from "../server.mjs";\ntest("health route is registered", () => { assert.ok(app._router || app.router); });\n',
    'web/package.json': json.dumps({'name': 'catalog-web', 'private': True, 'type': 'module', 'scripts': {'build': 'vite build', 'test': 'vitest run'}, 'dependencies': {'react': '^19.0.0', 'react-dom': '^19.0.0', 'react-router': '^7.0.0'}, 'devDependencies': {'vite': '^6.0.0', 'vitest': '^3.0.0'}}, indent=2) + '\n',
    'web/index.html': '<!doctype html><html><body><div id="root"></div><script type="module" src="/src/main.jsx"></script></body></html>\n',
    'web/src/main.jsx': 'import React from "react";\nimport { createRoot } from "react-dom/client";\nimport { BrowserRouter, Routes, Route } from "react-router";\nfunction App() { return <Routes><Route path="/" element={<h1>Catalog</h1>} /></Routes>; }\ncreateRoot(document.getElementById("root")).render(<BrowserRouter><App /></BrowserRouter>);\n',
    'web/src/app.test.js': 'import { describe, it, expect } from "vitest";\ndescribe("catalog", () => { it("starts", () => expect(2 + 2).toBe(4)); });\n',
}

SAILS_API = {
    'EVAL_ENV.md': ENV + '\nThis is the api Git repository. Its sibling ../web is a separate Git repository, also in scope.\n',
    'README.md': 'Sails API; sibling web is a separate repository. No lockfile yet.\n',
    'package.json': json.dumps({'name': 'harbor-api', 'private': True, 'scripts': {'start': 'sails lift', 'test': 'node --test'}, 'dependencies': {'sails': '^1.5.0'}}, indent=2) + '\n',
    'app.js': 'require("sails").lift({port: process.env.PORT || 1337});\n',
    'config/routes.js': 'module.exports.routes = {"GET /health": "HealthController.status"};\n',
    'api/controllers/HealthController.js': 'module.exports = {status: function (_req, res) {return res.json({ok: true});}};\n',
    'test/routes.test.js': 'const {test} = require("node:test");\nconst assert = require("node:assert/strict");\ntest("health route is mapped", () => { const routes = require("../config/routes").routes; assert.equal(routes["GET /health"], "HealthController.status"); });\n',
}

SAILS_WEB = {
    'EVAL_ENV.md': ENV + '\nThis is the web Git repository. Its sibling ../api is a separate Git repository, also in scope.\n',
    'README.md': 'React Router declarative-mode Vite app; sibling api is an independent Sails repository. No lockfile yet.\n',
    'package.json': json.dumps({'name': 'harbor-web', 'private': True, 'type': 'module', 'scripts': {'build': 'vite build', 'test': 'vitest run'}, 'dependencies': {'react': '^19.0.0', 'react-dom': '^19.0.0', 'react-router': '^7.0.0'}, 'devDependencies': {'vite': '^6.0.0', 'vitest': '^3.0.0'}}, indent=2) + '\n',
    'index.html': '<!doctype html><html><body><div id="root"></div><script type="module" src="/src/main.jsx"></script></body></html>\n',
    'src/main.jsx': EXPRESS_REACT['web/src/main.jsx'],
    'src/app.test.js': EXPRESS_REACT['web/src/app.test.js'],
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    create(root / 'django-angular', DJANGO_ANGULAR)
    create(root / 'express-react-router', EXPRESS_REACT)
    split = root / 'sails-react-router-split'
    split.mkdir()
    (split / 'EVAL_ENV.md').write_text(ENV + '\nThe api/ and web/ child directories are separate Git repositories. Both are in scope.\n')
    create(split / 'api', SAILS_API)
    create(split / 'web', SAILS_WEB)
    cases = {name: {'target': str(root / name), 'prompt': ''} for name in
             ('django-angular', 'express-react-router', 'sails-react-router-split')}
    (root / 'run_manifest.json').write_text(json.dumps({'cases': cases, 'isolation':
        'Shared host; project scope/network limits are instructions, not OS isolation'}, indent=2) + '\n')
    print(json.dumps({'output': str(root), 'cases': sorted(cases)}))


if __name__ == '__main__':
    main()
