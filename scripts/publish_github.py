#!/usr/bin/env python3
"""Publish reviewed files to a NEW public GitHub repo; explicit execution only.

A dry run is offline. Live mode requires GitHub CLI authentication, creates a
fresh staging history, and never overwrites an existing repository.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from validate_package import ROOT, manifest_entries, validate


def checked(args: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(args, cwd=cwd, env=env, text=True, capture_output=True)
    if result.returncode:
        # No command contains a token; do not print credential values.
        raise RuntimeError(f'{args[0]} command failed: {result.stderr.strip()}')
    return result.stdout.strip()


def safe_identifier(value: str, *, owner: bool = False) -> bool:
    if owner:
        return bool(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?', value))
    return bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,99}', value)) and value not in {'.', '..'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner', help='Default: currently authenticated GitHub user')
    parser.add_argument('--repo', default='income-opportunity-map')
    parser.add_argument('--dry-run', action='store_true', help='Offline preview; no writes')
    parser.add_argument('--yes', action='store_true', help='Explicitly confirm a NEW PUBLIC repository')
    args = parser.parse_args()
    if not safe_identifier(args.repo) or (args.owner and not safe_identifier(args.owner, owner=True)):
        parser.error('Invalid repository name or owner')
    errors = validate(ROOT)
    if errors:
        raise RuntimeError('Package validation failed: ' + '; '.join(errors))
    entries = manifest_entries(ROOT)
    files = sorted([*entries, 'SHA256SUMS'])
    target = f'{args.owner or "<authenticated-user>"}/{args.repo}'
    print(f'Target: {target}; visibility: PUBLIC; files: {len(files)}')
    if args.dry_run:
        for name in files:
            print(f'  {name}')
        print('DRY RUN: no network, no installation, no repository created or pushed.')
        return 0
    for tool in ('git', 'gh'):
        if not shutil.which(tool):
            raise RuntimeError(f'Missing {tool}. Live publication has not started.')

    env = os.environ.copy()
    env.update({'GH_HOST': 'github.com', 'GH_PROMPT_DISABLED': '1', 'GIT_TERMINAL_PROMPT': '0'})
    # Honor the user's logged-in gh account, but not unrelated source Git contexts.
    for key in list(env):
        if key.startswith(('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR',
                           'GIT_AUTHOR_', 'GIT_COMMITTER_')):
            env.pop(key)
    checked(['gh', 'auth', 'status', '--hostname', 'github.com'], cwd=ROOT, env=env)
    identity = json.loads(checked(['gh', 'api', 'user', '--jq', '{login: .login, id: .id}'], cwd=ROOT, env=env))
    login, uid = identity['login'], identity['id']
    if not safe_identifier(login, owner=True) or not isinstance(uid, int) or uid < 1:
        raise RuntimeError('Invalid authenticated GitHub identity')
    owner = args.owner or login
    target = f'{owner}/{args.repo}'
    probe = subprocess.run(['gh', 'api', f'repos/{target}'], cwd=ROOT, env=env,
                           text=True, capture_output=True)
    if probe.returncode == 0:
        raise RuntimeError(f'Repository already exists: {target}. It was not changed.')
    if 'HTTP 404' not in probe.stderr:
        raise RuntimeError('Could not establish repository absence; no remote write attempted.')
    print(f'Will create PUBLIC repository {target} under authenticated user {login}.')
    print('Only reviewed manifest files are sent, with a fresh initial commit; existing repos are never replaced.')
    if not args.yes:
        if not sys.stdin.isatty():
            raise RuntimeError('A public write requires interactive confirmation or explicit --yes.')
        if input('Type PUBLISH to continue: ').strip() != 'PUBLISH':
            print('Cancelled. No repository created.')
            return 0

    with tempfile.TemporaryDirectory(prefix='income-map-publish-') as temp:
        staging = Path(temp) / 'income-opportunity-map'
        staging.mkdir()
        for relative in files:
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
        stage_errors = validate(staging)
        if stage_errors:
            raise RuntimeError('Staged snapshot validation failed: ' + '; '.join(stage_errors))
        # Clean history; suppress inherited hooks, templates and commit signing.
        template = Path(temp) / 'empty-template'
        template.mkdir()
        checked(['git', 'init', '--initial-branch=main', f'--template={template}'], cwd=staging, env=env)
        checked(['git', 'config', '--local', 'core.hooksPath', '/dev/null'], cwd=staging, env=env)
        checked(['git', 'config', '--local', 'core.autocrlf', 'false'], cwd=staging, env=env)
        base = ['git', '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false',
                '-c', f'user.name={login}', '-c', f'user.email={uid}+{login}@users.noreply.github.com']
        checked([*base, 'add', '--', *files], cwd=staging, env=env)
        checked([*base, 'commit', '-m', 'Initial open-source release: income opportunity map v1.0.1'],
                cwd=staging, env=env)
        expected = checked(['git', 'rev-parse', 'HEAD'], cwd=staging, env=env)
        try:
            checked(['gh', 'repo', 'create', target, '--public', '--source', str(staging),
                     '--remote', 'origin', '--push', '--description',
                     '从兴趣、能力与行业展开收入路径的 Agent Skill / Income Opportunity Map'],
                    cwd=staging, env=env)
            info = json.loads(checked(['gh', 'repo', 'view', target, '--json', 'url,isPrivate'],
                                      cwd=staging, env=env))
            remote_sha = checked(['gh', 'api', f'repos/{target}/commits/main', '--jq', '.sha'],
                                 cwd=staging, env=env)
            if info.get('isPrivate') is not False or remote_sha != expected:
                raise RuntimeError('Remote visibility or commit does not match the staged snapshot')
            print(f'PUBLISHED: {info["url"]}')
            print(f'Verified remote main commit: {expected}')
        except RuntimeError as error:
            raise RuntimeError(f'Publication not verified. A repository may have been created at {target}; '
                               'inspect it before retrying. Nothing is automatically deleted. ' + str(error)) from error
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        raise SystemExit(1)
