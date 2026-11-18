"""Offline regression for existing-tag verification in check-release.yml."""
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'ghcr.io/develata/ustc-iwan-docker'
VERSION = 'v26.11.1'
INDEX = 'sha256:516d09ab47086f9255ad0885deaa17ea9ed1568a514a40fef49b36cdf1d3519a'
AMD64 = 'sha256:' + 'a' * 64
ARM64 = 'sha256:' + 'b' * 64


def inspect_text(digest=INDEX, with_header=True):
    """Representative Buildx multi-arch text with additional child digests."""
    header = f'Digest:    {digest}\n' if with_header else ''
    return (
        f'Name:      {IMAGE}:{VERSION}\n'
        'MediaType: application/vnd.oci.image.index.v1+json\n'
        + header + '\nManifests:\n'
        f'  Name:      {IMAGE}@{AMD64}\n'
        f'  Digest:    {AMD64}\n'
        '  Platform:  linux/amd64\n\n'
        f'  Name:      {IMAGE}@{ARM64}\n'
        f'  Digest:    {ARM64}\n'
        '  Platform:  linux/arm64\n'
    )


class ExistingReleaseVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        workflow = (ROOT / '.github/workflows/check-release.yml').read_text()
        step = workflow.split(
            '      - name: Verify existing immutable version on both architectures\n', 1)[1]
        block = step.split('        run: |\n', 1)[1].split('\n      - ', 1)[0]
        cls.command = textwrap.dedent(block)

    def invoke(self, output, inspect_status=0, smoke_status=0):
        with tempfile.TemporaryDirectory() as dirname:
            work = Path(dirname)
            tools = work / 'tools'
            tools.mkdir()
            scripts = work / 'scripts'
            scripts.mkdir()
            fixture = work / 'inspect.txt'
            fixture.write_text(output)
            capture = work / 'smoke-calls.txt'

            docker = tools / 'docker'
            docker.write_text('''#!/usr/bin/env python3
import os
from pathlib import Path
import sys
expected = ['buildx', 'imagetools', 'inspect', os.environ['IMAGE'] + ':' + os.environ['UPSTREAM_VERSION']]
if sys.argv[1:] != expected:
    print('Unexpected Docker invocation: ' + repr(sys.argv[1:]), file=sys.stderr)
    sys.exit(91)
with open(os.environ['FIXTURE_INSPECT'], 'rb') as stream:
    try:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            os.write(1, chunk)
    except BrokenPipeError:
        os._exit(255)
sys.exit(int(os.environ['FIXTURE_INSPECT_STATUS']))
''')
            docker.chmod(0o755)
            smoke = scripts / 'smoke-image.sh'
            smoke.write_text('''#!/bin/sh
printf '%s\\n' "$1" "$2" >> "$FIXTURE_SMOKE_CALLS"
exit "$FIXTURE_SMOKE_STATUS"
''')
            env = dict(
                os.environ, PATH=f'{tools}:{os.environ["PATH"]}',
                IMAGE=IMAGE, UPSTREAM_VERSION=VERSION,
                FIXTURE_INSPECT=str(fixture),
                FIXTURE_INSPECT_STATUS=str(inspect_status),
                FIXTURE_SMOKE_CALLS=str(capture),
                FIXTURE_SMOKE_STATUS=str(smoke_status),
            )
            result = subprocess.run(
                ['bash', '-c', self.command], env=env, cwd=work,
                capture_output=True, text=True, timeout=15)
            return result, capture.read_text() if capture.exists() else None

    def test_large_multiline_output_selects_index_not_child(self):
        # Much larger than a pipe buffer: catches early-reader exit / SIGPIPE.
        output = inspect_text() + (f'  Name: {IMAGE}@{ARM64}\n' * 40000)
        result, call = self.invoke(output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(call, f'{IMAGE}@{INDEX}\n{VERSION}\n')

    def test_missing_top_level_digest_rejects_child_digests(self):
        result, call = self.invoke(inspect_text(with_header=False))
        self.assertEqual(result.returncode, 1)
        self.assertIn('Could not resolve the immutable image index digest', result.stderr)
        self.assertIsNone(call)

    def test_missing_and_invalid_index_digest_fail_closed(self):
        bad = ('', 'sha256:abc', 'sha256:' + 'f' * 63,
               'sha256:' + 'A' * 64, 'sha256:' + 'g' * 64,
               'sha512:' + 'a' * 64, INDEX + 'tail')
        for digest in bad:
            with self.subTest(digest=digest):
                result, call = self.invoke(inspect_text(digest=digest))
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn('Could not resolve the immutable image index digest', result.stderr)
                self.assertIsNone(call)

    def test_duplicate_top_level_digests_rejected(self):
        result, call = self.invoke(inspect_text() + f'Digest: {AMD64}\n')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('Could not resolve the immutable image index digest', result.stderr)
        self.assertIsNone(call)

    def test_inspect_nonzero_even_if_it_printed_valid_digest(self):
        result, call = self.invoke(inspect_text(), inspect_status=73)
        self.assertEqual(result.returncode, 73, result.stderr)
        self.assertIsNone(call)

    def test_smoke_failure_is_not_converted_to_success(self):
        result, call = self.invoke(inspect_text(), smoke_status=47)
        self.assertEqual(result.returncode, 47, result.stderr)
        self.assertEqual(call, f'{IMAGE}@{INDEX}\n{VERSION}\n')


if __name__ == '__main__':
    unittest.main()
