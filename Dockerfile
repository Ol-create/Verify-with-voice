# FROM python:3.10-slim
# WORKDIR /app
# COPY requirements.txt ./
# RUN pip install --no-cache-dir -r requirements.txt
# COPY . .
# VOLUME ["/app/pretrained_models", "/app/truevoice.db"]
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


# FROM ubuntu:22.04

# RUN apt-get update && apt-get install -y \
#     python3 python3-pip ffmpeg libsndfile1 git \
#     && rm -rf /var/lib/apt/lists/*

# WORKDIR /app
# COPY . .
# RUN pip3 install -r requirements.txt

# # Start FastAPI with Uvicorn
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

FROM ubuntu:22.04

# --- System deps ---
RUN apt-get update && apt-get install -y \
    python3 python3-pip ffmpeg libsndfile1 git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Install torch separately (heavy, cacheable) ---
RUN pip3 install --no-cache-dir --default-timeout=1000 --retries=20 \
    torch==2.8.0 -f https://download.pytorch.org/whl/torch_stable.html

# --- Copy requirements (lighter deps) ---
COPY requirements.txt .

# --- Install remaining dependencies ---
RUN pip3 install --no-cache-dir --default-timeout=100 --retries=10 -r requirements.txt

# --- Copy app code ---
COPY app ./app

# --- Expose App Runner port ---
EXPOSE 8080

# --- Start FastAPI ---
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
