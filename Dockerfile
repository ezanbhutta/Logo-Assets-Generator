# syntax=docker/dockerfile:1
# Logo Package Engine — production image (single container = UI + API).
# Stage 1 builds the Vite frontend; stage 2 runs FastAPI with the native
# vector toolchain and serves the built frontend from the same origin.

# ---- Stage 1: build the frontend ----
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build            # -> /app/frontend/dist

# ---- Stage 2: backend runtime ----
FROM python:3.11-slim AS runtime

# Native toolchain: pdf2svg (.ai->SVG), rsvg-convert (vector PDF),
# poppler-utils (pdftocairo fallback), cairo (cairosvg PNG/JPG). apt pulls the
# transitive cairo/pango/poppler libraries automatically.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      pdf2svg librsvg2-bin poppler-utils libcairo2 fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOGO_WORK_ROOT=/tmp/logo_jobs

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend
# main.py mounts ../../frontend/dist relative to backend/app/, i.e. /app/frontend/dist
COPY --from=frontend /app/frontend/dist ./frontend/dist

EXPOSE 8000
# Render (and most PaaS) inject $PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}"]
