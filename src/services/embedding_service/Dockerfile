FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models/huggingface \
    TRANSFORMERS_CACHE=/models/huggingface

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY src/services/embedding_service ./src/services/embedding_service
WORKDIR /app/src/services/embedding_service

RUN python -m pip install --upgrade pip \
  && python -m pip install --no-cache-dir .

EXPOSE 19400
CMD ["embedding-service"]
