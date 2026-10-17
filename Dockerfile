FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /uvx /usr/local/bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    MEMORY_OS_DATABASE_URL=sqlite:////app/data/memory.db \
    MEMORY_OS_KNOWLEDGE_DIR=/app/knowledge \
    MEMORY_OS_LOG_LEVEL=INFO \
    MEMORY_OS_CONFIGURATION_READ_ONLY=true \
    MEMORY_OS_AI_ENABLED=false \
    MEMORY_OS_AI_CONFIG_FILE=/app/config/ai-providers.yml \
    MEMORY_OS_RAG_ENABLED=false \
    MEMORY_OS_EMBEDDING_CONFIG_FILE=/app/config/embedding-providers.yml

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --python /usr/local/bin/python3 \
    && uv cache clean \
    && groupadd --gid 10001 memoryos \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin memoryos \
    && mkdir /app/data /app/knowledge /app/config \
    && chown 10001:10001 /app/data /app/knowledge

COPY app ./app
COPY config/ai-providers.example.yml ./config/ai-providers.example.yml
COPY config/embedding-providers.example.yml ./config/embedding-providers.example.yml
COPY alembic.ini ./
COPY migrations ./migrations
USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD ["/app/.venv/bin/python", "-c", "import json, urllib.request; response = urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3); assert response.status == 200 and json.load(response) == {'status': 'ok', 'database': 'ok'}"]

CMD ["/app/.venv/bin/uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
