FROM node:22-alpine AS frontend
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html tsconfig.json vite.config.ts ./
COPY src ./src
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    SIGNALDESK_ENVIRONMENT=production \
    SIGNALDESK_SERVE_FRONTEND=true \
    SIGNALDESK_REQUIRE_BASIC_AUTH=true \
    SIGNALDESK_BOOTSTRAP_UNIVERSE=true \
    SIGNALDESK_AUTO_WARMUP=true \
    SIGNALDESK_API_HOST=0.0.0.0 \
    SIGNALDESK_STATE_DIR=/data
WORKDIR /app
COPY requirements.lock pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.lock
COPY backend ./backend
COPY --from=frontend /app/dist ./dist
RUN useradd --create-home --uid 10001 signaldesk \
    && mkdir -p /data \
    && chown signaldesk:signaldesk /data
USER signaldesk
EXPOSE 8000
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + __import__('os').environ.get('PORT', '8000') + '/api/health', timeout=4)"
CMD ["python", "backend/run.py"]
