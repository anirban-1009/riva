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
    PATH="/app/.venv/bin:$PATH"

COPY . .

RUN uv sync --frozen --no-dev

EXPOSE 8000

CMD ["uvicorn", "riva_agent.api.gateway:app", "--host", "0.0.0.0", "--port", "8000"]
