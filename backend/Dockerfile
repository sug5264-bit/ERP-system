# Multi-stage build keeps the final image small and rootless.
FROM python:3.11-slim AS builder

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt \
    && pip install --no-cache-dir --prefix=/install gunicorn


FROM python:3.11-slim AS runtime

# Korean font for PDF export + curl for the healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
      fonts-nanum curl \
    && rm -rf /var/lib/apt/lists/*

# Run as a non-root user.
RUN groupadd -r erp && useradd -r -g erp -d /app -s /sbin/nologin erp

WORKDIR /app
COPY --from=builder /install /usr/local
COPY --chown=erp:erp . .

USER erp

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/api/health/ready || exit 1

# Tunable via env. Default 2 workers × 4 threads keeps a small VM happy.
ENV GUNICORN_WORKERS=2 \
    GUNICORN_THREADS=4 \
    GUNICORN_TIMEOUT=60

CMD ["sh", "-c", "gunicorn -k uvicorn.workers.UvicornWorker \
     --workers ${GUNICORN_WORKERS} \
     --threads ${GUNICORN_THREADS} \
     --timeout ${GUNICORN_TIMEOUT} \
     --access-logfile - --error-logfile - \
     --bind 0.0.0.0:8000 app.main:app"]
