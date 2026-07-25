FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# 依赖层：uv workspace 的 frozen 解析需要**全部成员**的 pyproject 骨架在场
# （成员清单见根 pyproject.toml [tool.uv.workspace]；漏一个就是
# "Distribution not found at file:///app/..."）。先只装外部依赖，命中缓存。
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
RUN uv sync --frozen --no-dev --no-install-workspace --package videoforge-api

# 源码层：api 及其 workspace 依赖（packages + 下载连接器组合根）
COPY packages packages
COPY connectors connectors
COPY apps/api apps/api
RUN uv sync --frozen --no-dev --package videoforge-api

EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "videoforge_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
