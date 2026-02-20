# ---------- builder ----------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.8.3

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl build-essential \
  && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

WORKDIR /app
COPY backend/pyproject.toml backend/poetry.lock ./

# Ставим зависимости в /usr/local (т.к. virtualenvs.create false)
RUN poetry config virtualenvs.create false \
  && poetry install --no-interaction --no-ansi --only main,ingest

# ---------- runtime ----------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Переносим только то, что установил builder
COPY --from=builder /usr/local /usr/local

COPY backend/ingestion_service ./backend/ingestion_service
WORKDIR /app/backend/ingestion_service

EXPOSE 19100
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "19100"]
