FROM grafana/k6:1.6.1 AS k6base

FROM python:3.12-slim

COPY --from=k6base /usr/bin/k6 /usr/bin/k6

# Install uv + deps in a cached layer (only busts when lockfile changes)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen

WORKDIR /app

# Source code — copy after deps so this layer is cheap to rebuild
COPY k6/       ./k6/
COPY dashboard/ ./dashboard/
COPY api_tests/ ./api_tests/
COPY luna_cli/  ./luna_cli/

# luna CLI is available inside the container
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 5656 6565

# Healthcheck — hits the /health endpoint every 30s
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:5656/health')" || exit 1

# Usage:
#   docker run luna                          → standalone dashboard at :5656
#   docker run luna smoke                    → immediate smoke run
#   LUNA_API_KEY=secret docker run luna      → dashboard with auth
CMD ["python3", "dashboard/server.py"]
ENTRYPOINT []
