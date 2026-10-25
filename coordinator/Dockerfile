# coordinator/Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY coordinator/requirements-coordinator.txt /app/requirements-coordinator.txt
RUN pip install --no-cache-dir -r /app/requirements-coordinator.txt
COPY coordinator /app/coordinator
CMD ["uvicorn", "coordinator.main:app", "--host", "0.0.0.0", "--port", "8001"]
