"""Offline regression checks. No LLM calls or live GitHub writes."""
from __future__ import annotations
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate_package import manifest_entries, package_files, validate  # noqa: E402


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='income-map-test-')
        self.base = Path(self.temp.name)
        self.home = self.base / 'home with spaces'
        self.home.mkdir()
        self.source = self.base / 'source' / 'income-opportunity-map'
        shutil.copytree(ROOT, self.source, ignore=shutil.ignore_patterns('.git', '__pycache__'))
        self.env = os.environ.copy()
        self.env.update({'HOME': str(self.home), 'PYTHONDONTWRITEBYTECODE': '1'})
        self.target = self.home / '.agents/skills/income-opportunity-map'

    def tearDown(self):
        self.temp.cleanup()

    def install(self, *args):
        return subprocess.run(['bash', str(self.source / 'install.sh'), *args], env=self.env,
                              text=True, capture_output=True)

    def rehash(self):
        files = package_files(self.source)
        (self.source/'SHA256SUMS').write_text(''.join(
            f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(self.source).as_posix()}\n'
            for p in files if p.name != 'SHA256SUMS'))

    def test_01_complete_package(self):
        self.assertEqual(validate(self.source), [])

    def test_02_bash_syntax(self):
        for script in ['install.sh', 'publish-github.sh']:
            result = subprocess.run(['bash', '-n', str(self.source/script)], capture_output=True)
            self.assertEqual(result.returncode, 0)

    def test_03_help_does_not_install(self):
        self.assertEqual(self.install('--help').returncode, 0)
        self.assertFalse((self.home/'.agents').exists())

    def test_04_missing_check_no_write(self):
        self.assertNotEqual(self.install('--check').returncode, 0)
        self.assertFalse((self.home/'.agents').exists())

    def test_05_default_install_and_check(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(validate(self.target), [])
        self.assertEqual(self.install('--check').returncode, 0)

    def test_06_no_global_config(self):
        self.assertEqual(self.install().returncode, 0)
        self.assertFalse((self.home/'.codex/config.toml').exists())
        self.assertFalse((self.home/'.gitconfig').exists())

    def test_07_idempotent(self):
        self.assertEqual(self.install().returncode, 0)
        before = {p.relative_to(self.target): p.stat().st_mtime_ns for p in package_files(self.target)}
        self.assertEqual(self.install().returncode, 0)
        after = {p.relative_to(self.target): p.stat().st_mtime_ns for p in package_files(self.target)}
        self.assertEqual(before, after)

    def test_08_refuses_modified_target(self):
        self.assertEqual(self.install().returncode, 0)
        (self.target/'SKILL.md').write_text('my local edits\n')
        self.assertNotEqual(self.install().returncode, 0)
        self.assertEqual((self.target/'SKILL.md').read_text(), 'my local edits\n')

    def test_09_check_detects_change(self):
        self.assertEqual(self.install().returncode, 0)
        (self.target/'README.md').write_text('modified\n')
        self.assertNotEqual(self.install('--check').returncode, 0)

    def test_10_custom_location(self):
        dest = self.base/'another location/skills'
        r = self.install('--skills-dir', str(dest))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((dest/'income-opportunity-map/SKILL.md').is_file())

    def test_11_relative_location_refused(self):
        self.assertNotEqual(self.install('--skills-dir', 'relative').returncode, 0)

    def test_12_missing_argument_refused(self):
        self.assertNotEqual(self.install('--skills-dir').returncode, 0)

    def test_13_target_symlink_refused(self):
        self.target.parent.mkdir(parents=True)
        self.target.symlink_to(self.source, target_is_directory=True)
        self.assertNotEqual(self.install().returncode, 0)

    def test_14_modified_source_refused(self):
        (self.source/'README.md').write_text('modified\n')
        self.assertNotEqual(self.install().returncode, 0)
        self.assertFalse(self.target.exists())

    def test_15_git_history_not_copied(self):
        (self.source/'.git').mkdir()
        (self.source/'.git/config').write_text('[test]\n')
        self.assertEqual(validate(self.source), [])
        self.assertEqual(self.install().returncode, 0)
        self.assertFalse((self.target/'.git').exists())

    def test_16_unlisted_private_file_not_copied(self):
        (self.source/'local-notes.txt').write_text('not for distribution\n')
        self.assertEqual(self.install().returncode, 0)
        self.assertFalse((self.target/'local-notes.txt').exists())
        self.assertTrue(validate(self.source))  # publication is stricter than installation

    def test_17_source_symlink_refused(self):
        file = self.source/'README.md'
        file.unlink()
        file.symlink_to(ROOT/'README.md')
        self.assertNotEqual(self.install().returncode, 0)
        self.assertTrue(validate(self.source))

    def test_18_escaping_manifest_refused(self):
        with (self.source/'SHA256SUMS').open('a') as f:
            f.write('0'*64 + '  ../outside.txt\n')
        self.assertNotEqual(self.install().returncode, 0)
        self.assertTrue(validate(self.source))
        self.assertFalse(self.target.exists())

    def test_19_duplicate_manifest_refused(self):
        p = self.source/'SHA256SUMS'
        text = p.read_text()
        p.write_text(text + text.splitlines()[0] + '\n')
        self.assertNotEqual(self.install().returncode, 0)
        self.assertTrue(validate(self.source))

    def test_20_source_nested_destination_refused(self):
        dest = self.source/'.agents/skills'
        self.assertNotEqual(self.install('--skills-dir', str(dest)).returncode, 0)
        self.assertFalse(dest.exists())

    def test_21_publish_dry_run_offline(self):
        result = subprocess.run([sys.executable, '-B', str(self.source/'scripts/publish_github.py'),
                                 '--dry-run'], env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('DRY RUN', result.stdout)
        self.assertFalse((self.source/'.git').exists())

    def test_22_invalid_repo_name_refused(self):
        result = subprocess.run([sys.executable, '-B', str(self.source/'scripts/publish_github.py'),
                                 '--dry-run', '--repo', '../wrong'], env=self.env, capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    def test_23_broken_reference_detected(self):
        with (self.source/'README.md').open('a') as f:
            f.write('\n[broken](missing-file.md)\n')
        self.assertTrue(any('Broken link' in e for e in validate(self.source, skip_manifest=True)))

    def test_24_duplicate_example_id_detected(self):
        p = self.source/'examples/digital-products.md'
        p.write_text(p.read_text().replace('| O25 ', '| O24 '))
        self.assertTrue(any('O01 through O25' in e for e in validate(self.source, skip_manifest=True)))

    def test_25_manifest_metadata_change_detected(self):
        self.assertEqual(self.install().returncode, 0)
        (self.target/'SHA256SUMS').write_text('edited manifest\n')
        self.assertNotEqual(self.install('--check').returncode, 0)

    def test_26_lock_respected(self):
        lock = self.target.parent/'.income-opportunity-map-install-lock'
        lock.mkdir(parents=True)
        self.assertNotEqual(self.install().returncode, 0)
        self.assertTrue(lock.exists())
        self.assertFalse(self.target.exists())

    def test_27_github_zip_directory_name_supported(self):
        alias = self.base/'income-opportunity-map-main'
        shutil.copytree(self.source, alias)
        self.assertEqual(validate(alias), [])
        result = subprocess.run(['bash', str(alias/'install.sh')], env=self.env,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.target/'SKILL.md').is_file())

    def test_28_source_alias_nested_destination_refused_without_write(self):
        alias = self.base / 'source alias'
        alias.symlink_to(self.source, target_is_directory=True)
        dest = alias / '.agents/skills'
        result = self.install('--skills-dir', str(dest))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.source / '.agents').exists())

if __name__ == '__main__':
    unittest.main()
