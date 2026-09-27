"""Prepare, record, grade and compare agent bootstrap trials; stdlib only.

This tool never starts an agent or executes commands in an evaluated project.
Observations must come from the actual agent run and must be reviewed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time

from grading import evaluate, compare_scores

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
GENERATORS = {'controlled': 'prepare.py', 'web': 'prepare_web_cases.py',
              'stacks': 'prepare_stack_cases.py'}
EXPECTED = {
    'controlled': {
        'python-library': ['.'], 'node-app': ['.'],
        'mixed-monorepo': ['.', 'services/api'],
        'split-workspace': {'backend': ['.'], 'frontend': ['.']},
    },
    'web': {
        'baseline': ['.', 'backend'], 'stale-config': ['.', 'backend'],
        'nested-frontends': ['backend', 'frontend'],
        'split-repos': {'api': ['.'], 'web': ['.']},
    },
    'stacks': {case: ['.'] for case in ('android-kotlin', 'go-service-kube',
        'rust-cli-helm', 'csharp-api-compose', 'django-postgres', 'static-html-kube')},
}
KINDS = {'container': ('docker', 'podman', 'buildah'),
         'compose': ('compose',), 'kubernetes': ('kubectl', 'kubeconform', 'kubeval'),
         'helm': ('helm',)}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_digest(source: Path) -> str:
    sha = hashlib.sha256()
    roots = [source / 'AGENTS.md', source / '.agents/registry.json',
             source / '.agents/agents', source / '.agents/skills/bootstrap-agent-env']
    for root in roots:
        for path in ([root] if root.is_file() else sorted(root.rglob('*')) if root.exists() else []):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                sha.update(str(path.relative_to(source)).encode('utf-8'))
                sha.update(bytes.fromhex(digest(path)))
    return sha.hexdigest()


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def prepare(args: argparse.Namespace) -> None:
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError(f'output is not empty: {output}')
    source = args.source.resolve()
    skill = source / '.agents/skills/bootstrap-agent-env/SKILL.md'
    if args.variant == 'skill' and not skill.is_file():
        raise ValueError(f'missing source skill: {skill}')
    subprocess.run([sys.executable, str(HERE / GENERATORS[args.suite]), '--output', str(output)], check=True)
    manifest = read(output / 'run_manifest.json')
    for case in manifest['cases'].values():
        target = Path(case['target'])
        case['prompt'] = (f'Use the skill at {skill} to bootstrap {target}. ' if args.variant == 'skill'
                          else f'Bootstrap the agent environment in {target}. ')
        case['prompt'] += ('Read EVAL_ENV.md. Assess the workspace, adapt commands, AGENTS and skills, '
                           'configure CI, validate available capabilities, and report exact gaps. '
                           'Edit only the target and its child repositories. Do not deploy externally.')
    if args.agents_file:
        incoming = args.agents_file.resolve()
        if not incoming.is_file():
            raise ValueError(f'missing AGENTS file: {incoming}')
        for case_name, case in manifest['cases'].items():
            for repo in repos(case_name, Path(case['target']), args.suite).values():
                dest = repo / 'AGENTS.md'
                if dest.exists():
                    raise ValueError(f'fixture already has AGENTS.md: {dest}')
                shutil.copyfile(incoming, dest)
                subprocess.run(['git', '-C', str(repo), 'add', 'AGENTS.md'], check=True)
                subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Fixture',
                                '-c', 'user.email=fixture@example.invalid', 'commit', '-qm',
                                'Add evaluation AGENTS instructions'], check=True)
    write(output / 'run_manifest.json', manifest)
    revision = subprocess.run(['git', '-C', str(source), 'rev-parse', 'HEAD'], capture_output=True, text=True)
    files = ['AGENTS.md', '.agents/skills/bootstrap-agent-env/SKILL.md',
             '.agents/skills/bootstrap-agent-env/references/evaluation.md']
    write(output / 'eval-run.json', {
        'schema_version': 1, 'suite': args.suite, 'variant': args.variant,
        'replicate': args.replicate,
        'source': str(source), 'source_revision': revision.stdout.strip() if revision.returncode == 0 else None,
        'source_digest': source_digest(source),
        'target_agents_sha256': digest(args.agents_file.resolve()) if args.agents_file else None,
        'instruction_hashes': {name: digest(source / name) for name in files if (source / name).is_file()},
        'host': {'platform': platform.platform(), 'python': sys.version.split()[0],
                 'tools': {name: shutil.which(name) for name in
                           ('git', 'python', 'node', 'npm', 'pnpm', 'uv', 'cargo', 'go',
                            'dotnet', 'java', 'docker', 'kubectl', 'helm')},
                 'network_policy': 'not measured; trial restrictions are instructions'},
        'cases': sorted(manifest['cases']), 'manifest_hash': digest(output / 'run_manifest.json'),
        'isolation': 'No per-agent network/filesystem isolation is supplied by this script.',
    })
    print(json.dumps({'run': str(output), 'cases': sorted(manifest['cases']),
                      'variant': args.variant}, indent=2))


def record(args: argparse.Namespace) -> None:
    root = args.run.resolve()
    meta = read(root / 'eval-run.json')
    if args.case not in meta['cases']:
        raise ValueError(f'unknown case: {args.case}')
    observations = root / 'observations' / args.case
    if observations.exists():
        raise ValueError(f'observation already exists: {observations}')
    checks = read(args.checks)
    if not isinstance(checks, list) or any(not isinstance(c, dict) or
            not {'id', 'argv', 'exit_code'} <= c.keys() or
            not isinstance(c['exit_code'], int) or not isinstance(c['argv'], list)
            or ('test_count' in c and (type(c['test_count']) is not int or c['test_count'] < 0))
            for c in checks):
        raise ValueError('checks must be a JSON list of {id, argv: array, exit_code: integer}')
    for c in checks:
        if c.get('test_count', 0) > 0 and 'log' not in c:
            raise ValueError('nonzero test_count requires an actual command log')
        if 'log' in c and not Path(c['log']).is_file():
            raise ValueError(f'check log missing: {c["log"]}')
    observations.mkdir(parents=True)
    shutil.copyfile(args.trace, observations / 'trace.txt')
    for index, c in enumerate(checks):
        if 'log' in c:
            destination = observations / f'check-{index}.log'
            shutil.copyfile(c.pop('log'), destination)
            c['log_file'] = destination.name
            c['log_sha256'] = digest(destination)
    write(observations / 'checks.json', checks)
    write(observations / 'record.json', {
        'schema_version': 1, 'agent': args.agent, 'model': args.model,
        'trace_kind': args.trace_kind,
        'trace_sha256': digest(observations / 'trace.txt'),
        'checks_sha256': digest(observations / 'checks.json'),
        'note': 'Operator-provided evidence. Exit status alone does not prove test collection or correctness.',
    })
    print(observations)


def invoke(args: argparse.Namespace) -> None:
    root = args.run.resolve()
    meta = read(root / 'eval-run.json')
    if source_digest(Path(meta['source'])) != meta['source_digest']:
        raise ValueError('source changed since prepare; create a fresh run from a frozen checkout')
    case = args.case
    if case not in meta['cases']:
        raise ValueError(f'unknown case: {case}')
    definition = read(root / 'run_manifest.json')['cases'][case]
    target = Path(definition['target']).resolve()
    output = root / 'invocations' / case
    if output.exists():
        raise ValueError(f'invocation already exists: {output}')
    if not args.command:
        raise ValueError('provide an explicit agent executable after --command')
    prompt_file = output / 'prompt.txt'
    command = [part.replace('{target}', str(target)).replace('{prompt_file}', str(prompt_file))
               for part in args.command]
    if args.dry_run:
        print(json.dumps({'cwd': str(target), 'argv': command,
                          'prompt': definition['prompt'], 'agent': args.agent,
                          'note': 'No sandbox or egress restrictions are installed by this harness.'}, indent=2))
        return
    output.mkdir(parents=True)
    prompt_file.write_text(definition['prompt'] + '\n', encoding='utf-8')
    started = time.monotonic()
    with prompt_file.open('rb') as stdin, (output / 'stdout.txt').open('wb') as stdout, \
            (output / 'stderr.txt').open('wb') as stderr:
        try:
            completed = subprocess.run(command, cwd=target, stdin=stdin, stdout=stdout,
                                       stderr=stderr, timeout=args.timeout, check=False)
            code = completed.returncode
        except subprocess.TimeoutExpired:
            code = 124
        except OSError as exc:
            stderr.write(str(exc).encode('utf-8', errors='replace'))
            code = 127
    write(output / 'invocation.json', {
        'schema_version': 1, 'agent': args.agent, 'model': args.model,
        'argv': command, 'cwd': str(target), 'exit_code': code,
        'duration_seconds': round(time.monotonic() - started, 3),
        'prompt_sha256': digest(prompt_file),
        'note': 'Invocation exit code is not proof that any project test ran; attach checks separately.',
    })
    print(json.dumps({'path': str(output), 'exit_code': code}, indent=2))


def repos(case: str, path: Path, suite: str) -> dict[str, Path]:
    requirement = EXPECTED[suite][case]
    return {name: path / name for name in requirement} if isinstance(requirement, dict) else {'.': path}


def assertions(path: Path, required: list[str], observed: dict | None) -> dict:
    agents = path / '.agents'
    config = agents / 'commands.json'
    try:
        registry = read(config) if config.is_file() else {}
        components = registry.get('components', {})
        paths = {v.get('path', '') for v in components.values() if isinstance(v, dict)}
        argv_blob = json.dumps(registry.get('components', {})).lower()
    except (ValueError, TypeError):
        components, paths, argv_blob = {}, set(), ''
    missing_native = []
    for component_path in required:
        package = path / component_path / 'package.json'
        if package.is_file():
            try:
                scripts = read(package).get('scripts', {})
            except (ValueError, TypeError):
                scripts = {}
            present = set().union(*(set(data.get('commands', {})) for data in components.values()
                if isinstance(data, dict) and data.get('path') == component_path)) if components else set()
            missing_native.extend(f'{component_path}:{name}' for name in ('test', 'lint', 'build')
                if name in scripts and name not in present)
    assessment = (agents / 'assessment.md').is_file()
    instructions = (path / 'AGENTS.md').is_file()
    prior_instructions = subprocess.run(['git', '-C', str(path), 'cat-file', '-e', 'HEAD:AGENTS.md'],
                                        capture_output=True).returncode == 0
    fixture_rev = subprocess.run(['git', '-C', str(path), 'rev-parse', 'HEAD^{tree}'],
                                 capture_output=True, text=True)
    fixture_files = subprocess.run(['git', '-C', str(path), 'ls-tree', '-r', 'HEAD'],
                                   capture_output=True, text=True)
    project_hash = hashlib.sha256('\n'.join(line for line in fixture_files.stdout.splitlines()
        if not line.split('\t')[-1].endswith('/AGENTS.md') and
           line.split('\t')[-1] != 'AGENTS.md').encode()).hexdigest() if fixture_files.returncode == 0 else None
    tracked_paths = [line.split('\t')[-1] for line in fixture_files.stdout.splitlines() if '\t' in line]
    fixture_has_tests = any(name.startswith(('tests/', 'test/')) or
        '/tests/' in name or '/test/' in name or name.endswith(('_test.go', '.test.js', '.test.jsx'))
        for name in tracked_paths)
    changed = subprocess.run(['git', '-C', str(path), 'status', '--porcelain', '--untracked-files=all'],
                             capture_output=True, text=True)
    changed_paths = [line[3:] for line in changed.stdout.splitlines() if len(line) > 3]
    application_edits = sorted(name for name in changed_paths if name.startswith((
        'src/', 'app/', 'backend/app/', 'tests/', 'test/', 'services/', 'apps/', 'packages/')) and
        not name.startswith(('apps/.agents/', 'services/.agents/')))
    skill = (agents / 'skills/bootstrap-agent-env/SKILL.md').is_file()
    ci = any((path / '.github/workflows').glob('*.yml')) or any((path / '.github/workflows').glob('*.yaml'))
    ci_files = list((path / '.github/workflows').glob('*.yml')) + list((path / '.github/workflows').glob('*.yaml'))
    ci_steps = any(re.search(r'(?m)^\s*[-]?\s*(run|uses):', file.read_text(encoding='utf-8'))
                   for file in ci_files)
    ignore = (path / '.gitignore').read_text() if (path / '.gitignore').is_file() else ''
    ignored_cache = bool(re.search(r'(?m)^\s*\.?/?\.local/?\s*$', ignore))
    release = {}
    inventory = {
        'container': any(path.rglob('Dockerfile')) or any(path.rglob('Containerfile')),
        'compose': any(path.rglob('compose.yaml')) or any(path.rglob('docker-compose.yml')),
        'kubernetes': any((path / d).exists() for d in ('deploy/k8s', 'k8s', 'manifests')),
        'helm': any(path.rglob('Chart.yaml')),
    }
    for kind, present in inventory.items():
        if present:
            release[kind] = any(token in argv_blob for token in KINDS[kind])
    try:
        receipt = read(agents / 'bootstrap.json') if (agents / 'bootstrap.json').is_file() else {}
        receipt_valid = isinstance(receipt, dict)
        if not receipt_valid:
            receipt = {}
    except (ValueError, TypeError):
        receipt, receipt_valid = {}, False
    applied = receipt.get('applied_version')
    checks = observed.get('checks', []) if observed else []
    successful = [c['id'] for c in checks if c['exit_code'] == 0]
    # Passing check receipts are observations, not independent verification of test quality.
    structural = {'assessment': assessment, 'instructions': instructions, 'installed_skill': skill,
                  'ci_configured': ci, 'ci_steps_present': ci_steps,
                  'cache_ignored': ignored_cache, 'bootstrap_record_valid': receipt_valid,
                  'required_components': all(item in paths for item in required),
                  'native_scripts_covered': not missing_native,
                  'release_checks_configured': all(release.values())}
    return {'structural': structural, 'release': release, 'registered_paths': sorted(paths),
            'fixture_tree': fixture_rev.stdout.strip() if fixture_rev.returncode == 0 else None,
            'fixture_project_digest': project_hash,
            'fixture_has_tests': fixture_has_tests,
            'missing_native_scripts': missing_native,
            'changed_paths': changed_paths, 'application_edits_review': application_edits,
            'instructions_origin': 'fixture' if prior_instructions else 'agent_or_preexisting_untracked',
            'agent': observed['record']['agent'] if observed else None,
            'model': observed['record']['model'] if observed else None,
            'trace_kind': observed['record'].get('trace_kind', 'unspecified') if observed else None,
            'version': {'applied': applied, 'pending': receipt.get('pending_version')},
            'observed_successful_checks': successful,
            'observed_failed_checks': [c['id'] for c in checks if c['exit_code'] != 0],
            'observed_checks': checks,
            'issues': ([name for name, passed in structural.items() if not passed] +
                       (['premature_finalize'] if applied and not receipt.get('pending_version') and (not observed or
                         not any(c['id'] == 'validate' and c['exit_code'] == 0 for c in checks) or
                         not structural['release_checks_configured']) else [])),
            'coverage': 'observed' if observed else 'unverified',
            'ci_execution': 'unverified',
        }


def grade(args: argparse.Namespace) -> None:
    root = args.run.resolve()
    meta = read(root / 'eval-run.json')
    manifest = read(root / 'run_manifest.json')
    if digest(root / 'run_manifest.json') != meta['manifest_hash']:
        raise ValueError('manifest changed since preparation')
    report = {'schema_version': 1, 'suite': meta['suite'], 'variant': meta['variant'],
              'replicate': meta.get('replicate', '1'),
              'source_revision': meta['source_revision'], 'source_digest': meta['source_digest'],
              'target_agents_sha256': meta.get('target_agents_sha256'),
              'instruction_hashes': meta['instruction_hashes'], 'host': meta['host'],
              'source_drift': source_digest(Path(meta['source'])) != meta['source_digest'],
              'cases': {}}
    for case in meta['cases']:
        path = Path(manifest['cases'][case]['target'])
        observation = root / 'observations' / case
        observed = None
        if (observation / 'record.json').is_file():
            rec = read(observation / 'record.json')
            if (observation / 'trace.txt').is_file() and (observation / 'checks.json').is_file() and \
                    rec['trace_sha256'] == digest(observation / 'trace.txt') and \
                    rec['checks_sha256'] == digest(observation / 'checks.json'):
                observed = {'record': rec, 'checks': read(observation / 'checks.json')}
                for check in observed['checks']:
                    if 'log_file' in check:
                        logfile = observation / check['log_file']
                        if not logfile.is_file() or check.get('log_sha256') != digest(logfile):
                            raise ValueError(f'check log integrity mismatch: {case}')
            else:
                raise ValueError(f'observation integrity mismatch: {case}')
        needed = EXPECTED[meta['suite']][case]
        report['cases'][case] = {
            name: assertions(repo, needed[name] if isinstance(needed, dict) else needed, observed)
            for name, repo in repos(case, path, meta['suite']).items()
        }
    write(root / 'grade.json', report)
    print(json.dumps(report, indent=2))


def compare(args: argparse.Namespace) -> None:
    before, after = read(args.before), read(args.after)
    if before['suite'] != after['suite'] or before['cases'].keys() != after['cases'].keys():
        raise ValueError('comparison requires the same suite and cases')
    rows = []
    for case in before['cases']:
        if before['cases'][case].keys() != after['cases'][case].keys():
            raise ValueError(f'different repositories within case {case}')
        for repo in before['cases'][case]:
            old, new = before['cases'][case][repo], after['cases'][case][repo]
            rows.append({'case': case, 'repository': repo,
                         'fixture_matches': old['fixture_tree'] == new['fixture_tree'],
                         'model_matches': old['model'] == new['model'] if old['model'] and new['model'] else None,
                         'old_issues': old['issues'], 'new_issues': new['issues'],
                         'resolved': sorted(set(old['issues']) - set(new['issues'])),
                         'regressions': sorted(set(new['issues']) - set(old['issues'])),
                         'old_coverage': old['coverage'], 'new_coverage': new['coverage']})
    print(json.dumps({'comparability': 'structural only; model/settings/host/trace differences require review',
                      'host_matches': before['host'] == after['host'],
                      'source_revisions': [before['source_revision'], after['source_revision']],
                      'source_digests': [before['source_digest'], after['source_digest']],
                      'target_agents_sha256': [before['target_agents_sha256'], after['target_agents_sha256']],
                      'results': rows}, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('prepare', help='generate fresh fixture and hidden grading metadata')
    p.add_argument('--suite', choices=sorted(GENERATORS), required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--source', type=Path, default=REPO)
    p.add_argument('--agents-file', type=Path, help='preload this AGENTS.md into each fixture commit')
    p.add_argument('--variant', choices=['skill', 'none'], default='skill')
    p.add_argument('--replicate', default='1', help='matched repeat identifier, e.g. 1, 2, 3')
    p.set_defaults(func=prepare)
    p = sub.add_parser('record', help='attach operator-observed agent trace and command receipts')
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--case', required=True)
    p.add_argument('--agent', required=True)
    p.add_argument('--model', required=True)
    p.add_argument('--trace', type=Path, required=True)
    p.add_argument('--trace-kind', choices=['raw', 'summary', 'output'], default='raw',
                   help='label whether this is a full trace or only a summary/output')
    p.add_argument('--checks', type=Path, required=True)
    p.set_defaults(func=record)
    p = sub.add_parser('invoke', help='explicitly launch an available agent CLI, with no implicit sandbox')
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--case', required=True)
    p.add_argument('--agent', required=True)
    p.add_argument('--model', required=True)
    p.add_argument('--timeout', type=int, default=1200)
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--command', nargs=argparse.REMAINDER, required=True,
                   help='agent CLI argv; use {target}, {prompt_file}, or stdin for the prompt')
    p.set_defaults(func=invoke)
    p = sub.add_parser('grade', help='grade resulting filesystem without running project code')
    p.add_argument('--run', type=Path, required=True)
    p.set_defaults(func=grade)
    p = sub.add_parser('compare', help='show structural regressions for paired runs')
    p.add_argument('--before', type=Path, required=True)
    p.add_argument('--after', type=Path, required=True)
    p.set_defaults(func=compare)
    p = sub.add_parser('score', help='apply an evidence-backed reviewer rubric to one graded run')
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--review', type=Path, required=True)
    p.set_defaults(func=evaluate)
    p = sub.add_parser('compare-scores', help='compare matched repeated scored runs')
    p.add_argument('--baseline', type=Path, nargs='+', required=True)
    p.add_argument('--candidate', type=Path, nargs='+', required=True)
    p.set_defaults(func=compare_scores)
    args = parser.parse_args()
    try:
        args.func(args)
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
