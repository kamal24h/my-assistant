FROM python:3.11-slim

WORKDIR /app

# نصب پیش‌نیازها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . .

# تایم‌اوت 300 ثانیه در Gunicorn به دلیل زمان‌بر بودن پردازش LLM
CMD ["gunicorn", "main:app", "--workers", "2", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--timeout", "300"]