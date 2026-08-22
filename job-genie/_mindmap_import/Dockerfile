# Use Microsoft's official Playwright image for robust browser dependency support
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_PROJECT_ENVIRONMENT=/venv

# Install system dependencies
# - texlive-latex-extra includes moderncv and other resume packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uv/bin/uv
ENV PATH="/uv/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml .
COPY uv.lock .

# Install dependencies using uv
# --no-dev: exclude development dependencies
# --no-install-project: install only dependencies first to cache them
RUN uv sync --frozen --no-dev --no-install-project

# Copy the rest of the application
COPY . .

# Install the project itself
RUN uv sync --frozen --no-dev

# Ensure necessary directories exist
RUN mkdir -p data/job_cache output/resumes

# Set the path to use the virtualenv created by uv
ENV PATH="/venv/bin:$PATH"

# Default command
ENTRYPOINT ["mindmap"]
CMD ["--help"]
