# Imatge de l'API, el worker i el scheduler (el compose canvia el command).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /srv/app

# Dependències primer, per aprofitar la cache de capes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
# Migracions dins de la imatge: el servei `migrate` del compose executa
# `alembic upgrade head` abans que arrenqui l'API (specs/deployment.md).
COPY alembic.ini ./
COPY alembic ./alembic
COPY README.md ./
RUN uv sync --frozen --no-dev

# Mai com a root.
RUN useradd --system --no-create-home lagalia && chown -R lagalia:lagalia /srv/app
USER lagalia

ENV PATH="/srv/app/.venv/bin:$PATH"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
