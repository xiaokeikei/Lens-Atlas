FROM node:22-bookworm-slim AS web
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LENS_DATA_DIR=/data LENS_MEDIA_ROOTS=/media
RUN apt-get update && apt-get install -y --no-install-recommends libimage-exiftool-perl ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 app \
    && mkdir -p /data /media && chown app:app /data
WORKDIR /app
COPY requirements-server.txt ./
RUN pip install --no-cache-dir -r requirements-server.txt
COPY backend/ ./backend/
COPY --from=web /build/dist/ ./frontend/dist/
COPY LICENSE THIRD_PARTY_NOTICES.md ./
# Source archives may carry private host permissions; runtime users need read
# access to application files, independently of the chosen NAS UID/GID.
RUN chmod -R a+rX /app/backend /app/frontend && chmod a+r /app/LICENSE /app/THIRD_PARTY_NOTICES.md
USER app
VOLUME ["/data"]
EXPOSE 52032
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:52032/api/health', timeout=3)"
CMD ["python", "-m", "backend", "--host", "0.0.0.0", "--port", "52032"]
