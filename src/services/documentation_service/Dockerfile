FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY src/services/documentation_service ./src/services/documentation_service
WORKDIR /app/src/services/documentation_service

RUN python -m pip install --upgrade pip \
  && python -m pip install --no-cache-dir -e .[dev]

EXPOSE 19500

CMD ["documentation-api"]
