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

La configuració es llegeix de variables d'entorn (vegeu `.env.example` a l'arrel).
L'aplicació **no arrenca** sense `SECRET_KEY` i `ENCRYPTION_KEY`.
