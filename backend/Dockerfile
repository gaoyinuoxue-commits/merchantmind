FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
COPY scripts ./scripts

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=6 \
    CMD python -c "import json,sys,urllib.request as u; r=u.urlopen('http://localhost:8000/api/health', timeout=3); sys.exit(0 if r.status==200 and json.load(r)['database']['status']=='up' else 1)"

CMD ["sh", "-c", "alembic upgrade head && PYTHONPATH=/app python scripts/seed_database.py --full --knowledge && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
