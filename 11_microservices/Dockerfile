FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi==0.115.* \
    "uvicorn[standard]==0.32.*" \
    sqlalchemy==2.0.* \
    psycopg2-binary==2.9.* \
    httpx==0.28.* \
    pydantic==2.10.*

COPY branches /app/branches

ENV PYTHONPATH=/app

CMD ["python", "-m", "branches._shared.branch_app"]
