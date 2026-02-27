FROM grafana/k6:latest AS k6base

FROM python:3.12-slim

# Copy k6 binary from official image
COPY --from=k6base /usr/bin/k6 /usr/bin/k6

WORKDIR /tests

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
