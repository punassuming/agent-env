"""Generate independent, toolchain-specific skill evaluation repositories."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


SOURCE = Path(__file__).resolve().parents[5]
SKILL = SOURCE / '.agents/skills/bootstrap-agent-env/SKILL.md'
DEFAULT = SOURCE / '.local/evals_stacks'


def create(path: Path, entries: dict[str, str]) -> None:
    path.mkdir(parents=True)
    for relative, content in entries.items():
        item = path / relative
        item.parent.mkdir(parents=True, exist_ok=True)
        item.write_text(content)
        if relative == 'gradlew':
            item.chmod(0o755)
    subprocess.run(['git', 'init', '-q', str(path)], check=True)
    subprocess.run(['git', '-C', str(path), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(path), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                    'commit', '-qm', 'fixture'], check=True)


BASE = '''# Evaluation environment

Linux bash. Host has Python 3.12, Node 24, npm 11, pnpm 11 and Git. The project-specific
compiler/SDK and Docker/kubectl/Helm are absent unless indicated. Do not download
packages or invoke an external deployment; package registry/network restrictions are
an evaluation instruction, not an enforced process sandbox. Project files are writable,
initial Git commit is clean, and project-specific caches start empty. Host caches may
contain unrelated content. Inspect evidence, choose project-specific commands and CI,
run only available meaningful checks, and report blocked capabilities explicitly.
'''


SCENARIOS: dict[str, dict[str, str]] = {
    'android-kotlin': {
        'settings.gradle.kts': 'pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }\ninclude(":app")\n',
        'app/build.gradle.kts': 'plugins { id("com.android.application") version "8.9.0"; kotlin("android") version "2.1.0" }\nandroid { namespace = "example.mobile"; compileSdk = 35; defaultConfig { applicationId = "example.mobile"; minSdk = 24; targetSdk = 35 }; flavorDimensions += "tier"; productFlavors { create("demo") { dimension = "tier" }; create("paid") { dimension = "tier" } } }\n',
        'app/src/main/java/example/mobile/MainActivity.kt': 'package example.mobile\nimport android.app.Activity\nclass MainActivity : Activity()\n',
        'app/src/test/java/example/mobile/ArithmeticTest.kt': 'package example.mobile\nimport org.junit.Test\nimport org.junit.Assert.assertEquals\nclass ArithmeticTest { @Test fun adds() = assertEquals(4, 2 + 2) }\n',
        'gradlew': '#!/bin/sh\necho "fixture wrapper: Gradle distribution unavailable" >&2\nexit 127\n',
        'README.md': 'Android Kotlin app with demo/paid variants; wrapper is incomplete and SDK unavailable.\n',
    },
    'go-service-kube': {
        'go.mod': 'module example.com/api\n\ngo 1.22\n',
        'main.go': 'package main\nimport "net/http"\nfunc main() { http.ListenAndServe(":8080", http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.Write([]byte("ok")) })) }\n',
        'main_test.go': 'package main\nimport "testing"\nfunc TestSmoke(t *testing.T) { if 2+2 != 4 { t.Fatal("bad math") } }\n',
        'Dockerfile': 'FROM golang:1.22 AS build\nWORKDIR /src\nCOPY . .\nRUN go build -o /out/api .\nFROM gcr.io/distroless/base-debian12\nCOPY --from=build /out/api /api\nENTRYPOINT ["/api"]\n',
        'deploy/k8s/deployment.yaml': 'apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: api\nspec:\n  replicas: 1\n  selector:\n    matchLabels: {app: api}\n  template:\n    metadata:\n      labels: {app: api}\n    spec:\n      containers:\n      - name: api\n        image: example.invalid/api:UNSET\n        ports: [{containerPort: 8080}]\n',
        'README.md': 'Go HTTP service, container build and Kubernetes deployment example. Image/tag and cluster are placeholders.\n',
    },
    'rust-cli-helm': {
        'Cargo.toml': '[package]\nname="reporter"\nversion="0.1.0"\nedition="2021"\n',
        'src/main.rs': 'fn main() { println!("reporter ready"); }\n',
        'tests/smoke.rs': '#[test]\nfn smoke() { assert_eq!(2 + 2, 4); }\n',
        'Dockerfile': 'FROM rust:1.80 AS build\nWORKDIR /src\nCOPY . .\nRUN cargo build --release\nFROM debian:bookworm-slim\nCOPY --from=build /src/target/release/reporter /usr/local/bin/reporter\nENTRYPOINT ["reporter"]\n',
        'charts/reporter/Chart.yaml': 'apiVersion: v2\nname: reporter\nversion: 0.1.0\n',
        'charts/reporter/values.yaml': 'image:\n  repository: example.invalid/reporter\n  tag: UNSET\n',
        'charts/reporter/templates/job.yaml': 'apiVersion: batch/v1\nkind: Job\nmetadata:\n  name: {{ .Release.Name }}\nspec:\n  template:\n    spec:\n      restartPolicy: Never\n      containers:\n      - name: reporter\n        image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"\n',
        'README.md': 'Rust CLI distributed as a container and Helm Job. Cluster and image tag are placeholders.\n',
    },
    'csharp-api-compose': {
        'global.json': '{"sdk":{"version":"8.0.100","rollForward":"latestFeature"}}\n',
        'src/Api/Api.csproj': '<Project Sdk="Microsoft.NET.Sdk.Web"><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>\n',
        'src/Api/Program.cs': 'var builder = WebApplication.CreateBuilder(args);\nvar app = builder.Build();\napp.MapGet("/health", () => Results.Ok(new { status = "ok" }));\napp.Run();\n',
        'tests/Api.Tests/Api.Tests.csproj': '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net8.0</TargetFramework><IsTestProject>true</IsTestProject></PropertyGroup><ItemGroup><PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.11.1"/><PackageReference Include="xunit" Version="2.9.2"/></ItemGroup></Project>\n',
        'tests/Api.Tests/Smoke.cs': 'using Xunit; public class Smoke { [Fact] public void MathWorks() => Assert.Equal(4, 2 + 2); }\n',
        'Dockerfile': 'FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build\nWORKDIR /src\nCOPY . .\nRUN dotnet publish src/Api/Api.csproj -c Release -o /out\nFROM mcr.microsoft.com/dotnet/aspnet:8.0\nCOPY --from=build /out /app\nWORKDIR /app\nENTRYPOINT ["dotnet", "Api.dll"]\n',
        'compose.yaml': 'services:\n  api:\n    build: .\n    ports: ["8080:8080"]\n',
        'README.md': 'ASP.NET Core API, xUnit tests and Compose. No SDK or Docker installed locally.\n',
    },
    'django-postgres': {
        'pyproject.toml': '[project]\nname="eval-django"\nversion="0.1.0"\nrequires-python=">=3.11"\ndependencies=["django>=5,<6","psycopg[binary]>=3,<4"]\n[dependency-groups]\ndev=["pytest>=8,<10","ruff>=0.9,<1"]\n',
        'manage.py': 'import os\nimport sys\nif __name__ == "__main__":\n    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "siteapp.settings")\n    from django.core.management import execute_from_command_line\n    execute_from_command_line(sys.argv)\n',
        'siteapp/__init__.py': '',
        'siteapp/settings.py': 'SECRET_KEY = "fixture-only"\nINSTALLED_APPS = []\nDATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "NAME": "app"}}\n',
        'siteapp/urls.py': 'from django.urls import path\nurlpatterns = []\n',
        'tests/test_settings.py': 'def test_settings():\n    from siteapp import settings\n    assert settings.DATABASES["default"]["NAME"] == "app"\n',
        'compose.yaml': 'services:\n  db:\n    image: postgres:16\n    environment:\n      POSTGRES_DB: app\n  web:\n    build: .\n    depends_on: [db]\n',
        'Dockerfile': 'FROM python:3.12-slim\nWORKDIR /app\nCOPY . .\nRUN pip install .\nCMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]\n',
        'README.md': 'Django application with Postgres in Compose. DB credentials and production settings are incomplete.\n',
    },
    'static-html-kube': {
        'package.json': '{"name":"eval-static","private":true,"type":"module","scripts":{"test":"node --test","lint":"node --check src/main.js","build":"node scripts/build.js"}}\n',
        'package-lock.json': '{"name":"eval-static","lockfileVersion":3,"requires":true,"packages":{"":{"name":"eval-static"}}}\n',
        'index.html': '<!doctype html><html><body><main id="app"></main><script type="module" src="/src/main.js"></script></body></html>\n',
        'src/main.js': 'export function label(name) { return `Hello ${name}`; }\n',
        'test/main.test.js': 'import test from "node:test"; import assert from "node:assert/strict"; import { label } from "../src/main.js"; test("label", () => assert.equal(label("Ada"), "Hello Ada"));\n',
        'scripts/build.js': 'import { mkdirSync, copyFileSync } from "node:fs"; mkdirSync("dist/src", { recursive: true }); copyFileSync("index.html", "dist/index.html"); copyFileSync("src/main.js", "dist/src/main.js");\n',
        'Dockerfile': 'FROM nginx:stable-alpine\nCOPY dist/ /usr/share/nginx/html/\n',
        'deploy/k8s/deployment.yaml': 'apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: static-site}\nspec:\n  replicas: 1\n  selector: {matchLabels: {app: static-site}}\n  template:\n    metadata: {labels: {app: static-site}}\n    spec:\n      containers:\n      - name: web\n        image: example.invalid/static-site:UNSET\n',
        'README.md': 'Static HTML and JS site; Node-only test/build work offline. Container and cluster are not available locally.\n',
    },
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=DEFAULT)
    args = parser.parse_args()
    base = args.output.resolve()
    if base.exists() and any(base.iterdir()):
        parser.error(f'{base} is not empty')
    base.mkdir(parents=True, exist_ok=True)
    cases = {}
    for name, entries in SCENARIOS.items():
        root = base / name
        create(root, entries | {'EVAL_ENV.md': BASE})
        cases[name] = {'target': str(root), 'prompt': f'Use {SKILL} to bootstrap {root}; read EVAL_ENV.md, assess real components/tooling/CI/container-orchestration evidence, configure agent commands, validate only what runs locally, leave unsupported deployment pending, report changes and gaps.'}
    (base / 'run_manifest.json').write_text(json.dumps({'schema_version': 1, 'cases': cases,
        'limitations': 'shared runtime; project scope/network are instructions, not OS isolation'}, indent=2) + '\n')
    print(json.dumps({'output': str(base), 'cases': list(cases)}, indent=2))


if __name__ == '__main__':
    main()
