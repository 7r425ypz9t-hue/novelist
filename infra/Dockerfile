# Base images are build args so a registry mirror can be used when Docker Hub rate-limits, e.g.
#   --build-arg NODE_IMAGE=mirror.gcr.io/library/node:22-bookworm-slim \
#   --build-arg PYTHON_IMAGE=mirror.gcr.io/library/python:3.12-slim-bookworm
ARG NODE_IMAGE=node:22-bookworm-slim
ARG PYTHON_IMAGE=python:3.12-slim-bookworm

# Stage 1 — build the control panel
FROM ${NODE_IMAGE} AS web
WORKDIR /src/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
RUN npx tsc -p tsconfig.json --noEmit && npx vite build --outDir /out/static

# Stage 2 — API runtime (serves the built panel on the same origin)
FROM ${PYTHON_IMAGE} AS api
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 NIS_DATA_DIR=/data NIS_SERVE_SPA=true
RUN apt-get update && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
    && rm -rf /var/lib/apt/lists/* && useradd --create-home --uid 10001 nis
WORKDIR /app
COPY apps/api/pyproject.toml ./
COPY apps/api/nis ./nis
COPY apps/api/migrations ./migrations
COPY apps/api/alembic.ini ./
COPY --from=web /out/static ./nis/static
RUN pip install --no-cache-dir ".[postgres,pdf]" && mkdir -p /data && chown -R nis /data
USER nis
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/v1/health').status==200 else 1)"
# `nis serve` = migrate → readiness check (`nis doctor`) → uvicorn; a blocker (e.g. wrong NIS_MASTER_KEY) stops the start.
CMD ["python", "-m", "nis.cli", "serve", "--host", "0.0.0.0", "--port", "8000"]
