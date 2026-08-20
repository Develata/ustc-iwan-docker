FROM alpine:3.22

ARG IWAN_VERSION
ARG IWAN_SHA256_AMD64
ARG IWAN_SHA256_ARM64

ENV IWAN_VERSION=${IWAN_VERSION} \
    IWAN_SHA256_AMD64=${IWAN_SHA256_AMD64} \
    IWAN_SHA256_ARM64=${IWAN_SHA256_ARM64}

RUN test -n "$IWAN_VERSION" \
    && test -n "$IWAN_SHA256_AMD64" \
    && test -n "$IWAN_SHA256_ARM64" \
    && apk add --no-cache ca-certificates curl tini unzip

COPY entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod +x /usr/local/bin/entrypoint.sh \
    && mkdir -p /config/bin

VOLUME ["/config"]
EXPOSE 1080

HEALTHCHECK --interval=60s --timeout=12s --start-period=30s --retries=2 \
  CMD curl -sS --max-time 8 --socks5-hostname 127.0.0.1:1080 "${IWAN_HEALTHCHECK_URL:-https://api.llm.ustc.edu.cn/}" -o /dev/null || exit 1

ENTRYPOINT ["/sbin/tini", "--", "/usr/local/bin/entrypoint.sh"]
CMD ["run"]
