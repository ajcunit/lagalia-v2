# LAGALia v2 — Backend

API de gestió de contractació pública (FastAPI + SQLAlchemy async).
Documentació d'arquitectura a [docs/03-arquitectura.md](../docs/03-arquitectura.md).

## Desenvolupament

```bash
uv sync                                  # crea .venv i instal·la dependències
uv run uvicorn app.main:app --reload     # http://localhost:8000/docs
uv run pytest                            # tests
uv run ruff check . && uv run mypy app   # lint i tipatge
```

L'aplicació té **dos processos**: l'API (uvicorn) i el **worker de la cua**
(arq), que executa sincronitzacions, enriquiments i la resta de jobs. Sense
worker, els jobs queden `queued` per sempre. En desenvolupament, en un segon
terminal:

```bash
# Windows (l'antivirus bloqueja arq.exe; s'invoca el CLI via python)
$env:PYTHONIOENCODING = "utf-8"
.venv/Scripts/python -c "from arq.cli import cli; cli()" app.jobs.worker.WorkerSettings

# Linux/macOS
uv run arq app.jobs.worker.WorkerSettings
```

Amb `docker compose --profile app up` el worker ja s'aixeca com a servei.

La configuració es llegeix de variables d'entorn (vegeu `.env.example` a l'arrel).
L'aplicació **no arrenca** sense `SECRET_KEY` i `ENCRYPTION_KEY`.
