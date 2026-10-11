#!/usr/bin/env python3
"""Validate this package (Python 3.9+, standard library; no network/model calls)."""
from __future__ import annotations
import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = 'income-opportunity-map'


def package_files(root: Path) -> list[Path]:
    """Return source files, excluding only Git internals; reject symlinks."""
    files = []
    for p in root.rglob('*'):
        rel = p.relative_to(root)
        if '.git' in rel.parts:
            continue
        if p.is_symlink():
            raise ValueError(f'Symlink not allowed: {rel}')
        if '__pycache__' in rel.parts:
            raise ValueError('Remove __pycache__; run Python with -B')
        if p.is_file():
            files.append(p)
    return sorted(files)


def manifest_entries(root: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    path = root / 'SHA256SUMS'
    if path.is_symlink():
        raise ValueError('SHA256SUMS must not be a symlink')
    for line in path.read_text(encoding='utf-8').splitlines():
        match = re.fullmatch(r'([a-f0-9]{64})  ([A-Za-z0-9._/-]+)', line)
        if not match:
            raise ValueError('Malformed SHA256SUMS line')
        digest, relative = match.groups()
        parts = relative.split('/')
        if any(p in ('', '.', '..', '.git') for p in parts) or relative.startswith('-'):
            raise ValueError(f'Unsafe manifest path: {relative}')
        if relative == 'SHA256SUMS' or relative in entries:
            raise ValueError(f'Duplicate/self manifest path: {relative}')
        target = root
        for part in parts:
            target = target / part
            if target.is_symlink():
                raise ValueError(f'Symlink in manifest path: {relative}')
        if not target.resolve().is_relative_to(root.resolve()):
            raise ValueError(f'Path escapes package: {relative}')
        entries[relative] = digest
    if not entries or 'SKILL.md' not in entries:
        raise ValueError('Manifest is empty or missing SKILL.md')
    return entries


def validate(root: Path, skip_manifest: bool = False) -> list[str]:
    errors: list[str] = []
    def require(ok: bool, message: str) -> None:
        if not ok:
            errors.append(message)

    required = [
        'SKILL.md', 'README.md', 'LICENSE', 'agents/openai.yaml', 'install.sh',
        'publish-github.sh', 'PUBLISHING.md', 'CONTRIBUTING.md', 'CHANGELOG.md',
        'references/income-taxonomy.md', 'references/expansion-and-evidence.md',
        'references/comparison-and-validation.md', 'assets/output-templates.md',
        'examples/digital-products.md', 'examples/photography.md',
        'tests/acceptance-cases.md', 'tests/test_package.py',
        'scripts/update_manifest.py', 'scripts/publish_github.py', 'sources.md',
    ]
    for relative in required:
        require((root / relative).is_file(), f'Missing file: {relative}')
    if not (root / 'SKILL.md').is_file():
        return errors
    try:
        files = package_files(root)
        skill = (root / 'SKILL.md').read_text(encoding='utf-8')
        match = re.match(r'\A---\n(.*?)\n---\n', skill, re.S)
        require(match is not None, 'Missing YAML frontmatter delimiters')
        if match:
            header = match.group(1)
            nm = re.search(r'^name:\s*([a-z0-9-]+)\s*$', header, re.M)
            require(nm is not None, 'Malformed skill name')
            if nm:
                name = nm.group(1)
                require(1 <= len(name) <= 64 and '--' not in name and
                        not name.startswith('-') and not name.endswith('-'), 'Invalid name')
                require(name == NAME, 'Unexpected skill name')
                if root.parent.name == 'skills':
                    require(name == root.name, 'Installed folder name must match skill name')
            desc = re.search(r'^description:\s*>-?\n((?:[ \t]+[^\n]*\n?)+)', header, re.M)
            require(desc is not None, 'Expected folded description')
            if desc:
                text = ' '.join(line.strip() for line in desc.group(1).splitlines())
                require(1 <= len(text) <= 1024, 'Description length out of range')
            require(re.search(r'^  version: "\d+\.\d+\.\d+"$', header, re.M) is not None,
                    'Version metadata must be a quoted semantic version')
            require('license: MIT' in header, 'MIT license metadata missing')
        for file in files:
            if file.suffix in {'.md', '.yaml', '.py', '.sh'}:
                text = file.read_text(encoding='utf-8')
                require('\x00' not in text, f'Null byte in {file.name}')
                if file.suffix == '.py':
                    compile(text, str(file), 'exec')
                if file.suffix == '.md':
                    prose = re.sub(r'```.*?```', '', text, flags=re.S)
                    for target in re.findall(r'\]\(([^)]+)\)', prose):
                        if '://' in target or target.startswith(('#', 'mailto:')):
                            continue
                        candidate = (file.parent / target.split('#', 1)[0]).resolve()
                        require(candidate.is_relative_to(root.resolve()), f'Escaping link: {target}')
                        require(candidate.is_file(), f'Broken link in {file.name}: {target}')
        ui = (root / 'agents/openai.yaml').read_text(encoding='utf-8')
        for field in ('display_name', 'short_description', 'default_prompt'):
            require(re.search(rf'^  {field}: "[^\n]+"$', ui, re.M) is not None,
                    f'Missing UI field: {field}')
        require('$income-opportunity-map' in ui, 'Missing invocation in default prompt')
        example = (root / 'examples/digital-products.md').read_text(encoding='utf-8')
        ids = re.findall(r'^\| (O\d{2}) ', example, re.M)
        require(ids == [f'O{i:02d}' for i in range(1, 26)], 'Expected O01 through O25 once each')
        for i in range(1, 10):
            require(f'### M{i:02d}' in example, f'Missing category M{i:02d}')
        require('交易结构假设' in example, 'Example must label hypotheses')
        if not skip_manifest:
            entries = manifest_entries(root)
            actual = {p.relative_to(root).as_posix() for p in files if p.name != 'SHA256SUMS'}
            require(set(entries) == actual, 'Manifest differs from the complete source file set')
            for relative, expected in entries.items():
                p = root / relative
                require(p.is_file(), f'Missing hashed file: {relative}')
                if p.is_file():
                    require(hashlib.sha256(p.read_bytes()).hexdigest() == expected,
                            f'Hash mismatch: {relative}')
    except (OSError, ValueError, UnicodeError, SyntaxError) as exc:
        errors.append(str(exc))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', nargs='?', type=Path, default=ROOT)
    parser.add_argument('--skip-manifest', action='store_true', help='Editing only: skip hash checks')
    args = parser.parse_args()
    errors = validate(args.path.resolve(), args.skip_manifest)
    if errors:
        for error in errors:
            print(f'FAIL: {error}', file=sys.stderr)
        return 1
    print('PASS: structure, metadata, references, examples and requested hashes')
    print('NOT TESTED: host discovery, model behavior, or live GitHub publication')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
