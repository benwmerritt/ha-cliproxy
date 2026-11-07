ARG BUILD_FROM=ghcr.io/home-assistant/base:3.23
FROM ${BUILD_FROM}

RUN apk add --no-cache python3 py3-aiohttp

COPY rootfs /

WORKDIR /app
CMD ["python3", "-u", "/app/server.py"]

LABEL \
    org.opencontainers.image.title="Home Assistant add-on: CLIProxy" \
    org.opencontainers.image.source="https://github.com/benwmerritt/ha-cliproxy" \
    org.opencontainers.image.licenses="MIT"
