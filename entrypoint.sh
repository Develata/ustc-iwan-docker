#!/bin/sh
set -eu

CONFIG_DIR="${IWAN_CONFIG_DIR:-/config}"
BIN_DIR="${CONFIG_DIR}/bin"
BIN="${BIN_DIR}/iwan-client-oidc-${IWAN_VERSION}"
SOCKS_LISTEN="${IWAN_SOCKS_LISTEN:-0.0.0.0:1080}"
SOCKS_MTU="${IWAN_SOCKS_MTU:-1380}"
SERVER_INDEX="${IWAN_SERVER_INDEX:-1}"
HEALTHCHECK_URL="${IWAN_HEALTHCHECK_URL:-https://api.llm.ustc.edu.cn/}"
HEALTHCHECK_TIMEOUT="${IWAN_HEALTHCHECK_TIMEOUT:-10}"
WATCHDOG_INTERVAL="${IWAN_WATCHDOG_INTERVAL:-30}"
WATCHDOG_FAILURES="${IWAN_WATCHDOG_FAILURES:-4}"
STARTUP_GRACE="${IWAN_STARTUP_GRACE:-20}"

mkdir -p "$BIN_DIR"

asset_name() {
    case "$(uname -m)" in
        x86_64)  echo "iwan-client-oidc-x86_64-musl" ;;
        aarch64) echo "iwan-client-oidc-aarch64-musl" ;;
        *)
            echo "unsupported architecture: $(uname -m)" >&2
            exit 2
            ;;
    esac
}

download_iwan() {
    [ -n "${IWAN_VERSION:-}" ] || {
        echo "IWAN_VERSION is empty; image was built incorrectly" >&2
        exit 2
    }

    if [ -x "$BIN" ]; then
        return 0
    fi

    asset="$(asset_name)"
    url="https://github.com/yyy1mu/ustc-iwan/releases/download/${IWAN_VERSION}/${asset}"
    tmp="${BIN}.tmp"

    echo "Downloading upstream ${asset} (${IWAN_VERSION})..." >&2
    rm -f "$tmp"
    curl -fL --retry 3 --retry-delay 2 "$url" -o "$tmp"

    expected="$(awk -v a="$asset" '$2 == a {print $1; exit}' /usr/local/share/ustc-iwan/UPSTREAM_SHA256S 2>/dev/null || true)"
    if [ -n "$expected" ]; then
        actual="$(sha256sum "$tmp" | awk '{print $1}')"
        if [ "$actual" != "$expected" ]; then
            echo "SHA-256 mismatch for ${asset}: expected ${expected}, got ${actual}" >&2
            rm -f "$tmp"
            exit 3
        fi
        echo "Verified SHA-256: ${actual}" >&2
    else
        echo "WARNING: no pinned SHA-256 is available for ${asset}; download is not checksum-pinned." >&2
    fi

    chmod 0755 "$tmp"
    mv "$tmp" "$BIN"
}

run_fetch() {
    download_iwan
    exec "$BIN" --config-dir "$CONFIG_DIR" --fetch
}

run_list() {
    download_iwan
    exec "$BIN" --config-dir "$CONFIG_DIR" --list
}

child_pid=""
cleanup() {
    if [ -n "$child_pid" ] && kill -0 "$child_pid" 2>/dev/null; then
        kill -TERM "$child_pid" 2>/dev/null || true
        wait "$child_pid" 2>/dev/null || true
    fi
}
trap cleanup INT TERM HUP EXIT

run_proxy() {
    download_iwan

    if [ ! -s "${CONFIG_DIR}/servers.json" ]; then
        echo "${CONFIG_DIR}/servers.json not found. Run: docker compose run --rm iwan fetch" >&2
        exit 4
    fi

    case "$SERVER_INDEX" in
        ''|*[!0-9]*|0)
            echo "IWAN_SERVER_INDEX must be a positive integer" >&2
            exit 2
            ;;
    esac

    echo "Starting USTC iWAN SOCKS5 on ${SOCKS_LISTEN}, upstream ${IWAN_VERSION}, server index ${SERVER_INDEX}" >&2

    "$BIN" \
        --config-dir "$CONFIG_DIR" \
        --connect \
        --socks \
        --socks-listen "$SOCKS_LISTEN" \
        --socks-mtu "$SOCKS_MTU" <<EOF &
${SERVER_INDEX}
EOF
    child_pid=$!

    sleep "$STARTUP_GRACE"

    failures=0
    while kill -0 "$child_pid" 2>/dev/null; do
        if curl -sS \
            --max-time "$HEALTHCHECK_TIMEOUT" \
            --socks5-hostname 127.0.0.1:1080 \
            "$HEALTHCHECK_URL" \
            -o /dev/null; then
            failures=0
        else
            failures=$((failures + 1))
            echo "watchdog: data-plane check failed (${failures}/${WATCHDOG_FAILURES})" >&2
            if [ "$failures" -ge "$WATCHDOG_FAILURES" ]; then
                echo "watchdog: failure threshold reached; terminating iWAN client so Docker can restart it" >&2
                kill -TERM "$child_pid" 2>/dev/null || true
                wait "$child_pid" 2>/dev/null || true
                child_pid=""
                exit 10
            fi
        fi
        sleep "$WATCHDOG_INTERVAL"
    done

    set +e
    wait "$child_pid"
    status=$?
    set -e
    child_pid=""
    echo "iWAN client exited with status ${status}" >&2
    exit "$status"
}

case "${1:-run}" in
    run)
        run_proxy
        ;;
    fetch)
        run_fetch
        ;;
    list)
        run_list
        ;;
    shell)
        download_iwan
        exec /bin/sh
        ;;
    *)
        download_iwan
        exec "$BIN" "$@"
        ;;
esac
