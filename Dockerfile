# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.12.23 AS uv
FROM python:3.14-slim-bookworm AS runtime
COPY --from=uv /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" STATIC_DIR=/app/frontend/dist DATABASE_URL=sqlite:////data/searchbar.db
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY backend/ ./backend/
RUN uv sync --locked --no-dev --no-editable && \
    groupadd --gid 10001 searchbar && useradd --uid 10001 --gid searchbar --no-create-home searchbar && \
    mkdir -p /data && chown searchbar:searchbar /data
COPY --from=frontend /build/frontend/dist ./frontend/dist
COPY --chmod=755 scripts/entrypoint.sh /app/entrypoint.sh
LABEL org.opencontainers.image.source="https://github.com/david-loe/paperless-searchbar" \
      org.opencontainers.image.title="Paperless Searchbar" \
      org.opencontainers.image.licenses="AGPL-3.0-only"
# Source checkouts may have a restrictive umask; the runtime user must read the app.
RUN chmod -R a+rX /app
USER 10001:10001
EXPOSE 8000
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]
ENTRYPOINT ["/app/entrypoint.sh"]
