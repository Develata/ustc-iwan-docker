"""Offline Docker CLI fixtures for the multi-arch image smoke test."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
VERSION = '26.11.1'
PLATFORMS = ('amd64', 'arm64')


def platform_manifests():
    return [dict(platform=dict(os='linux', architecture=arch), digest=f'sha256:{arch}')
            for arch in PLATFORMS]


class ImageSmokeTests(unittest.TestCase):
    def run_smoke(self, manifests, versions=None, expected_version=f'v{VERSION}',
                  version_status=0, version_ending='\n'):
        versions = versions or {arch: f'iwan-client-oidc {VERSION}' for arch in PLATFORMS}
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
            linux/amd64:example.invalid/iwan@sha256:amd64)
                version="$FIXTURE_AMD64_VERSION" ;;
            linux/arm64:example.invalid/iwan@sha256:arm64)
                version="$FIXTURE_ARM64_VERSION" ;;
            *) exit 99 ;;
        esac
        case "$6" in
            --version)
                printf '%s%s' "$version" "$FIXTURE_VERSION_ENDING"
                exit "$FIXTURE_VERSION_STATUS" ;;
            --help) printf '%s\\n' '--config-dir --fetch --list --connect --server --socks --socks-listen --socks-mtu' ;;
            *) exit 98 ;;
        esac ;;
    *) exit 97 ;;
esac
''')
            tool.chmod(0o755)
            env = dict(os.environ, PATH=f'{work}:{os.environ["PATH"]}',
                       FIXTURE_INDEX=json.dumps({'manifests': manifests}),
                       FIXTURE_AMD64_VERSION=versions['amd64'],
                       FIXTURE_ARM64_VERSION=versions['arm64'],
                       FIXTURE_VERSION_STATUS=str(version_status),
                       FIXTURE_VERSION_ENDING=version_ending)
            return subprocess.run(['sh', str(ROOT / 'scripts/smoke-image.sh'),
                                   'example.invalid/iwan@sha256:index', expected_version],
                                  env=env, text=True, capture_output=True, timeout=10)

    def test_each_architecture_uses_its_own_child_digest(self):
        manifests = platform_manifests()
        manifests.append(dict(platform=dict(os='unknown', architecture='unknown'), digest='sha256:attestation'))
        result = self.run_smoke(manifests)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count('PASS linux/'), 2)

    def test_optional_v_in_expected_and_actual_versions(self):
        for expected in (VERSION, f'v{VERSION}'):
            for actual in (f'iwan-client-oidc {VERSION}', f'iwan-client-oidc v{VERSION}'):
                for ending in ('', '\n'):
                    with self.subTest(expected=expected, actual=actual, ending=ending):
                        result = self.run_smoke(
                            platform_manifests(),
                            versions={arch: actual for arch in PLATFORMS},
                            expected_version=expected, version_ending=ending)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stdout.count('PASS linux/'), 2)

    def test_extra_trailing_newlines_are_rejected_on_either_architecture(self):
        for arch in PLATFORMS:
            for prefix in ('', 'v'):
                for extra in ('\n', '\n\n', '\n\n\n'):
                    with self.subTest(arch=arch, prefix=prefix, extra=extra):
                        versions = {key: f'iwan-client-oidc {VERSION}' for key in PLATFORMS}
                        versions[arch] = f'iwan-client-oidc {prefix}{VERSION}{extra}'
                        result = self.run_smoke(platform_manifests(), versions=versions)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn(f'Unexpected linux/{arch} client version:', result.stderr)

    def test_architectures_can_use_different_v_formats(self):
        result = self.run_smoke(
            platform_manifests(),
            versions={'amd64': f'iwan-client-oidc v{VERSION}',
                      'arm64': f'iwan-client-oidc {VERSION}'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count('PASS linux/'), 2)

    def test_wrong_version_or_extra_output_is_rejected_on_either_architecture(self):
        for arch in PLATFORMS:
            for actual in (
                    'iwan-client-oidc 26.11.0',
                    'iwan-client-oidc v26.11.0',
                    'iwan-client-oidc 26.11.10',
                    'iwan-client-oidc v26.11.10',
                    f'iwan-client-oidc vv{VERSION}',
                    f'iwan-client-oidc V{VERSION}',
                    f'iwan-client-oidc {VERSION}-rc.1',
                    f'iwan-client-oidc {VERSION} extra',
                    f'iwan-client-oidc  {VERSION}',
                    f'iwan-client-oidc {VERSION} ',
                    f'iwan-client-oidc {VERSION}.',
                    f'other-client {VERSION}',
                    f'prefix iwan-client-oidc {VERSION}',
                    f'iwan-client-oidc {VERSION}\nextra',
                    ''):
                with self.subTest(arch=arch, actual=actual):
                    versions = {key: f'iwan-client-oidc {VERSION}' for key in PLATFORMS}
                    versions[arch] = actual
                    result = self.run_smoke(platform_manifests(), versions=versions)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(f'Unexpected linux/{arch} client version:', result.stderr)

    def test_version_command_failure_is_not_hidden(self):
        result = self.run_smoke(platform_manifests(), version_status=42)
        self.assertEqual(result.returncode, 42)
        self.assertNotIn('PASS linux/', result.stdout)

    def test_missing_architecture_fails(self):
        result = self.run_smoke([])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('expected one platform manifest', result.stderr)

    def test_ambiguous_architecture_fails(self):
        manifest = dict(platform=dict(os='linux', architecture='amd64'), digest='sha256:amd64')
        result = self.run_smoke([manifest, manifest])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('expected one platform manifest', result.stderr)
