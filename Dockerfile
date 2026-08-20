FROM alpine:3.22

ARG IWAN_VERSION
ENV IWAN_VERSION=${IWAN_VERSION}

RUN apk add --no-cache ca-certificates curl tini

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY UPSTREAM_SHA256S /usr/local/share/ustc-iwan/UPSTREAM_SHA256S

RUN chmod +x /usr/local/bin/entrypoint.sh \
    && mkdir -p /config/bin

VOLUME ["/config"]
EXPOSE 1080

HEALTHCHECK --interval=60s --timeout=12s --start-period=30s --retries=2 \
  CMD curl -sS --max-time 8 --socks5-hostname 127.0.0.1:1080 "${IWAN_HEALTHCHECK_URL:-https://api.llm.ustc.edu.cn/}" -o /dev/null || exit 1

ENTRYPOINT ["/sbin/tini", "--", "/usr/local/bin/entrypoint.sh"]
CMD ["run"]
