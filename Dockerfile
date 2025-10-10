# # FROM python:3.10-slim
# # WORKDIR /app
# # COPY requirements.txt ./
# # RUN pip install --no-cache-dir -r requirements.txt
# # COPY . .
# # VOLUME ["/app/pretrained_models", "/app/truevoice.db"]
# # CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


# FROM ubuntu:22.04

# # --- System deps ---
# RUN apt-get update && apt-get install -y \
#     python3 python3-pip ffmpeg libsndfile1 git \
#     && rm -rf /var/lib/apt/lists/*

# WORKDIR /app

# # --- Install torch separately (heavy, cacheable) ---
# RUN pip3 install --no-cache-dir --default-timeout=1000 --retries=20 \
#     torch==2.8.0 -f https://download.pytorch.org/whl/torch_stable.html

# # --- Copy requirements (lighter deps) ---
# COPY requirements.txt .

# # --- Install remaining dependencies ---
# RUN pip3 install --no-cache-dir --default-timeout=100 --retries=10 -r requirements.txt

# # --- Copy app code ---
# COPY app ./app

# # --- Expose App Runner port ---
# EXPOSE 8080

# # --- Start FastAPI ---
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]


# # ====== 1. Use a base Python image ======
# FROM python:3.10-slim

# # ====== 2. Set work directory inside the container ======
# WORKDIR /app

# # ====== 3. Copy your app code into the container ======
# COPY . /app

# # ====== 4. Copy your local virtual environment ======
# # We copy it into /opt/venv inside the container
# COPY venvTruevoice /opt/venv

# # ====== 5. Set environment to use the copied venv ======
# ENV VIRTUAL_ENV=/opt/venv
# ENV PATH="$VIRTUAL_ENV/Scripts:$VIRTUAL_ENV/bin:$PATH"

# # ====== 6. Upgrade pip inside the container ======
# RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel

# # ====== 7. Validate dependencies (optional but useful) ======
# RUN python -m pip list

# # ====== 8. Copy environment variables file (if you use it) ======
# # Note: make sure `.env` file exists
# COPY .env .env

# # ====== 9. Expose the FastAPI port ======
# EXPOSE 8000

# # ====== 10. Start the FastAPI app ======
# # CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
# CMD ["/opt/venv/Scripts/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]


# ====== 1. Use a base Python image ======
FROM python:3.10-slim

# ====== 2. Set working directory inside the container ======
WORKDIR /app

# ====== 3. Copy all project files into the container ======
COPY . /app

# ====== 4. Install system and Python dependencies ======
RUN apt-get update && apt-get install -y build-essential ffmpeg \
    && pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# ====== 5. Copy environment variables file (optional) ======
COPY .env .env

# ====== 6. Expose the FastAPI port ======
EXPOSE 8000

# ====== 7. Run Alembic migrations, then start FastAPI ======
# This assumes `alembic.ini` is in the root folder
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
