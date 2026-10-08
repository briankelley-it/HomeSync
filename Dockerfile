# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1: build Tailwind CSS and vendor htmx / Chart.js
# ---------------------------------------------------------------------------
FROM node:26-alpine AS assets
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY assets ./assets
COPY scripts/vendor.mjs ./scripts/vendor.mjs
COPY static ./static
# Tailwind scans templates and Python files for class names.
COPY templates ./templates
COPY apps ./apps
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: Python runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first so this layer is cached between code changes.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
COPY --from=assets /build/static ./static

# Collect static files at build time (placeholder secrets are build-only).
RUN DJANGO_SECRET_KEY=collectstatic-only DATABASE_URL=sqlite:////tmp/build.sqlite3 \
    python manage.py collectstatic --noinput

# Run as an unprivileged user; only the uploads directory is writable.
RUN useradd --system --uid 10001 --create-home houseledger \
    && mkdir -p /app/private_media \
    && chown houseledger /app/private_media
USER houseledger

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/', timeout=4)"

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
