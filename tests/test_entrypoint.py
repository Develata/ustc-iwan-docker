"""Offline download regression tests; executables and HTTP are test fixtures."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = b'#!/bin/sh\nprintf "fixture client\\n"\n'
SHA = hashlib.sha256(PAYLOAD).hexdigest()


class EntrypointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.tools = self.work / 'tools'
        self.tools.mkdir()
        self.env = dict(os.environ, PATH=f'{self.tools}:{os.environ["PATH"]}',
                        IWAN_VERSION='v26.9.1', IWAN_CONFIG_DIR=str(self.work / 'config'),
                        IWAN_SHA256_AMD64=SHA, IWAN_SHA256_ARM64=SHA,
                        FIXTURE_DIR=str(self.work))
        # Accept only the exact new URL; do not mask filename regressions.
        self.tool('curl', '''#!/bin/sh
set -eu
printf 'download\n' >> "$FIXTURE_DIR/requests"
while [ "$#" -gt 0 ]; do
    case "$1" in
        https://*) url="$1" ;;
        -o) shift; output="$1" ;;
    esac
    shift
done
[ "$url" = "$FIXTURE_URL" ] || exit 22
cp "$FIXTURE_DIR/asset.zip" "$output"
''')

    def tool(self, name, text):
        path = self.tools / name
        path.write_text(text)
        path.chmod(0o755)

    def fixture(self, arch='x86_64', member=None):
        self.tool('uname', f'#!/bin/sh\nprintf "{arch}\\n"\n')
        asset = f'iwan-client-oidc-linux-{arch}-musl'
        self.env['FIXTURE_URL'] = (
            f'https://github.com/yyy1mu/ustc-iwan/releases/download/v26.9.1/{asset}.zip')
        with zipfile.ZipFile(self.work / 'asset.zip', 'w') as archive:
            archive.writestr(member or asset, PAYLOAD)

    def invoke(self):
        return subprocess.run(['sh', str(ROOT / 'entrypoint.sh'), '--version'],
                              env=self.env, text=True, capture_output=True, timeout=10)

    def test_both_architectures_download_and_reuse_verified_cache(self):
        for arch in ('x86_64', 'aarch64'):
            with self.subTest(arch=arch):
                self.fixture(arch)
                self.env['IWAN_CONFIG_DIR'] = str(self.work / arch)
                self.env['IWAN_SHA256_AMD64'] = SHA if arch == 'x86_64' else '0' * 64
                self.env['IWAN_SHA256_ARM64'] = SHA if arch == 'aarch64' else '0' * 64
                result = self.invoke()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, 'fixture client\n')
                self.assertIn('Verified SHA-256', result.stderr)
                requests = (self.work / 'requests').read_text()
                result = self.invoke()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((self.work / 'requests').read_text(), requests)

    def test_checksum_mismatch_never_installs(self):
        self.fixture()
        self.env['IWAN_SHA256_AMD64'] = '0' * 64
        result = self.invoke()
        self.assertEqual(result.returncode, 3)
        self.assertIn('SHA-256 mismatch', result.stderr)
        self.assertFalse((self.work / 'config/bin/iwan-client-oidc-v26.9.1').exists())

    def test_wrong_archive_member_is_rejected(self):
        self.fixture(member='iwan-client-oidc-x86_64-musl')
        result = self.invoke()
        self.assertEqual(result.returncode, 3)
        self.assertIn('did not contain expected binary', result.stderr)

    def test_missing_checksum_is_rejected_before_download(self):
        self.fixture()
        self.env['IWAN_SHA256_AMD64'] = ''
        result = self.invoke()
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.work / 'requests').exists())

    def test_workflows_use_new_asset_names_for_both_architectures(self):
        for path in (ROOT / '.github/workflows').glob('*.yml'):
            text = path.read_text()
            for arch in ('x86_64', 'aarch64'):
                self.assertIn(f'iwan-client-oidc-linux-{arch}-musl.zip', text)
                self.assertNotIn(f'iwan-client-oidc-{arch}-musl', text)


if __name__ == '__main__':
    unittest.main()
