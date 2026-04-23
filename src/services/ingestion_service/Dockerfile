FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl build-essential \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY src/services/ingestion_service ./src/services/ingestion_service
WORKDIR /app/src/services/ingestion_service

RUN python -m pip install --upgrade pip \
  && python -m pip install --no-cache-dir .

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /usr/local /usr/local
COPY src/services/ingestion_service ./src/services/ingestion_service

WORKDIR /app/src/services/ingestion_service

EXPOSE 19100
CMD ["ingestion-api"]
