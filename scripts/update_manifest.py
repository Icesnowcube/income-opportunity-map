#!/usr/bin/env python3
"""Explicitly rebuild the file manifest after reviewing intended changes."""
from __future__ import annotations
import hashlib
from pathlib import Path
from validate_package import package_files, validate


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = validate(root, skip_manifest=True)
    if errors:
        for error in errors:
            print(f'FAIL: {error}')
        return 1
    lines = [f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root).as_posix()}\n'
             for p in package_files(root) if p.name != 'SHA256SUMS']
    (root / 'SHA256SUMS').write_text(''.join(lines), encoding='utf-8')
    print(f'Updated SHA256SUMS for {len(lines)} files; this is not a signature.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
