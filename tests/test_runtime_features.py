"""Exercise failure handoff, opt-in change checks, and task ingestion end to end."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from agent_env.bootstrap import install


class RuntimeFeatures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        install(self.repo, {})
        self.config = self.repo / '.agents/commands.json'
        self.runner = self.repo / '.agents/bin/runtime.py'

    def configure(self, components):
        self.config.write_text(json.dumps({'schema_version': 1, 'local_root': '.local',
                                            'components': components}))

    def call(self, *args, env=None):
        if env is None:
            env = os.environ.copy()
            env.pop('CI', None)
            env.pop('GITHUB_ACTIONS', None)
        return subprocess.run([sys.executable, str(self.runner), *args], cwd=self.repo,
                              env=env, capture_output=True, text=True)

    def test_last_failure_survives_user_run_and_success_marks_resolution(self):
        self.configure({'app': {'path': '.', 'tools': ['python'], 'commands': {'validate': [
            {'argv': [sys.executable, '-c', 'import sys; print("diagnostic"); sys.exit(6)']}]}}})
        failure = self.call('validate')
        self.assertEqual(failure.returncode, 6, failure.stderr)
        status = json.loads(self.call('status').stdout)
        record = status['last_failure']
        self.assertEqual((record['component'], record['command'], record['exit_code']), ('app', 'validate', 6))
        self.assertIn('diagnostic', (self.repo / record['log']).read_text())
        self.assertFalse(status['last_failure_followed_by_success'])
        self.configure({'app': {'path': '.', 'tools': ['python'], 'commands': {'validate': [
            {'argv': [sys.executable, '-c', 'print("recovered")']}],
            'lint': [{'argv': [sys.executable, '-c', 'print("linted")']}]}}})
        self.assertEqual(self.call('validate').returncode, 0)
        status = json.loads(self.call('status').stdout)
        self.assertEqual(status['last_failure']['exit_code'], 6)
        self.assertTrue(status['last_failure_followed_by_success'])
        self.assertEqual(self.call('lint').returncode, 0)
        self.assertTrue(json.loads(self.call('status').stdout)['last_failure_followed_by_success'])
        self.assertIn('recovered', self.call('validate', '--changed').stdout)

    def test_changed_skips_only_declared_inputs_after_success_and_never_in_ci(self):
        (self.repo / 'src').mkdir()
        (self.repo / 'src/code.txt').write_text('one')
        checker = self.repo / 'check.py'
        checker.write_text('from pathlib import Path\np=Path("counter.txt")\np.write_text(str(int(p.read_text()) + 1 if p.exists() else 1))\nif Path("src/fail.txt").exists(): raise SystemExit(8)\n')
        self.configure({'app': {'path': '.', 'tools': ['python'],
            'commands': {'validate': [{'argv': [sys.executable, 'check.py']}]},
            'change_detection': {'validate': {'inputs': ['src/**/*', 'check.py']}}}})
        counter = self.repo / 'counter.txt'
        self.assertEqual(self.call('validate', '--changed').returncode, 0)
        self.assertEqual(counter.read_text(), '1')
        skipped = self.call('validate', '--changed')
        self.assertIn('SKIPPED UNCHANGED', skipped.stdout)
        self.assertEqual(counter.read_text(), '1')
        self.assertTrue(json.loads(self.call('changes', '--json').stdout)['app']['unchanged_since_success'])
        (self.repo / 'src/code.txt').write_text('two')
        change_report = json.loads(self.call('changes', '--json').stdout)['app']
        self.assertEqual(change_report['changed_files'], ['src/code.txt'])
        self.assertIsNotNone(change_report['last_success_utc'])
        self.assertGreaterEqual(change_report['newest_input_age_seconds'], 0)
        self.assertEqual(self.call('validate', '--changed').returncode, 0)
        self.assertEqual(counter.read_text(), '2')
        (self.repo / 'src/fail.txt').write_text('fail')
        self.assertEqual(self.call('validate', '--changed').returncode, 8)
        self.assertFalse(json.loads(self.call('changes', '--json').stdout)['app']['unchanged_since_success'])
        (self.repo / 'src/fail.txt').unlink()
        self.assertEqual(self.call('validate', '--changed').returncode, 0)
        self.assertEqual(counter.read_text(), '4')
        env = os.environ.copy()
        env['CI'] = 'true'
        self.assertEqual(self.call('validate', '--changed', env=env).returncode, 0)
        self.assertEqual(counter.read_text(), '5')

    def test_declared_file_parameters_are_scoped_and_not_interpolated(self):
        (self.repo / 'src').mkdir()
        (self.repo / 'src/a.py').write_text('pass\n')
        self.configure({'app': {'path': '.', 'tools': ['python'],
            'parameters': {'test-file': {'file': {'type': 'file'}},
                           'test-node': {'node_id': {'type': 'nodeid'}}},
            'commands': {'test-file': [{'argv': [sys.executable, '-c', 'import sys; print(sys.argv[1])', '{file}']}],
                         'test-node': [{'argv': [sys.executable, '-c', 'import sys; print(sys.argv[1])', '{node_id}']}]}}})
        self.assertIn('src/a.py', self.call('test-file', '--component', 'app', '--file', 'src/a.py').stdout)
        self.assertIn('::test_a', self.call('test-node', '--component', 'app', '--node-id', 'src/a.py::test_a').stdout)
        self.assertEqual(self.call('test-file', '--component', 'app', '--file', '../escape.py').returncode, 2)
        self.assertEqual(self.call('test-file', '--component', 'app', '--file', '-x').returncode, 2)

    def test_vscode_jsonc_task_catalog_and_process_execution(self):
        self.configure({'app': {'path': '.', 'tools': [], 'commands': {'validate': []}}})
        vscode = self.repo / '.vscode'
        vscode.mkdir()
        (vscode / 'tasks.json').write_text('''{
          // A process task can be imported without interpreting a shell.
          "version": "2.0.0",
          "tasks": [
            {"label":"safe", "type":"process", "command":''' + json.dumps(sys.executable) + ''',
             "args":["-c","from pathlib import Path; Path('task-ran').write_text('yes')"],
             "options":{"cwd":"${workspaceFolder}"},},
            {"label":"shell", "type":"shell", "command":"echo data > unsafe"},
            {"label":"dynamic", "type":"process", "command":"${command:choose}"},
          ],
        }''')
        catalog = self.call('catalog', '--json')
        self.assertEqual(catalog.returncode, 0, catalog.stderr)
        tasks = {task['label']: task for task in json.loads(catalog.stdout)['vscode_tasks']}
        self.assertTrue(tasks['safe']['runnable'])
        self.assertFalse(tasks['shell']['runnable'])
        self.assertFalse(tasks['dynamic']['runnable'])
        self.assertEqual(self.call('run-task', '--task', 'safe').returncode, 0)
        self.assertEqual((self.repo / 'task-ran').read_text(), 'yes')
        self.assertEqual(self.call('run-task', '--task', 'shell').returncode, 2)
        self.assertFalse((self.repo / 'unsafe').exists())


if __name__ == '__main__':
    unittest.main()
