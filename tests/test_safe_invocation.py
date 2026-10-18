"""Offline CLI safety checks: no credentials, network, or live workflow execution."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which('bash')


class SafeInvocationTests(unittest.TestCase):
    def run_cli(self, args=(), live=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = root / 'calls'
            # PATH contains ONLY harmless stubs. Even the unpatched script cannot
            # reach real curl/jq or read credentials through them. The synthetic
            # suspended response stops the original before its engagement loop.
            for name in ('curl', 'jq', 'date'):
                stub = root / name
                stub.write_text('#!/bin/bash\nprintf "%s\\n" "$0" >> "$CALL_LOG"\nprintf "suspended\\n"\n')
                stub.chmod(0o755)
            env = {'PATH': str(root), 'HOME': str(root), 'CALL_LOG': str(calls), 'LC_ALL': 'C'}
            if live is not None:
                env['MOLTBOOK_LIVE'] = live
            result = subprocess.run([BASH, str(ROOT / 'bin/moltbook-engage'), *args],
                                    env=env, capture_output=True, text=True, timeout=5)
            self.assertFalse(calls.exists(), 'Invoked credential/network commands before safety exit')
            return result

    def test_default_is_offline(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0)
        self.assertIn('DRY-RUN', result.stdout)

    def test_only_exact_true_opts_in(self):
        for value in ('', 'false', '1', 'TRUE', 'yes'):
            with self.subTest(value=value):
                self.assertEqual(self.run_cli(live=value).returncode, 0)

    def test_dry_run_overrides_live(self):
        result = self.run_cli(['--dry-run'], live='true')
        self.assertEqual(result.returncode, 0)
        self.assertIn('DRY-RUN', result.stdout)

    def test_help_is_offline(self):
        for option in ('--help', '-h'):
            self.assertEqual(self.run_cli([option], live='true').returncode, 0)

    def test_unsupported_options_fail_closed(self):
        for option in ('--scan-only', '--post', '--replies', '--verbose', '--dryrun', '--live', 'unexpected'):
            with self.subTest(option=option):
                self.assertNotEqual(self.run_cli([option], live='true').returncode, 0)

    def test_bad_option_is_not_hidden_by_dry_run_or_help(self):
        for args in (['--dry-run', '--bad'], ['--help', '--bad'], ['--bad', '--dry-run']):
            self.assertNotEqual(self.run_cli(args, live='true').returncode, 0)

    def test_suspension_check_does_not_publish_a_test_post(self):
        text = (ROOT / 'bin/moltbook-engage').read_text()
        preflight = text.split('# === PART 1:')[0]
        self.assertNotIn('-X POST', preflight)
        self.assertNotIn('test_payload=', preflight)


if __name__ == '__main__':
    unittest.main()
