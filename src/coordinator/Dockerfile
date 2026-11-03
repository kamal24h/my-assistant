# src/coordinator/Dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

WORKDIR /app

# Install dependencies first (maximizes Docker layer cache reuse).
COPY requirements.txt .
RUN pip install \
        --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
        --trusted-host pypi.tuna.tsinghua.edu.cn \
        -r requirements.txt

# Copy the application package.
COPY app /app/app
COPY main.py /app/main.py

# Non-root user for the container.
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8101

# Single worker: OpenAI rate-limit is per-process (in-memory semaphore + deque).
# Multiple workers would multiply the allowed OpenAI concurrency/rate.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8101", "--proxy-headers"]