# syntax=docker/dockerfile:1.7
# src/rag_service/Dockerfile
# ---------- Stage 1: Builder ----------
FROM python:3.11-slim AS builder

# تنظیمات پایتون و pip — فقط mirror Tsinghua
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

WORKDIR /app

# وابستگی‌های سیستمی برای build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    python3-dev \
    libpq-dev \
    libmagic1 \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# ۱. فقط requirements.txt را کپی کن
COPY requirements.txt .

# ۲. نصب نیازمندی‌ها فقط از mirror Tsinghua (بدون fallback به PyPI)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install -r requirements.txt

# ---------- Stage 2: Runtime ----------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# وابستگی‌های سیستمی runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libmagic1 \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

# کپی بسته‌های نصب‌شده از builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# کپی کد
COPY . .

# پوشه‌های temp و data
RUN mkdir -p /app/temp_uploads /app/data

# Non-root user.
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8102

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8102/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8102", "--workers", "2", "--proxy-headers"]