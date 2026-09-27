import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ControlledEvaluationFixtures(unittest.TestCase):
    def test_framework_cases_separate_components_and_git_roots(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'frameworks'
            result = subprocess.run([sys.executable,
                str(source / '.agents/skills/bootstrap-agent-env/scripts/evaluations/prepare_framework_cases.py'),
                '--output', str(root)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((root / 'run_manifest.json').read_text())
            self.assertEqual(set(manifest['cases']), {'django-angular', 'express-react-router',
                                                       'sails-react-router-split'})
            for case in ('django-angular', 'express-react-router'):
                self.assertTrue((root / case / '.git').is_dir())
                self.assertTrue((root / case / 'EVAL_ENV.md').is_file())
            self.assertTrue((root / 'django-angular/backend/manage.py').is_file())
            angular = json.loads((root / 'django-angular/frontend/angular.json').read_text())
            self.assertIn('test', angular['projects']['catalog-web']['architect'])
            self.assertTrue((root / 'express-react-router/api/test/health.test.mjs').is_file())
            self.assertTrue((root / 'express-react-router/web/src/main.jsx').is_file())
            for child in ('api', 'web'):
                self.assertTrue((root / 'sails-react-router-split' / child / '.git').is_dir())
            check = subprocess.run(['npm', 'test'], cwd=root / 'sails-react-router-split/api',
                                   capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
            self.assertIn('pass 1', check.stdout)

    def test_prepare_creates_four_offline_projects_with_working_native_tests(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'cases'
            result = subprocess.run([sys.executable, str(source / '.agents/skills/bootstrap-agent-env/scripts/evaluations/prepare.py'), '--output', str(output)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((output / 'run_manifest.json').read_text())
            self.assertEqual(len(manifest['cases']), 4)
            self.assertIn('not isolated', manifest['isolation'])
            checks = [('python-library', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-q']),
                      ('node-app', ['npm', 'test']),
                      ('mixed-monorepo', ['npm', 'test']),
                      ('split-workspace/backend', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-q']),
                      ('split-workspace/frontend', ['npm', 'test'])]
            for name, argv in checks:
                with self.subTest(name=name):
                    test = subprocess.run(argv, cwd=output / name, capture_output=True, text=True)
                    self.assertEqual(test.returncode, 0, test.stdout + test.stderr)
                    self.assertTrue((output / name / 'EVAL_ENV.md').is_file())

    def test_web_cases_expose_backend_react_sites_and_distinct_project_boundaries(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'web'
            result = subprocess.run([sys.executable, str(source / '.agents/skills/bootstrap-agent-env/scripts/evaluations/prepare_web_cases.py'),
                                     '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((output / 'run_manifest.json').read_text())
            self.assertEqual(set(manifest['cases']), {'baseline', 'stale-config', 'nested-frontends', 'split-repos'})
            for name in ('baseline', 'stale-config', 'nested-frontends'):
                root = output / name
                self.assertTrue((root / 'backend/app/main.py').is_file())
                self.assertTrue((root / 'backend/tests/test_health.py').is_file())
                self.assertTrue((root / '.git').is_dir())
                check = subprocess.run([sys.executable, 'scripts/static_check.py'], cwd=root / 'backend',
                                       capture_output=True, text=True)
                self.assertEqual(check.returncode, 0, check.stderr)
            self.assertTrue((output / 'baseline/apps/admin/src/main.jsx').is_file())
            self.assertTrue((output / 'baseline/apps/store/src/main.jsx').is_file())
            self.assertTrue((output / 'stale-config/.agents/commands.json').is_file())
            self.assertTrue((output / 'nested-frontends/frontend/pnpm-workspace.yaml').is_file())
            for child in ('api', 'web'):
                self.assertTrue((output / 'split-repos' / child / '.git').is_dir())

    def test_stack_cases_cover_native_and_infrastructure_artifacts(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'stacks'
            result = subprocess.run([sys.executable,
                str(source / '.agents/skills/bootstrap-agent-env/scripts/evaluations/prepare_stack_cases.py'),
                '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            expected = {'android-kotlin', 'go-service-kube', 'rust-cli-helm', 'csharp-api-compose',
                        'django-postgres', 'static-html-kube'}
            manifest = json.loads((output / 'run_manifest.json').read_text())
            self.assertEqual(set(manifest['cases']), expected)
            for case in expected:
                self.assertTrue((output / case / '.git').is_dir())
                self.assertTrue((output / case / 'EVAL_ENV.md').is_file())
            for path in ('go-service-kube/Dockerfile', 'go-service-kube/deploy/k8s/deployment.yaml',
                         'rust-cli-helm/charts/reporter/Chart.yaml', 'csharp-api-compose/compose.yaml',
                         'django-postgres/manage.py', 'android-kotlin/app/build.gradle.kts',
                         'static-html-kube/index.html'):
                self.assertTrue((output / path).is_file(), path)
            site = output / 'static-html-kube'
            for argv in (['npm', 'test'], ['npm', 'run', 'lint'], ['npm', 'run', 'build']):
                with self.subTest(argv=argv):
                    test = subprocess.run(argv, cwd=site, capture_output=True, text=True)
                    self.assertEqual(test.returncode, 0, test.stdout + test.stderr)
            self.assertTrue((site / 'dist/index.html').is_file())
