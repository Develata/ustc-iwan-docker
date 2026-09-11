#!/bin/sh
# Read back the exact published digest, exercising cold-start downloads on
# both supported architectures. No campus credentials or tunnel are needed.
set -eu
image="${1:?usage: smoke-image.sh IMAGE@DIGEST UPSTREAM_VERSION}"
version="${2:?upstream version is required}"

for platform in linux/amd64 linux/arm64; do
    docker pull --platform "$platform" "$image"
    actual="$(docker run --rm --platform "$platform" "$image" --version)"
    [ "$actual" = "iwan-client-oidc ${version#v}" ] || {
        printf 'Unexpected %s client version: %s\n' "$platform" "$actual" >&2
        exit 1
    }
    help="$(docker run --rm --platform "$platform" "$image" --help)"
    for flag in --config-dir --fetch --list --connect --socks --socks-listen --socks-mtu; do
        case "$help" in
            *"$flag"*) ;;
            *) printf 'Missing upstream option: %s\n' "$flag" >&2; exit 1 ;;
        esac
    done
    printf 'PASS %s: verified cold-start download, version and wrapper CLI options\n' "$platform"
done
