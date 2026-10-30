# Stage 1: build the React app to static files.
FROM node:20.19-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Firebase web config: public by design (it identifies the project, it isn't a secret).
ARG VITE_FIREBASE_API_KEY
ARG VITE_FIREBASE_AUTH_DOMAIN
ARG VITE_FIREBASE_PROJECT_ID
ARG VITE_FIREBASE_APP_ID
RUN npm run build

# Stage 2: the Python API, which also serves the built frontend.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
# Run as a non-root user. The code is copied owned by it, so it stays readable whatever
# the file permissions were on the machine that built the image.
RUN useradd --create-home app
COPY --chown=app:app backend/ backend/
COPY --chown=app:app --from=frontend /frontend/dist frontend/dist
USER app
# Cloud Run sets PORT.
CMD ["sh", "-c", "exec /app/.venv/bin/uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8080}"]
