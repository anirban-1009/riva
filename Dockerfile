FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ARG VERSION=0.0.0-dev
LABEL org.opencontainers.image.title="riva-agent"
LABEL org.opencontainers.image.description="Private, persistent personal AI assistant that coordinates localized genies on-device."
LABEL org.opencontainers.image.version=$VERSION
LABEL org.opencontainers.image.source="https://github.com/anirban-1009/riva"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=300 \
    PATH="/app/.venv/bin:$PATH"

# Pre-cache third-party dependencies before copying full application source
COPY pyproject.toml uv.lock ./
COPY common/pyproject.toml common/
COPY job-genie/pyproject.toml job-genie/
COPY money-genie/pyproject.toml money-genie/
COPY workout-genie/pyproject.toml workout-genie/
COPY lighthouse-genie/pyproject.toml lighthouse-genie/
COPY experiments/pyproject.toml experiments/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace

# Copy full application source code
COPY . .

# Fast sync to install only local workspace members
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

EXPOSE 8000

CMD ["uvicorn", "riva_agent.api.gateway:app", "--host", "0.0.0.0", "--port", "8000"]
