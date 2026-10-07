# syntax=docker/dockerfile:1.7
# One image for the API/MCP server and the worker. Build from the repository root:
#   docker compose build

# ---------------------------------------------------------------- web app
FROM node:22-alpine AS web
WORKDIR /src
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/
RUN npm ci --workspace apps/web --no-audit --no-fund
COPY apps/web apps/web
RUN npm run build --workspace apps/web

# ---------------------------------------------------------------- server
FROM python:3.13-slim AS app
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONUNBUFFERED=1
# git lets the Brain commit its governed changes when its repository is mounted.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && git config --system --add safe.directory '*'
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY packages packages
COPY apps/server apps/server
RUN uv sync --frozen --no-dev --package workspace-server --extra postgres
COPY config config
COPY --from=web /src/apps/web/dist /app/web

ENV PATH="/app/.venv/bin:$PATH" \
    CONTXT_DATA_DIR=/data \
    CONTXT_HOST=0.0.0.0 \
    CONTXT_PORT=8787 \
    CONTXT_WEB_DIST=/app/web \
    CONTXT_TEMPLATES_DIR=/app/config/templates
# The default user. Compose runs the containers as CONTXT_UID:CONTXT_GID instead, after
# data-init (root, on the data volume alone) hands /data to that user; see docs/operations.md.
RUN useradd --create-home --uid 10001 contxt \
    && mkdir -p /data && chown contxt:contxt /data
COPY --chmod=755 docker/data-init.sh /usr/local/bin/data-init
USER contxt
VOLUME ["/data"]
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/api/health', timeout=4)" || exit 1
CMD ["contxt", "--env-file", "", "serve", "--no-worker"]
