FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy just what warm_up() needs first, so this expensive step is cached by
# Docker and only reruns if these specific files change — not on every
# unrelated source edit.
COPY core core
COPY ingestion ingestion
COPY utils utils

# Bake Chroma's embedding model into the image at build time. It downloads
# to ~/.cache/chroma/onnx_models (a user-level cache, not tied to
# CHROMA_PERSIST_DIR — see ingestion/embedder.py's warm_up() docstring), so
# doing this once here means every container start is fast, instead of a
# fresh container's first real request taking 60-90+ seconds.
RUN ANTHROPIC_API_KEY=build-time-placeholder \
    CHROMA_PERSIST_DIR=/tmp/build_chroma \
    python -c "from ingestion.embedder import VectorStoreManager; VectorStoreManager().warm_up()"

COPY . .

EXPOSE 8000

# CHROMA_PERSIST_DIR and JOB_DB_PATH are set by docker-compose.yml to point
# inside the mounted volume — see its comments for why.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
