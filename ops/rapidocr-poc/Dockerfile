# Independent experiment only; never published or used by Wealth deployment.
FROM python:3.11-slim-bookworm
ARG TARGETARCH
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 WEALTH_ENV=test WEALTH_DISABLE_ENV_FILE=1 WEALTH_DATA_DIR=/tmp/finance DATA_DIR=/tmp/finance
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils fonts-nanum libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
COPY ops/rapidocr-poc/requirements-*.lock /locks/
RUN python -m pip install --no-cache-dir --require-hashes -r /locks/requirements-${TARGETARCH}.lock \
    && python -m pip check
WORKDIR /app
# No data, environment files, credentials, frontend, or production entrypoint.
COPY app/__init__.py /app/app/__init__.py
COPY app/services /app/app/services
COPY app/config /app/app/config
COPY ops/pension-ocr/generate_fixtures.py /app/ops/pension-ocr/generate_fixtures.py
COPY ops/rapidocr-poc /app/ops/rapidocr-poc
USER 65534:65534
ENTRYPOINT ["python", "/app/ops/rapidocr-poc/run.py", "--inside"]
