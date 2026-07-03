# approval-service

Production-grade approval workflow engine. Manages multi-step approval chains with workspace isolation, idempotent mutations, append-only audit trail, and event-driven integration via transactional outbox.

## Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 |
| Framework | FastAPI 0.115 |
| ORM | SQLAlchemy 2.0 (async, `asyncpg`) |
| Migrations | Alembic |
| Database | PostgreSQL 16 |
| Validation | Pydantic v2 |
| Logging | structlog (JSON) |
| Container | Docker, docker compose |

## Quick Start

```bash
cd approval-service
docker compose up -d --build
```

The service starts at `http://localhost:8000`. API docs are available at `/docs` (Swagger) and `/redoc`.

### Local Development (without Docker)

```bash
# 1. Install dependencies
pip install -e ".[dev]"

# 2. Start PostgreSQL (e.g. via docker)
docker compose up -d db

# 3. Set database URL
export APPROVAL_DATABASE_URL="postgresql+asyncpg://approval:approval@localhost:5432/approval"

# 4. Run migrations
alembic upgrade head

# 5. Start dev server
uvicorn approval_service.main:create_app --factory --reload --host 0.0.0.0 --port 8000
```

## Migrations

```bash
# Apply all pending migrations
make migrate
# or
alembic upgrade head

# Create a new migration after model changes
alembic revision --autogenerate -m "description"

# Rollback one step
alembic downgrade -1
```

## Running Tests

```bash
# All tests (unit + integration)
make test
# or
pytest -v

# Integration tests only (uses SQLite in-memory, no PostgreSQL needed)
pytest tests/integration/ -v

# With coverage
pytest --cov=approval_service --cov-report=term-missing
```

### Linting and Type Checking

```bash
make lint        # ruff check + format check
make format      # auto-fix lint + format
make typecheck   # mypy strict mode
```

## Authentication Stub

The service does **not** implement authentication or authorization. Instead, it delegates identity to the API gateway via headers:

| Header | Required | Description |
|--------|----------|-------------|
| `X-Workspace-Id` | Yes | UUID of the tenant workspace. Every query is scoped to this workspace. Missing or invalid header returns `422` / `400`. |
| `Idempotency-Key` | No | Arbitrary string for POST idempotency. 24h TTL. Same key replays the cached response; same key on a different path returns `422`. |

Actor identity (`requester_id`, `actor_id`) is passed in request bodies. In production, the gateway should inject these from the authenticated session. The service enforces business rules (e.g. self-approval prevention) based on these IDs.

## API Endpoints

All endpoints are prefixed with `/api/v1`.

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health/live` | Liveness probe (always `200`) |
| `GET` | `/health/ready` | Readiness probe (checks DB connection) |

### Rules

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/rules` | Create approval rule |
| `GET` | `/rules` | List rules (filter: `resource_type`, `is_active`) |
| `GET` | `/rules/{id}` | Get rule by ID |
| `PUT` | `/rules/{id}` | Update rule (optimistic locking via `version`) |
| `DELETE` | `/rules/{id}` | Soft-delete (deactivate) rule |

### Requests

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/requests` | Create approval request |
| `GET` | `/requests` | List requests (filter: `status`, `resource_type`, `requester_id`) |
| `GET` | `/requests/{id}` | Get request with steps |
| `POST` | `/requests/{id}/cancel` | Cancel pending/in-review request |

### Decisions

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/requests/{id}/decisions` | Approve or reject active step |
| `GET` | `/requests/{id}/decisions` | List decisions for a request |

### Audit Log

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/audit-log` | List audit entries (filter: `entity_type`, `entity_id`, `actor_id`) |

## Example Requests (curl)

### Create a workspace-scoped rule

```bash
curl -s -X POST http://localhost:8000/api/v1/rules \
  -H "Content-Type: application/json" \
  -H "X-Workspace-Id: 550e8400-e29b-41d4-a716-446655440000" \
  -d '{
    "name": "Invoice approval",
    "resource_type": "invoice",
    "steps": [
      {"order": 1, "approver_role": "manager", "required_count": 1},
      {"order": 2, "approver_role": "cfo", "required_count": 1}
    ]
  }' | python -m json.tool
