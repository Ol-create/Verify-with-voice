FROM python:3.13-slim

WORKDIR /app

# System dependencies (ffmpeg for audio conversion, libsndfile for soundfile)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        ffmpeg \
        libsndfile1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 && \
    rm -rf /var/lib/apt/lists/*

# Python dependencies (CPU-only torch keeps the image several GB smaller)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt \
        --extra-index-url https://download.pytorch.org/whl/cpu

COPY . /app

EXPOSE 8000

# Apply database migrations, then start the API.
# Set RUN_MIGRATIONS=0 when migrations run as a separate deploy step instead.
ENV RUN_MIGRATIONS=1
CMD ["sh", "-c", "if [ \"$RUN_MIGRATIONS\" = \"1\" ]; then alembic upgrade head; fi && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
