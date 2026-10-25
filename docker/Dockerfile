# syntax=docker/dockerfile:1.7
# One image for the app: the API, the MCP endpoint, the web app and their background work.
# Build from the repository root:
#   docker compose build

# ---------------------------------------------------------------- web app
FROM node:22-alpine AS web
WORKDIR /src
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/
RUN npm ci --workspace apps/web --no-audit --no-fund
COPY apps/web apps/web
RUN npm run build --workspace apps/web

# ---------------------------------------------------------------- Node.js for the server
# Gnomon's own n8n installs and runs with Node.js 20.19 to 24 and npm, and Claude Code (the CLI
# the heartbeat, the knowledge agent and "Run now" use) comes from npm.
FROM node:22-slim AS node

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
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
# Claude Code; pin it with --build-arg CLAUDE_CODE_VERSION=<version>. Its login lives in HOME
# (in the data volume, below): run `claude auth login` in the container once.
ARG CLAUDE_CODE_VERSION=latest
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && npm install -g --no-audit --no-fund "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
    && npm cache clean --force \
    && claude --version
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY packages packages
COPY apps/server apps/server
RUN uv sync --frozen --no-dev --package workspace-server --extra postgres
COPY config config
# The starter Brains, so `contxt setup` can make a Brain from inside the image.
COPY brains brains
COPY --from=web /src/apps/web/dist /app/web

# HOME is in the data volume: the CLI's login, npm's cache (n8n installs with it) and whatever
# else a CLI keeps there survive a new container, and belong to the user Compose runs it as.
# An update comes with a new image, so Claude Code's own updater stays off.
ENV PATH="/app/.venv/bin:$PATH" \
    HOME=/data/home \
    DISABLE_AUTOUPDATER=1 \
    CONTXT_DATA_DIR=/data \
    CONTXT_HOST=0.0.0.0 \
    CONTXT_PORT=8787 \
    CONTXT_WEB_DIST=/app/web \
    CONTXT_TEMPLATES_DIR=/app/config/templates
# The default user. Compose runs the container as CONTXT_UID:CONTXT_GID instead, after
# data-init (root, on the data volume alone) hands /data to that user; see docs/operations.md.
RUN useradd --create-home --uid 10001 contxt \
    && mkdir -p /data/home && chmod 700 /data/home && chown -R contxt:contxt /data
COPY --chmod=755 docker/data-init.sh /usr/local/bin/data-init
USER contxt
VOLUME ["/data"]
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/api/health', timeout=4)" || exit 1
# The app with its background work: the worker's clock, the heartbeat, Gnomon's own n8n.
CMD ["contxt", "--env-file", "", "serve", "--no-open"]
