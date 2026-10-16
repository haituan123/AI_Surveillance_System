# syntax=docker/dockerfile:1.7

FROM python:3.12-slim-bookworm AS backend

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        curl \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
ARG TORCH_VERSION=2.14.1
ARG TORCHVISION_VERSION=0.29.1
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install \
        --index-url https://download.pytorch.org/whl/cpu \
        "torch==${TORCH_VERSION}" \
        "torchvision==${TORCHVISION_VERSION}" \
    && python -m pip install -r /app/backend/requirements.txt

COPY backend /app/backend

ENV BACKEND_HOST=0.0.0.0 \
    BACKEND_PORT=8000 \
    DATABASE_PATH=/app/backend/database/app.db \
    DATA_DIR=/app/backend/data \
    MODELS_DIR=/app/backend/models

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]


FROM ghcr.io/cirruslabs/flutter:stable AS frontend-build

WORKDIR /src/app_flutter

COPY app_flutter/pubspec.yaml app_flutter/pubspec.lock ./
RUN flutter pub get

COPY app_flutter ./

ARG BACKEND_URL=/api
RUN flutter build web --release --dart-define=BACKEND_URL=${BACKEND_URL}


FROM nginx:1.27-alpine AS frontend

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-build /src/app_flutter/build/web /usr/share/nginx/html

EXPOSE 80
