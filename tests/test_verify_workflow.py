"""Run the verification workflow's input guard offline, without Docker or HTTP."""
import os
from pathlib import Path
import subprocess
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
VALID_DIGEST = 'sha256:' + '0123456789abcdef' * 4


class VerifyWorkflowInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        workflow = (ROOT / '.github/workflows/verify-image.yml').read_text()
        step = workflow.split(
            '      - name: Validate immutable image reference and expected version\n', 1)[1]
        block = step.split('        run: |\n', 1)[1].split('\n      - ', 1)[0]
        cls.guard = textwrap.dedent(block)

    def invoke(self, digest=VALID_DIGEST, version='v26.11.1'):
        env = dict(os.environ, IMAGE_DIGEST=digest, UPSTREAM_VERSION=version)
        return subprocess.run(['bash', '-c', self.guard], env=env, text=True,
                              capture_output=True, timeout=10)

    def test_valid_digest_and_optional_v_versions(self):
        for version in ('26.11.1', 'v26.11.1'):
            with self.subTest(version=version):
                result = self.invoke(version=version)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_digest_is_rejected(self):
        for digest in (
                '', 'stable', 'sha256:abc', 'sha256:' + 'g' * 64,
                'sha256:' + 'A' * 64, 'sha512:' + 'a' * 64,
                'ghcr.io/develata/ustc-iwan-docker@' + VALID_DIGEST,
                ' ' + VALID_DIGEST, VALID_DIGEST + '\n'):
            with self.subTest(digest=digest):
                result = self.invoke(digest=digest)
                self.assertEqual(result.returncode, 1)
                self.assertIn('Expected a SHA-256 image index digest', result.stderr)

    def test_invalid_version_is_rejected(self):
        for version in (
                '', 'v', 'vv26.11.1', 'V26.11.1', '26.11', '26.11.1.0',
                '26.11.1-rc.1', '26.11.1+build', ' v26.11.1',
                'v26.11.1\n', '26.11.1; exit 0'):
            with self.subTest(version=version):
                result = self.invoke(version=version)
                self.assertEqual(result.returncode, 1)
                self.assertIn('Expected a stable release version', result.stderr)
