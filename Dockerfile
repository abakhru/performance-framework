FROM grafana/k6:1.6.1 AS k6base

FROM python:3.12-slim

COPY --from=k6base /usr/bin/k6 /usr/bin/k6

# Install deps first — this layer is cached until pyproject.toml/uv.lock changes
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --no-dev --frozen

WORKDIR /tests

# Copy source last — invalidates only when code changes
COPY k6/ ./k6/
COPY dashboard/ ./dashboard/

EXPOSE 5656 6565

# Default: plain smoke run. Override CMD for dashboard mode.
# Usage:
#   docker run matrix-k6                → plain smoke
#   docker run matrix-k6 smoke          → dashboard smoke at :5656
#   docker run matrix-k6 ramp           → dashboard ramp  at :5656
ENTRYPOINT ["/bin/sh", "-c", "\
  if [ \"$1\" = 'smoke' ] || [ \"$1\" = 'ramp' ]; then \
    python3 dashboard/server.py \"$1\"; \
  else \
    k6 run k6/main.js; \
  fi", "--"]
CMD []
