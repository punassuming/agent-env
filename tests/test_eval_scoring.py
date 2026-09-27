"""Regressions in the evidence-backed grading and paired comparison rules."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / '.agents/skills/bootstrap-agent-env/scripts/evaluations/loop.py'
RUBRIC = ROOT / '.agents/skills/bootstrap-agent-env/assets/evaluations/rubric.json'


def call(*args):
    return subprocess.run([sys.executable, str(CLI), *map(str, args)],
                          capture_output=True, text=True)


def review(score=2, violations=None):
    return {'criteria': {name: {'score': score, 'evidence': ['assessment and validation log'],
                                'rationale': 'Reviewer inspected the recorded artifact and check output.'}
                         for name in json.loads(RUBRIC.read_text())['criteria']},
            'violations': [] if violations is None else violations, 'ci_run': 'not_run'}


class EvalScoringTests(unittest.TestCase):
    def test_scoring_needs_evidence_and_caps_false_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = root / 'run'
            self.assertEqual(call('prepare', '--suite', 'controlled', '--output', run).returncode, 0)
            target = run / 'node-app'
            (target / '.agents/skills/bootstrap-agent-env').mkdir(parents=True)
            (target / '.agents/skills/bootstrap-agent-env/SKILL.md').write_text('skill\n')
            (target / '.agents/assessment.md').write_text('Observed one passing test.\n')
            (target / '.agents/bootstrap.json').write_text('{"applied_version":"0.6.0"}\n')
            (target / '.agents/commands.json').write_text(json.dumps({'components':{'root':{'path':'.','commands':{
                'test':[{'argv':['npm','test']}], 'lint':[{'argv':['npm','run','lint']}],
                'build':[{'argv':['npm','run','build']}],
                'validate':[{'argv':['npm','test']}, {'argv':['npm','run','lint']},
                            {'argv':['npm','run','build']}]}}}})+'\n')
            (target / 'AGENTS.md').write_text('Run checks.\n')
            (target / '.gitignore').write_text('.local/\n')
            (target / '.github/workflows').mkdir(parents=True)
            (target / '.github/workflows/ci.yml').write_text('name: CI\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: npm test\n')
            trace = root / 'trace.txt'
            trace.write_text('agent ran validation\n')
            check_log = root / 'validate.log'
            check_log.write_text('ℹ tests 1\nℹ pass 1\nℹ fail 0\n', encoding='utf-8')
            checks = root / 'checks.json'
            checks.write_text(json.dumps([{'id':'validate','argv':['npm','test'],
                'exit_code':0,'test_count':1,'log':str(check_log)}])+'\n')
            self.assertEqual(call('record', '--run', run, '--case', 'node-app', '--agent', 'codex',
                '--model', 'pinned', '--trace', trace, '--checks', checks).returncode, 0)
            saved_log = run / 'observations/node-app/check-0.log'
            saved_log.write_text('tampered log\n')
            self.assertNotEqual(call('grade', '--run', run).returncode, 0)
            saved_log.write_text(check_log.read_text(encoding='utf-8'), encoding='utf-8')
            self.assertEqual(call('grade', '--run', run).returncode, 0)
            report = {'schema_version': 1, 'reviewer': 'reviewer-1',
                'cases': {name: {repo: review() if name == 'node-app' else None
                    for repo in reps} for name, reps in json.loads((run / 'grade.json').read_text())['cases'].items()}}
            path = root / 'review.json'
            path.write_text(json.dumps(report))
            scored = call('score', '--run', run, '--review', path)
            self.assertEqual(scored.returncode, 0, scored.stderr)
            case = json.loads(scored.stdout)['cases']['node-app']['.']
            self.assertEqual(case['score'], 100)
            self.assertTrue(case['accepted'])
            grade_file = run / 'grade.json'
            original_grade = grade_file.read_text()
            uncollected = json.loads(original_grade)
            uncollected['cases']['node-app']['.']['observed_checks'][0]['test_count'] = 0
            grade_file.write_text(json.dumps(uncollected))
            scored = call('score', '--run', run, '--review', path)
            self.assertEqual(scored.returncode, 0, scored.stderr)
            case = json.loads(scored.stdout)['cases']['node-app']['.']
            self.assertEqual(case['dimensions']['validation_quality'], 1)
            self.assertIn('test_count_unverified', case['issues'])
            grade_file.write_text(original_grade)
            (target / 'src/index.js').write_text('export const double = (value) => value + value;\n')
            self.assertEqual(call('grade', '--run', run).returncode, 0)
            scoped = call('score', '--run', run, '--review', path)
            self.assertEqual(scoped.returncode, 0, scoped.stderr)
            self.assertIn('unreviewed_application_edit',
                          json.loads(scoped.stdout)['cases']['node-app']['.']['issues'])
            self.assertFalse(json.loads(scoped.stdout)['cases']['node-app']['.']['accepted'])
            report['cases']['node-app']['.']['violations'] = [
                {'id':'out_of_scope_write', 'evidence':'git diff src/index.js'}]
            path.write_text(json.dumps(report))
            scored = call('score', '--run', run, '--review', path)
            self.assertEqual(scored.returncode, 0, scored.stderr)
            case = json.loads(scored.stdout)['cases']['node-app']['.']
            self.assertFalse(case['accepted'])
            self.assertEqual(case['dimensions']['scope_control'], 0)
            self.assertIn('out_of_scope_write', case['critical_failures'])
            report['cases']['node-app']['.']['violations'] = []
            checks.write_text('[{"id":"validate","argv":["npm","test"],"exit_code":0}]\n')
            # An existing observation cannot be silently rewritten after grading.
            path.write_text(json.dumps(report))
            self.assertEqual(call('record', '--run', run, '--case', 'node-app', '--agent', 'codex',
                '--model', 'pinned', '--trace', trace, '--checks', checks).returncode, 2)

    def test_five_matched_positive_pairs_and_mismatch_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline, candidate = [], []
            for index in range(1, 6):
                for side, collection, score in [('old', baseline, 70), ('new', candidate, 80)]:
                    path = root / f'{side}-{index}.json'
                    row = {'status':'reviewed', 'score':score, 'accepted':True,
                           'critical_failures':[], 'dimensions':{'scope_control':2},
                           'trace_kind':'raw', 'model':'pinned', 'agent':'codex',
                           'fixture_project_digest':'same-fixture'}
                    path.write_text(json.dumps({'suite':'controlled', 'replicate':str(index),
                        'host':{'python':'3.12'}, 'reviewer':'blinded-reviewer',
                        'source_digest':side, 'target_agents_sha256':None,
                        'cases':{'node-app':{'.':row}}}))
                    collection.append(path)
            result = call('compare-scores', '--baseline', *baseline, '--candidate', *candidate)
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(result.stdout)['summary'][0]
            self.assertEqual(summary['verdict'], 'evidence_of_improvement')
            self.assertEqual(summary['pairs'], 5)
            self.assertEqual(summary['one_sided_sign_p_improvement'], 0.03125)
            changed = json.loads(candidate[0].read_text())
            changed['host']['python'] = '3.13'
            candidate[0].write_text(json.dumps(changed))
            self.assertNotEqual(call('compare-scores', '--baseline', *baseline,
                                     '--candidate', *candidate).returncode, 0)
            changed['host']['python'] = '3.12'
            changed['cases']['node-app']['.']['critical_failures'] = ['false_success_claim']
            candidate[0].write_text(json.dumps(changed))
            result = call('compare-scores', '--baseline', *baseline, '--candidate', *candidate)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['summary'][0]['verdict'], 'critical_regression')
            changed['cases']['node-app']['.']['critical_failures'] = []
            changed['source_digest'] = 'old'
            candidate[0].write_text(json.dumps(changed))
            self.assertNotEqual(call('compare-scores', '--baseline', *baseline,
                                     '--candidate', *candidate).returncode, 0)


if __name__ == '__main__':
    unittest.main()
