"""Offline Docker CLI fixtures for the multi-arch image smoke test."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ImageSmokeTests(unittest.TestCase):
    def run_smoke(self, manifests):
        with tempfile.TemporaryDirectory() as work:
            tool = Path(work) / 'docker'
            tool.write_text('''#!/bin/sh
set -eu
case "$1" in
    buildx) printf '%s' "$FIXTURE_INDEX" ;;
    pull)
        case "$3:$4" in
            linux/amd64:example.invalid/iwan@sha256:amd64) ;;
            linux/arm64:example.invalid/iwan@sha256:arm64) ;;
            *) exit 99 ;;
        esac ;;
    run)
        case "$4:$5" in
            linux/amd64:example.invalid/iwan@sha256:amd64) ;;
            linux/arm64:example.invalid/iwan@sha256:arm64) ;;
            *) exit 99 ;;
        esac
        case "$6" in
            --version) printf 'iwan-client-oidc 26.9.1\n' ;;
            --help) printf '%s\n' '--config-dir --fetch --list --connect --socks --socks-listen --socks-mtu' ;;
            *) exit 98 ;;
        esac ;;
    *) exit 97 ;;
esac
''')
            tool.chmod(0o755)
            env = dict(os.environ, PATH=f'{work}:{os.environ["PATH"]}',
                       FIXTURE_INDEX=json.dumps({'manifests': manifests}))
            return subprocess.run(['sh', str(ROOT / 'scripts/smoke-image.sh'),
                                   'example.invalid/iwan@sha256:index', 'v26.9.1'],
                                  env=env, text=True, capture_output=True, timeout=10)

    def test_each_architecture_uses_its_own_child_digest(self):
        manifests = [dict(platform=dict(os='linux', architecture=arch), digest=f'sha256:{arch}')
                     for arch in ('amd64', 'arm64')]
        manifests.append(dict(platform=dict(os='unknown', architecture='unknown'), digest='sha256:attestation'))
        result = self.run_smoke(manifests)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count('PASS linux/'), 2)

    def test_missing_architecture_fails(self):
        result = self.run_smoke([])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('expected one platform manifest', result.stderr)

    def test_ambiguous_architecture_fails(self):
        manifest = dict(platform=dict(os='linux', architecture='amd64'), digest='sha256:amd64')
        result = self.run_smoke([manifest, manifest])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('expected one platform manifest', result.stderr)
