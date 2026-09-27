"""Inspect agent-produced project artifacts; does not execute project commands."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


def inspect_repo(repo: Path) -> dict:
    agent = repo / '.agents'
    commands_file = agent / 'commands.json'
    record_file = agent / 'bootstrap.json'
    commands = json.loads(commands_file.read_text()) if commands_file.exists() else {}
    record = json.loads(record_file.read_text()) if record_file.exists() else {}
    components = commands.get('components', {})
    status = subprocess.run(['git', '-C', str(repo), 'status', '--short'], capture_output=True, text=True)
    return {
        'path': str(repo), 'assessment': (agent / 'assessment.md').is_file(),
        'skill': (agent / 'skills/bootstrap-agent-env/SKILL.md').is_file(),
        'components': {name: {'path': data.get('path'),
                              'validate': data.get('commands', {}).get('validate', [])}
                       for name, data in components.items()},
        'version': {'applied': record.get('applied_version'), 'pending': record.get('pending_version')},
        'ci_files': sorted(str(p.relative_to(repo)) for p in (repo / '.github/workflows').glob('*.yml')),
        'git_changes': status.stdout.splitlines(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.manifest.read_text())
    report = {}
    for name, case in data['cases'].items():
        path = Path(case['target'])
        repositories = sorted(p for p in path.iterdir() if (p / '.git').is_dir()) if name.startswith('split') else [path]
        report[name] = [inspect_repo(repo) for repo in repositories]
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
