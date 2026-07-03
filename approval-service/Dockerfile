FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

FROM base AS builder

COPY pyproject.toml .
RUN pip install --no-cache-dir --prefix=/install .

FROM base AS runtime

COPY --from=builder /install /usr/local
COPY src/ /app/src/
COPY alembic/ /app/alembic/
COPY alembic.ini /app/alembic.ini

USER app

EXPOSE 8000

CMD ["uvicorn", "approval_service.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
