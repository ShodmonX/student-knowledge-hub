FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV APP_WORKERS=2
ENV RUN_MIGRATIONS_ON_START=true
ENV RUN_SEED_ON_START=true

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
RUN pip install --upgrade pip && pip install -e .[dev]

RUN useradd --create-home --shell /bin/bash appuser

COPY . .

RUN mkdir -p /app/storage /home/appuser/storage /home/appuser/backups \
    && chmod +x /app/docker/entrypoint.sh \
    && chown -R appuser:appuser /app /home/appuser/storage /home/appuser/backups

USER appuser

ENTRYPOINT ["sh", "/app/docker/entrypoint.sh"]
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${APP_WORKERS}"]
