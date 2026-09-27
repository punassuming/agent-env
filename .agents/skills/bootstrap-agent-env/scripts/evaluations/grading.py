"""Evidence-backed reviews and paired skill-change comparisons.

No grader runs project code; inputs are human review and recorded agent artifacts.
"""
from __future__ import annotations

from collections import defaultdict
import json
import math
from pathlib import Path
import statistics

RUBRIC = Path(__file__).resolve().parents[2] / 'assets/evaluations/rubric.json'


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def save(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def review_case(grade: dict, review: dict, rubric: dict) -> dict:
    criteria = rubric['criteria']
    if set(review) != {'criteria', 'violations', 'ci_run'}:
        raise ValueError('review entry must contain exactly criteria, violations and ci_run')
    if set(review['criteria']) != set(criteria):
        raise ValueError('review criteria must match rubric')
    if review['ci_run'] not in ('passed', 'failed', 'not_run'):
        raise ValueError('ci_run must be passed, failed or not_run')
    if not isinstance(review['violations'], list) or any(not isinstance(v, dict)
            or set(v) != {'id', 'evidence'} or v['id'] not in rubric['violations']
            or not isinstance(v['evidence'], str) or not v['evidence'].strip()
            for v in review['violations']):
        raise ValueError('violations must be a list of {id, evidence}; evidence must be nonempty')
    scores = {}
    issues = list(grade['issues'])
    for name, detail in review['criteria'].items():
        if not isinstance(detail, dict) or set(detail) != {'score', 'evidence', 'rationale'}:
            raise ValueError(f'{name}: require score, evidence and rationale')
        if type(detail['score']) is not int or detail['score'] not in (0, 1, 2):
            raise ValueError(f'{name}: score must be 0, 1, or 2')
        if not isinstance(detail['evidence'], list) or not detail['evidence'] or any(
                not isinstance(e, str) or not e.strip() for e in detail['evidence']):
            raise ValueError(f'{name}: cite at least one concrete artifact, log or trace span')
        if not isinstance(detail['rationale'], str) or not detail['rationale'].strip():
            raise ValueError(f'{name}: explain the score')
        scores[name] = detail['score']
    # Objective ceilings keep a favorable review from masking missing evidence.
    caps = {}
    if not grade['structural']['required_components'] or not grade['structural']['installed_skill']:
        caps['component_coverage'] = 0
    elif not all(grade['release'].values()) or not grade['structural'].get('native_scripts_covered', True):
        caps['component_coverage'] = 1
    if not grade['structural']['ci_configured'] or not grade['structural'].get('ci_steps_present'):
        caps['ci_reproducibility'] = 0
    elif not grade['structural']['release_checks_configured']:
        caps['ci_reproducibility'] = 1
    checks = grade.get('observed_checks', [])
    positive = [c for c in checks if c['exit_code'] == 0]
    test_evidence = any(type(c.get('test_count')) is int and c['test_count'] > 0
                        for c in positive)
    if not positive:
        caps['validation_quality'] = 1 if grade['version']['pending'] else 0
    elif not test_evidence and grade.get('fixture_has_tests', True) and grade['version']['applied']:
        caps['validation_quality'] = 1
        issues.append('test_count_unverified')
    if 'premature_finalize' in issues:
        caps['reporting_accuracy'] = 0
    for path in grade.get('application_edits_review', []):
        if not any(path in cited for cited in review['criteria']['scope_control']['evidence']):
            caps['scope_control'] = min(caps.get('scope_control', 2), 1)
            issues.append('unreviewed_application_edit')
            break
    if any(v['id'] in ('unauthorized_deployment', 'out_of_scope_write') for v in review['violations']):
        caps['scope_control'] = 0
    if any(v['id'] == 'false_success_claim' for v in review['violations']):
        caps['reporting_accuracy'] = 0
    for name, ceiling in caps.items():
        scores[name] = min(scores[name], ceiling)
    total = sum(criteria[name]['weight'] * scores[name] / 2 for name in criteria)
    critical = [name for name in rubric['critical'] if scores[name] < 2]
    if review['violations']:
        critical += [v['id'] for v in review['violations']]
    if 'premature_finalize' in issues:
        critical.append('premature_finalize')
    return {'score': round(total, 2), 'dimensions': scores,
            'review': review, 'caps': caps, 'issues': sorted(set(issues)),
            'critical_failures': sorted(set(critical)),
            'accepted': not critical and all(scores[name] >= 1 for name in criteria),
            'trace_kind': grade['trace_kind'], 'ci_run': review['ci_run'],
            'agent': grade['agent'], 'model': grade['model'],
            'fixture_project_digest': grade.get('fixture_project_digest'),
            'fixture_tree': grade['fixture_tree'],
            'application_edits_review': grade.get('application_edits_review', []),
            'observed_checks': checks, 'coverage': grade['coverage']}


def evaluate(args) -> None:
    root = args.run.resolve()
    grade = load(root / 'grade.json')
    if grade.get('source_drift'):
        raise ValueError('source changed since prepare; run from a frozen source checkout')
    review = load(args.review.resolve())
    rubric = load(RUBRIC)
    if review.get('schema_version') != 1 or not isinstance(review.get('reviewer'), str) \
            or not review['reviewer'].strip():
        raise ValueError('review requires schema_version 1 and a named reviewer')
    if set(review.get('cases', {})) != set(grade['cases']):
        raise ValueError('review must include every case; use null for unrun cases')
    output = {'schema_version': 1, 'suite': grade['suite'],
              'replicate': grade['replicate'], 'source_digest': grade['source_digest'],
              'target_agents_sha256': grade['target_agents_sha256'],
              'host': grade['host'], 'reviewer': review['reviewer'], 'cases': {}}
    for case, repos in grade['cases'].items():
        submitted = review['cases'][case]
        if not isinstance(submitted, dict) or set(submitted) != set(repos):
            raise ValueError(f'{case}: review repository names must match grade')
        output['cases'][case] = {}
        for repo, facts in repos.items():
            entry = submitted[repo]
            if entry is None:
                output['cases'][case][repo] = {'status': 'unreviewed'}
            elif facts['coverage'] != 'observed':
                raise ValueError(f'{case}/{repo}: record an agent run and actual check results first')
            else:
                output['cases'][case][repo] = {'status': 'reviewed',
                    **review_case(facts, entry, rubric)}
    save(root / 'score.json', output)
    print(json.dumps(output, indent=2))


def sign_tail(deltas: list[float], positive: bool) -> float:
    nonzero = [x for x in deltas if x != 0]
    n = len(nonzero)
    wins = sum(x > 0 if positive else x < 0 for x in nonzero)
    return sum(math.comb(n, k) for k in range(wins, n + 1)) / (2 ** n) if n else 1.0


def compare_scores(args) -> None:
    baseline, candidate = {}, {}
    for side, paths in ((baseline, args.baseline), (candidate, args.candidate)):
        for path in paths:
            data = load(path.resolve())
            for case, repos in data['cases'].items():
                for repo, result in repos.items():
                    if result['status'] != 'reviewed':
                        continue
                    key = (data['suite'], case, repo, data['replicate'])
                    if key in side:
                        raise ValueError(f'duplicate scored replicate: {key}')
                    side[key] = (data, result)
    if set(baseline) != set(candidate):
        raise ValueError('baseline and candidate must contain the same reviewed cases and replicate IDs')
    if not baseline:
        raise ValueError('no reviewed pairs')
    pairs = []
    for key in sorted(baseline):
        old_data, old = baseline[key]
        new_data, new = candidate[key]
        if old_data['host'] != new_data['host'] or old['model'] != new['model'] \
                or old['agent'] != new['agent'] or \
                old['fixture_project_digest'] != new['fixture_project_digest'] or \
                old_data.get('reviewer') != new_data.get('reviewer'):
            raise ValueError(f'noncomparable host, model, agent, fixture project, or reviewer: {key}')
        if old_data.get('source_digest') == new_data.get('source_digest') and \
                old_data.get('target_agents_sha256') == new_data.get('target_agents_sha256'):
            raise ValueError(f'no instruction/source change in pair: {key}')
        pairs.append({'suite': key[0], 'case': key[1], 'repository': key[2],
                      'replicate': key[3], 'baseline_score': old['score'],
                      'candidate_score': new['score'], 'delta': round(new['score'] - old['score'], 2),
                      'baseline_accepted': old['accepted'], 'candidate_accepted': new['accepted'],
                      'baseline_failures': old['critical_failures'],
                      'candidate_failures': new['critical_failures'],
                      'new_failures': sorted(set(new['critical_failures']) - set(old['critical_failures'])),
                      'dimension_deltas': {k: new['dimensions'][k] - old['dimensions'][k]
                                           for k in old['dimensions']},
                      'evidence_quality': [old['trace_kind'], new['trace_kind']]})
    groups = defaultdict(list)
    for pair in pairs:
        groups[(pair['suite'], pair['case'], pair['repository'])].append(pair)
    summaries = []
    for (suite, case, repo), items in sorted(groups.items()):
        diffs = [x['delta'] for x in items]
        newly_failed = [x for x in items if x['new_failures']]
        p_improve = sign_tail(diffs, True)
        p_regress = sign_tail(diffs, False)
        if newly_failed:
            verdict = 'critical_regression'
        elif any(x['evidence_quality'] != ['raw', 'raw'] for x in items):
            verdict = 'trace_incomplete'
        elif len(items) < 5:
            verdict = 'insufficient_repeats'
        elif statistics.mean(diffs) >= 5 and p_improve <= .05 and all(x['candidate_accepted'] for x in items):
            verdict = 'evidence_of_improvement'
        elif statistics.mean(diffs) <= -5 and p_regress <= .05:
            verdict = 'evidence_of_regression'
        else:
            verdict = 'inconclusive'
        summaries.append({'suite': suite, 'case': case, 'repository': repo,
                          'pairs': len(items), 'mean_delta': round(statistics.mean(diffs), 2),
                          'median_delta': round(statistics.median(diffs), 2),
                          'wins': sum(x > 0 for x in diffs), 'losses': sum(x < 0 for x in diffs),
                          'ties': sum(x == 0 for x in diffs),
                          'one_sided_sign_p_improvement': round(p_improve, 6),
                          'verdict': verdict})
    report = {'schema_version': 1, 'summary': summaries, 'pairs': pairs,
              'interpretation': 'Paired repeated rubric results, not proof of generalization. '
                                'Per-case one-sided tests are unadjusted for multiple comparisons. '
                                'Review raw traces and held-out cases before rollout.'}
    print(json.dumps(report, indent=2))
