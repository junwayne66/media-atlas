FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ARG WORKER_PACKAGE
WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# ffprobe 用于采集媒体可读性/Golden 指标；只以参数数组调用（L3 独立工具）。
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/temporal-worker/pyproject.toml apps/temporal-worker/pyproject.toml
COPY packages/contracts-py/pyproject.toml packages/contracts-py/pyproject.toml
COPY packages/persistence/pyproject.toml packages/persistence/pyproject.toml
COPY packages/media-core/pyproject.toml packages/media-core/pyproject.toml
COPY packages/workflows/pyproject.toml packages/workflows/pyproject.toml
COPY packages/provider-sdk/pyproject.toml packages/provider-sdk/pyproject.toml
COPY packages/domain/pyproject.toml packages/domain/pyproject.toml
COPY services/edge-agent/pyproject.toml services/edge-agent/pyproject.toml
COPY connectors/sources/douyin/pyproject.toml connectors/sources/douyin/pyproject.toml
COPY connectors/sources/tiktok/pyproject.toml connectors/sources/tiktok/pyproject.toml
COPY connectors/downloaders/yt-dlp/pyproject.toml connectors/downloaders/yt-dlp/pyproject.toml
COPY connectors/downloaders/f2/pyproject.toml connectors/downloaders/f2/pyproject.toml
RUN uv sync --frozen --no-dev --no-install-workspace --package "${WORKER_PACKAGE}"

COPY packages packages
COPY connectors connectors
COPY apps/temporal-worker apps/temporal-worker
COPY services/edge-agent services/edge-agent
RUN uv sync --frozen --no-dev --package "${WORKER_PACKAGE}"
