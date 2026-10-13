# syntax=docker/dockerfile:1.7
# Stage 1 — build the control panel
FROM node:22-bookworm-slim AS web
WORKDIR /src/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
RUN npx tsc -p tsconfig.json --noEmit && npx vite build --outDir /out/static

# Stage 2 — API runtime (serves the built panel on the same origin)
FROM python:3.12-slim-bookworm AS api
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
CMD ["sh", "-c", "python -m nis.cli migrate && uvicorn nis.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
