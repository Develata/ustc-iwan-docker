#!/bin/sh
# Read back the exact published digest, exercising cold-start downloads on
# both supported architectures. No campus credentials or tunnel are needed.
set -eu
image="${1:?usage: smoke-image.sh IMAGE@DIGEST UPSTREAM_VERSION}"
version="${2:?upstream version is required}"

index="$(docker buildx imagetools inspect "$image" --raw)"
for platform in linux/amd64 linux/arm64; do
    # Classic Docker image stores cannot associate one index digest with two
    # local architectures. Pull each exact child manifest instead.
    digest="$(printf '%s' "$index" | jq -er --arg arch "${platform#linux/}" '
        [.manifests[] | select(.platform.os == "linux" and .platform.architecture == $arch) | .digest]
        | if length == 1 then .[0] else error("expected one platform manifest") end
    ')"
    platform_image="${image%@*}@${digest}"
    docker pull --platform "$platform" "$platform_image"
    actual="$(docker run --rm --platform "$platform" "$platform_image" --version)"
    # Upstream releases may print the tag with or without its leading v.
    # Match the whole line and exact version; do not accept prefixes/suffixes.
    case "$actual" in
        "iwan-client-oidc ${version#v}"|"iwan-client-oidc v${version#v}") ;;
        *)
            printf 'Unexpected %s client version: %s\n' "$platform" "$actual" >&2
            exit 1
            ;;
    esac
    help="$(docker run --rm --platform "$platform" "$platform_image" --help)"
    for flag in --config-dir --fetch --list --connect --socks --socks-listen --socks-mtu; do
        case "$help" in
            *"$flag"*) ;;
            *) printf 'Missing upstream option: %s\n' "$flag" >&2; exit 1 ;;
        esac
    done
    printf 'PASS %s: verified cold-start download, version and wrapper CLI options\n' "$platform"
done
