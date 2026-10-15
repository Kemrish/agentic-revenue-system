FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS builder
WORKDIR /build
RUN python -m pip install --no-cache-dir build==1.6.1 hatchling==1.32.4
COPY pyproject.toml README.md ./
COPY src ./src
COPY packs ./packs
RUN python -m build --wheel --no-isolation

FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock ./
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.lock
COPY --from=builder /build/dist/*.whl /tmp/
RUN python -m pip install --no-cache-dir --no-deps /tmp/*.whl && \
    useradd --uid 10001 --create-home revenue && \
    mkdir -p /data /backups && chown revenue:revenue /data /backups
USER revenue
ENV DATABASE_URL=sqlite:////data/production.db
CMD ["python", "-m", "revenue_system.cli", "ui", "--host", "0.0.0.0"]
