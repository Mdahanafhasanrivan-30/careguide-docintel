FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System tools needed in later phases (OCR and file-type detection)
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr libmagic1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /code

# Copy requirements first so Docker caches this slow layer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a normal user, not root
RUN useradd --create-home appuser
USER appuser