```

### Create an approval request

```bash
curl -s -X POST http://localhost:8000/api/v1/requests \
  -H "Content-Type: application/json" \
  -H "X-Workspace-Id: 550e8400-e29b-41d4-a716-446655440000" \
  -H "Idempotency-Key: create-inv-42" \
  -d '{
    "external_resource_id": "INV-42",
    "resource_type": "invoice",
    "title": "Invoice #42 — $15,000",
    "requester_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "rule_id": "<RULE_ID_FROM_ABOVE>",
    "payload": {"amount": 15000, "currency": "USD"}
  }' | python -m json.tool
```

### Approve the first step

```bash
curl -s -X POST http://localhost:8000/api/v1/requests/<REQUEST_ID>/decisions \
  -H "Content-Type: application/json" \
  -H "X-Workspace-Id: 550e8400-e29b-41d4-a716-446655440000" \
  -d '{
    "actor_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "action": "approve",
    "comment": "Looks good"
  }' | python -m json.tool
```

### Cancel a request

```bash
curl -s -X POST http://localhost:8000/api/v1/requests/<REQUEST_ID>/cancel \
  -H "Content-Type: application/json" \
  -H "X-Workspace-Id: 550e8400-e29b-41d4-a716-446655440000" \
  -d '{"actor_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"}' \
  | python -m json.tool
```

### Query the audit log

```bash
curl -s "http://localhost:8000/api/v1/audit-log?entity_type=approval_request&limit=10" \
  -H "X-Workspace-Id: 550e8400-e29b-41d4-a716-446655440000" \
  | python -m json.tool
```

### Replay an idempotent request

```bash
# Second call with the same Idempotency-Key returns the cached 201 response
curl -s -X POST http://localhost:8000/api/v1/requests \
  -H "Content-Type: application/json" \
  -H "X-Workspace-Id: 550e8400-e29b-41d4-a716-446655440000" \
  -H "Idempotency-Key: create-inv-42" \
  -d '{"external_resource_id":"INV-42","resource_type":"invoice","title":"Invoice #42","requester_id":"a1b2c3d4-e5f6-7890-abcd-ef1234567890"}' \
  | python -m json.tool
```

## Environment Variables

All variables use the `APPROVAL_` prefix (via pydantic-settings).

| Variable | Default | Description |
|----------|---------|-------------|
| `APPROVAL_DATABASE_URL` | _(required)_ | PostgreSQL connection string (`postgresql+asyncpg://...`) |
| `APPROVAL_DATABASE_POOL_SIZE` | `10` | SQLAlchemy connection pool size |
| `APPROVAL_DATABASE_MAX_OVERFLOW` | `5` | Max connections above pool size |
| `APPROVAL_DATABASE_ECHO` | `false` | Log all SQL statements |
| `APPROVAL_IDEMPOTENCY_KEY_TTL_HOURS` | `24` | TTL for stored idempotency responses |
| `APPROVAL_OUTBOX_POLL_INTERVAL_SECONDS` | `5` | Outbox publisher poll interval |
| `APPROVAL_OUTBOX_BATCH_SIZE` | `100` | Max events per outbox poll cycle |
| `APPROVAL_OUTBOX_MAX_RETRIES` | `5` | Max publish retries before dead-lettering |
| `APPROVAL_LOG_LEVEL` | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `APPROVAL_CORS_ORIGINS` | `[]` | Allowed CORS origins (JSON list) |

## Project Structure

```
approval-service/
  src/approval_service/
    domain/           # FSM, events, exceptions (zero I/O dependencies)
    application/      # Services, DTOs, interfaces (orchestration layer)
    infrastructure/   # ORM models, repositories, outbox, session factory
    api/              # FastAPI routers, middleware, schemas
    config.py         # pydantic-settings configuration
    main.py           # App factory
    dependencies.py   # FastAPI DI wiring
  tests/
    unit/             # Domain model tests (no I/O)
    integration/      # Full API tests via httpx + SQLite in-memory
  alembic/            # Database migrations
  Dockerfile
  docker-compose.yml
  pyproject.toml
  Makefile
```

## License

Private. All rights reserved.
