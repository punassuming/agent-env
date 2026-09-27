"""Black-box checks for the evaluation recorder and grader."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


CLI = Path(__file__).resolve().parents[1] / '.agents/skills/bootstrap-agent-env/scripts/evaluations/loop.py'


class EvalLoopTests(unittest.TestCase):
    def test_framework_grader_accepts_simple_workspace_script_delegation(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp) / 'frameworks'
            self.assertEqual(self.command('prepare', '--suite', 'frameworks', '--output', run).returncode, 0)
            target = run / 'express-react-router'
            (target / '.agents').mkdir()
            config = {'components': {
                'workspace': {'path': '.', 'commands': {'validate': []}},
                'api': {'path': 'api', 'commands': {'test': [], 'build': []}},
                'web': {'path': 'web', 'commands': {'test': [], 'build': []}},
            }}
            (target / '.agents/commands.json').write_text(json.dumps(config))
            report = self.command('grade', '--run', run)
            self.assertEqual(report.returncode, 0, report.stderr)
            self.assertEqual(json.loads(report.stdout)['cases']['express-react-router']['.']['missing_native_scripts'], [])
            del config['components']['web']['commands']['build']
            (target / '.agents/commands.json').write_text(json.dumps(config))
            report = self.command('grade', '--run', run)
            self.assertIn('web:build', json.loads(report.stdout)['cases']['express-react-router']['.']['missing_native_scripts'])

    def command(self, *args):
        return subprocess.run([sys.executable, str(CLI), *map(str, args)],
                              text=True, capture_output=True)

    def test_preparation_recording_grading_and_comparison(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            before = root / 'before'
            after = root / 'after'
            for run in (before, after):
                result = self.command('prepare', '--suite', 'controlled', '--output', run)
                self.assertEqual(result.returncode, 0, result.stderr)
                manifest = json.loads((run / 'run_manifest.json').read_text())
                self.assertEqual(len(manifest['cases']), 4)
                self.assertIn('Read EVAL_ENV.md', manifest['cases']['python-library']['prompt'])
                self.assertIn('instruction_hashes', json.loads((run / 'eval-run.json').read_text()))
            target = after / 'python-library'
            agents = target / '.agents'
            agents.mkdir()
            (agents / 'assessment.md').write_text('observed pass\n')
            (agents / 'bootstrap.json').write_text('{"applied_version":"0.5.0"}\n')
            (agents / 'commands.json').write_text('{"components":{"root":{"path":".","commands":{"validate":[]}}}}\n')
            (target / 'AGENTS.md').write_text('run tests\n')
            (target / '.gitignore').write_text('.local/\n')
            (target / '.github/workflows').mkdir(parents=True)
            (target / '.github/workflows/ci.yml').write_text('name: CI\n')
            (agents / 'skills/bootstrap-agent-env').mkdir(parents=True)
            (agents / 'skills/bootstrap-agent-env/SKILL.md').write_text('skill\n')
            trace = root / 'trace.txt'
            trace.write_text('agent finished\n')
            checks = root / 'checks.json'
            checks.write_text('[{"id":"lint","argv":["python","-m","compileall"],"exit_code":0}]\n')
            result = self.command('record', '--run', after, '--case', 'python-library',
                                  '--agent', 'sample', '--model', 'fixed-model', '--trace', trace, '--checks', checks)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotEqual(self.command('record', '--run', after, '--case', 'python-library',
                                  '--agent', 'sample', '--model', 'fixed-model', '--trace', trace, '--checks', checks).returncode, 0)
            for run in (before, after):
                result = self.command('grade', '--run', run)
                self.assertEqual(result.returncode, 0, result.stderr)
            result = self.command('compare', '--before', before / 'grade.json', '--after', after / 'grade.json')
            self.assertEqual(result.returncode, 0, result.stderr)
            comparison = json.loads(result.stdout)
            row = next(x for x in comparison['results'] if x['case'] == 'python-library')
            self.assertIn('assessment', row['resolved'])
            self.assertIn('premature_finalize', row['regressions'])
            result = self.command('invoke', '--run', after, '--case', 'node-app',
                                  '--agent', 'example', '--model', 'fixed-model', '--dry-run',
                                  '--command', sys.executable, '{prompt_file}', '{target}')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((after / 'invocations').exists())
            self.assertIn('No sandbox', result.stdout)
            result = self.command('invoke', '--run', after, '--case', 'node-app',
                                  '--agent', 'mock', '--model', 'fixed-model', '--timeout', '15',
                                  '--command', sys.executable, '-c', 'print("agent started")')
            self.assertEqual(result.returncode, 0, result.stderr)
            invocation = after / 'invocations/node-app'
            self.assertEqual(json.loads((invocation / 'invocation.json').read_text())['exit_code'], 0)
            self.assertIn('agent started', (invocation / 'stdout.txt').read_text())

    def test_manifest_tampering_prevents_grading(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'run'
            result = self.command('prepare', '--suite', 'controlled', '--output', root)
            self.assertEqual(result.returncode, 0, result.stderr)
            (root / 'run_manifest.json').write_text('{}\n')
            result = self.command('grade', '--run', root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('manifest changed', result.stderr)

    def test_stack_grader_tracks_release_artifacts_without_executing_them(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'run'
            self.assertEqual(self.command('prepare', '--suite', 'stacks', '--output', root).returncode, 0)
            result = self.command('grade', '--run', root)
            self.assertEqual(result.returncode, 0, result.stderr)
            site = json.loads(result.stdout)['cases']['static-html-kube']['.']
            self.assertEqual(site['release'], {'container': False, 'kubernetes': False})
            self.assertEqual(site['ci_execution'], 'unverified')
            target = root / 'static-html-kube'
            (target / '.agents').mkdir()
            (target / '.agents/commands.json').write_text(json.dumps({'components':{
                'root':{'path':'.','commands':{
                    'container-check':[{'argv':['docker','buildx','build','--check','.']}],
                    'manifest-check':[{'argv':['node','scripts/check-manifest.js']}]}}}}))
            (target / 'scripts/check-manifest.js').write_text(
                'import { spawnSync } from "node:child_process";\n'
                'spawnSync("docker", ["run", "ghcr.io/yannh/kubeconform:v0.6.7"]);\n')
            result = self.command('grade', '--run', root)
            self.assertEqual(result.returncode, 0, result.stderr)
            site = json.loads(result.stdout)['cases']['static-html-kube']['.']
            self.assertEqual(site['release'], {'container': True, 'kubernetes': True})
            self.assertIn('scripts/check-manifest.js', site['inspected_adapters'])

    def test_fixture_agents_file_is_committed_and_labeled_as_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            instructions = root / 'custom-AGENTS.md'
            instructions.write_text('Run native tests and report exact counts.\n')
            run = root / 'run'
            result = self.command('prepare', '--suite', 'controlled', '--output', run,
                                  '--agents-file', instructions)
            self.assertEqual(result.returncode, 0, result.stderr)
            repo = run / 'python-library'
            self.assertEqual((repo / 'AGENTS.md').read_text(), instructions.read_text())
            self.assertFalse(subprocess.run(['git', '-C', str(repo), 'status', '--porcelain'],
                                             capture_output=True, text=True).stdout)
            graded = self.command('grade', '--run', run)
            self.assertEqual(graded.returncode, 0, graded.stderr)
            self.assertEqual(json.loads(graded.stdout)['cases']['python-library']['.']
                             ['instructions_origin'], 'fixture')


if __name__ == '__main__':
    unittest.main()
