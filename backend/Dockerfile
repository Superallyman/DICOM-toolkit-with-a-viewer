FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg poppler-utils libglib2.0-0 libsm6 libxext6 libxrender1 libgl1 \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    PERSISTENT_OUTPUT_DIR=/app/persistent_output \
    OHIF_VIEWER_DIR=/app/ohif \
    OHIF_RO_SRC=/opt/ohif-ro

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
 && pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY config ./config
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY dicomAnonymizer ./dicomAnonymizer
COPY config.properties ./config.properties

RUN mkdir -p /app/persistent_output /app/ohif

COPY *.py ./

COPY entrypoint.sh /app/entrypoint.sh
RUN sed -i 's/\r$//' /app/entrypoint.sh \
 && chmod +x /app/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
