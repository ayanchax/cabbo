# Dockerfile for production
FROM python:3.10-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install uv && uv pip install -r pyproject.toml

COPY . .

ENV ENV=prod

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
