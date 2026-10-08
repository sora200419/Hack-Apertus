FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY src/api/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY src/api /app
COPY src/eval /app/eval
# Data is baked in so the image runs on its own; compose also bind-mounts ./data
# so record mode can append to the replay cache.
COPY data /data
ENV DATA_DIR=/data

EXPOSE 8000
CMD ["uvicorn", "originpass.main:app", "--host", "0.0.0.0", "--port", "8000"]
