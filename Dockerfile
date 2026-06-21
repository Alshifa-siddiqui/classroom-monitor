# Multi-stage build: build the React dashboard, then run the FastAPI backend
# which serves the built dashboard from frontend/dist (single process, port 8000).

# ---- Stage 1: build the frontend ----
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build          # -> /app/frontend/dist

# ---- Stage 2: backend runtime ----
FROM python:3.12-slim AS runtime

# OpenCV needs these shared libraries at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install backend deps first for better layer caching.
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Backend source.
COPY backend/ backend/

# Built dashboard goes where app/main.py expects it: <repo>/frontend/dist.
COPY --from=frontend /app/frontend/dist frontend/dist

# Vision models (YuNet/SFace/FER+) are NOT baked in — they are ~83 MB and
# git-ignored. Without them the app runs with detector "fallback" (REST/auth/
# reports/dashboard all work; live recognition does not). To enable recognition,
# mount a populated backend/models/ volume or run scripts/download_models.py.
ENV PRODUCTION=false \
    DATABASE_URL=sqlite:////data/classroom.db

EXPOSE 8000
WORKDIR /app/backend
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
