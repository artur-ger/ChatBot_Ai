ARG PYTHON_BASE_IMAGE=python:3.12-slim
FROM ${PYTHON_BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=2.2.1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=15 \
    POETRY_HTTP_TIMEOUT=600

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY certs/russian_trusted_root_ca_pem.crt certs/russian_trusted_sub_ca_pem.crt \
    /usr/local/share/ca-certificates/
RUN chmod 644 /usr/local/share/ca-certificates/russian_trusted_*.crt \
    && update-ca-certificates

RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

COPY pyproject.toml poetry.lock README.md /app/
RUN poetry install --no-root --with dev

COPY certs/russian_trusted_root_ca_pem.crt certs/russian_trusted_sub_ca_pem.crt /app/certs/
COPY scripts/build_ca_bundle.py /tmp/build_ca_bundle.py
RUN poetry run python /tmp/build_ca_bundle.py \
        --output /app/certs/ca-bundle.crt \
        /app/certs/russian_trusted_root_ca_pem.crt \
        /app/certs/russian_trusted_sub_ca_pem.crt \
    && rm /tmp/build_ca_bundle.py

ENV SSL_CERT_FILE=/app/certs/ca-bundle.crt \
    REQUESTS_CA_BUNDLE=/app/certs/ca-bundle.crt

COPY app /app/app
COPY tests /app/tests
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini

EXPOSE 8000

CMD ["sh", "-c", "poetry run alembic upgrade head && poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000"]
