# Approval Service --- Design Document

**Stack:** Python 3.12 + FastAPI + SQLAlchemy 2.0 (async) + Alembic + PostgreSQL 16  
**Status:** Draft  
**Author:** Staff Backend Engineer  

---

## 1. Архитектура проекта

### 1.1 Высокоуровневая архитектура

```
                    +-----------+
                    |  API GW / |
                    |  LB       |
                    +-----+-----+
                          |
                    +-----v-----+
                    | approval- |
                    | service   |
                    | (FastAPI) |
                    +-----+-----+
                          |
          +---------------+---------------+
          |               |               |
   +------v------+ +-----v------+ +------v------+
   | PostgreSQL  | | Event Bus  | | Object      |
   | (primary    | | (outbox    | | Store / S3  |
   |  store)     | | -> broker) | | (вложения)  |
   +-------------+ +------------+ +-------------+
```

### 1.2 Ключевые принципы

| Принцип | Реализация |
|---|---|
| **Workspace isolation** | Все запросы, правила и объекты привязаны к `workspace_id`. Middleware извлекает его из JWT/header и внедряет в каждый query через SQLAlchemy event listener. Нет cross-workspace доступа. |
| **Idempotency** | Клиент передаёт `Idempotency-Key` (UUID v4). Сервис хранит ключ + response в таблице `idempotency_keys` с TTL. При повторе --- отдаёт сохранённый ответ. |
| **Audit trail** | Append-only таблица `audit_log`. Каждая мутация генерирует запись. Нет UPDATE/DELETE на audit_log. |
| **Immutable terminal states** | FSM запрещает переходы из `approved` / `rejected` / `cancelled`. Проверка на уровне domain layer + DB constraint (CHECK на UPDATE trigger). |
| **Event-driven readiness** | Transactional Outbox pattern --- события пишутся в `outbox` таблицу в той же транзакции. Отдельный worker (или polling) публикует в брокер. |
| **Safe logging & responses** | Middleware фильтрует PII/secrets из логов. API responses не содержат internal IDs БД, stack traces, SQL. Structured JSON logging. |

### 1.3 Слои приложения

```
┌────────────────────────────────────────────────┐
│  Presentation Layer (FastAPI routers)          │
│  - HTTP handlers, request/response schemas     │
│  - Idempotency middleware                      │
│  - Auth & workspace middleware                 │
├────────────────────────────────────────────────┤
│  Application Layer (services / use cases)      │
│  - ApprovalService, RuleService                │
│  - Orchestration, transaction boundaries       │
│  - Event emission (outbox writes)              │
├────────────────────────────────────────────────┤
│  Domain Layer (models, FSM, value objects)     │
│  - ApprovalRequest entity + state machine      │
│  - ApprovalRule, ApprovalStep                  │
│  - Domain events                               │
├────────────────────────────────────────────────┤
│  Infrastructure Layer                          │
│  - SQLAlchemy repositories                     │
│  - Outbox publisher                            │
│  - External integrations (notifications, etc.) │
└────────────────────────────────────────────────┘
```

---

## 2. Структура папок

```
approval-service/
├── alembic/
│   ├── versions/
│   ├── env.py
│   └── alembic.ini
├── src/
│   └── approval_service/
│       ├── __init__.py
│       ├── main.py                    # FastAPI app factory
│       ├── config.py                  # pydantic-settings, env parsing
│       ├── dependencies.py            # FastAPI Depends factories
│       │
│       ├── api/                       # Presentation layer
│       │   ├── __init__.py
│       │   ├── v1/
│       │   │   ├── __init__.py
│       │   │   ├── routers/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── requests.py    # approval request CRUD
│       │   │   │   ├── rules.py       # approval rules management
│       │   │   │   ├── decisions.py   # approve / reject actions
│       │   │   │   └── health.py      # liveness + readiness
│       │   │   └── schemas/
│       │   │       ├── __init__.py
│       │   │       ├── requests.py    # pydantic request/response models
│       │   │       ├── rules.py
│       │   │       ├── decisions.py
│       │   │       └── common.py      # pagination, error envelope
│       │   └── middleware/
│       │       ├── __init__.py
│       │       ├── workspace.py       # workspace_id extraction & injection
│       │       ├── idempotency.py     # idempotency key handling
│       │       ├── logging_ctx.py     # structured logging context
│       │       └── error_handler.py   # global exception -> safe response
│       │
│       ├── domain/                    # Domain layer (no framework deps)
│       │   ├── __init__.py
│       │   ├── models/
│       │   │   ├── __init__.py
│       │   │   ├── approval_request.py
│       │   │   ├── approval_rule.py
│       │   │   ├── approval_step.py
│       │   │   └── enums.py           # RequestStatus, StepStatus, ActionType
│       │   ├── events.py             # domain event definitions
│       │   ├── exceptions.py         # domain-specific errors
│       │   └── fsm.py               # state machine transitions
│       │
│       ├── application/              # Application / service layer
│       │   ├── __init__.py
│       │   ├── services/
│       │   │   ├── __init__.py
│       │   │   ├── approval_service.py
│       │   │   ├── rule_service.py
│       │   │   └── audit_service.py
│       │   ├── dto.py                # internal data transfer objects
│       │   └── interfaces.py        # abstract repo & publisher ports
│       │
│       ├── infrastructure/           # Infrastructure layer
│       │   ├── __init__.py
│       │   ├── database/
│       │   │   ├── __init__.py
│       │   │   ├── session.py        # async engine + session factory
│       │   │   ├── base.py           # declarative base, mixins
│       │   │   └── models/           # SQLAlchemy ORM models (mapped)
│       │   │       ├── __init__.py
│       │   │       ├── approval_request.py
│       │   │       ├── approval_rule.py
│       │   │       ├── approval_step.py
│       │   │       ├── audit_log.py
│       │   │       ├── idempotency_key.py
│       │   │       └── outbox.py
│       │   ├── repositories/
│       │   │   ├── __init__.py
│       │   │   ├── approval_repo.py
│       │   │   ├── rule_repo.py
│       │   │   └── audit_repo.py
│       │   ├── outbox/
│       │   │   ├── __init__.py
│       │   │   └── publisher.py      # outbox polling / relay
│       │   └── logging/
│       │       ├── __init__.py
│       │       └── filters.py        # PII masking, safe serialization
│       │
│       └── common/                   # shared utilities
│           ├── __init__.py
│           ├── clock.py              # injectable time provider
│           └── pagination.py         # cursor/offset helpers
│
├── tests/
│   ├── conftest.py                   # fixtures: test DB, client, factories
│   ├── unit/
│   │   ├── domain/
│   │   │   ├── test_fsm.py
│   │   │   └── test_approval_request.py
│   │   └── application/
│   │       ├── test_approval_service.py
│   │       └── test_rule_service.py
│   ├── integration/
│   │   ├── test_api_requests.py
│   │   ├── test_api_decisions.py
│   │   ├── test_api_rules.py
│   │   ├── test_idempotency.py
│   │   ├── test_workspace_isolation.py
│   │   └── test_audit_trail.py
│   └── factories.py                  # test data factories
│
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml                # PG + service for local dev
└── Makefile                          # lint, test, migrate shortcuts
```

---

## 3. Модель данных

### 3.1 Таблицы

#### `workspaces`
| Колонка | Тип | Описание |
|---|---|---|
| `id` | UUID PK | Идентификатор воркспейса |
| `name` | VARCHAR(255) NOT NULL | Название |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |
| `is_active` | BOOLEAN NOT NULL DEFAULT true | Soft-delete |

#### `approval_rules`
| Колонка | Тип | Описание |
|---|---|---|
| `id` | UUID PK | |
| `workspace_id` | UUID FK -> workspaces NOT NULL | Изоляция |
| `name` | VARCHAR(255) NOT NULL | Человекочитаемое название правила |
| `description` | TEXT | |
| `resource_type` | VARCHAR(100) NOT NULL | Тип ресурса (invoice, purchase_order, contract...) |
| `conditions` | JSONB NOT NULL DEFAULT '{}' | Условия срабатывания (amount > X, department = Y) |
| `steps` | JSONB NOT NULL | Описание шагов: `[{order: 1, approver_role: "manager", required_count: 1}, ...]` |
| `is_active` | BOOLEAN NOT NULL DEFAULT true | |
| `version` | INTEGER NOT NULL DEFAULT 1 | Optimistic locking |
| `created_at` | TIMESTAMPTZ NOT NULL | |
| `updated_at` | TIMESTAMPTZ NOT NULL | |

**Index:** `(workspace_id, resource_type, is_active)`

#### `approval_requests`
| Колонка | Тип | Описание |
|---|---|---|
| `id` | UUID PK | |
| `workspace_id` | UUID FK -> workspaces NOT NULL | |
| `rule_id` | UUID FK -> approval_rules NOT NULL | Какое правило применялось |
| `external_resource_id` | VARCHAR(255) NOT NULL | ID ресурса во внешней системе |
| `resource_type` | VARCHAR(100) NOT NULL | Денормализация для запросов |
| `title` | VARCHAR(500) NOT NULL | |
| `payload` | JSONB NOT NULL DEFAULT '{}' | Метаданные ресурса (amount, department, etc.) |
| `status` | VARCHAR(20) NOT NULL DEFAULT 'pending' | `pending` -> `in_review` -> `approved` / `rejected` / `cancelled` |
| `requester_id` | UUID NOT NULL | Кто инициировал |
| `resolved_at` | TIMESTAMPTZ | Когда перешёл в финальное состояние |
| `created_at` | TIMESTAMPTZ NOT NULL | |
| `updated_at` | TIMESTAMPTZ NOT NULL | |

**Constraints:**
- `CHECK (status IN ('pending','in_review','approved','rejected','cancelled'))`
- Partial unique index: `(workspace_id, external_resource_id, resource_type) WHERE status NOT IN ('cancelled')` --- не даёт создать два активных запроса на один ресурс.

**Index:** `(workspace_id, status, created_at DESC)` для листинга.

#### `approval_steps`
| Колонка | Тип | Описание |
|---|---|---|
| `id` | UUID PK | |
| `request_id` | UUID FK -> approval_requests NOT NULL | |
| `workspace_id` | UUID NOT NULL | Денормализация для RLS |
| `step_order` | SMALLINT NOT NULL | Порядок шага (1, 2, 3...) |
| `approver_role` | VARCHAR(100) NOT NULL | Роль-цель |
| `required_count` | SMALLINT NOT NULL DEFAULT 1 | Сколько аппрувов нужно |
| `current_count` | SMALLINT NOT NULL DEFAULT 0 | Текущий счёт |
| `status` | VARCHAR(20) NOT NULL DEFAULT 'pending' | `pending` / `active` / `approved` / `rejected` |
| `activated_at` | TIMESTAMPTZ | Когда шаг стал активным |
| `completed_at` | TIMESTAMPTZ | |
| `created_at` | TIMESTAMPTZ NOT NULL | |

**Index:** `(request_id, step_order)` UNIQUE

#### `approval_decisions`
| Колонка | Тип | Описание |
|---|---|---|
| `id` | UUID PK | |
| `step_id` | UUID FK -> approval_steps NOT NULL | |
| `workspace_id` | UUID NOT NULL | |
| `actor_id` | UUID NOT NULL | Кто принял решение |
| `action` | VARCHAR(20) NOT NULL | `approve` / `reject` / `request_changes` |
| `comment` | TEXT | Опционально |
| `created_at` | TIMESTAMPTZ NOT NULL | |

**Constraint:** UNIQUE `(step_id, actor_id)` --- один актор не может голосовать дважды на одном шаге.

#### `audit_log`
| Колонка | Тип | Описание |
|---|---|---|
| `id` | BIGSERIAL PK | Автоинкремент для порядка |
| `workspace_id` | UUID NOT NULL | |
| `entity_type` | VARCHAR(50) NOT NULL | `approval_request`, `approval_rule`, ... |
| `entity_id` | UUID NOT NULL | |
| `action` | VARCHAR(50) NOT NULL | `created`, `status_changed`, `decision_made`, ... |
| `actor_id` | UUID | NULL для системных действий |
| `old_state` | JSONB | Снэпшот до |
| `new_state` | JSONB | Снэпшот после |
| `metadata` | JSONB DEFAULT '{}' | IP, user-agent, correlation_id |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |

**Особенности:**
- Таблица append-only. `REVOKE UPDATE, DELETE ON audit_log FROM app_user;` на уровне PG.
- Партиционирование по `created_at` (monthly) для production-scale.

**Index:** `(workspace_id, entity_type, entity_id, created_at DESC)`

#### `idempotency_keys`
| Колонка | Тип | Описание |
|---|---|---|
| `key` | VARCHAR(255) PK | UUID v4 от клиента |
| `workspace_id` | UUID NOT NULL | |
| `method` | VARCHAR(10) NOT NULL | HTTP method |
| `path` | VARCHAR(500) NOT NULL | Request path |
| `status_code` | SMALLINT NOT NULL | Сохранённый HTTP status |
| `response_body` | JSONB NOT NULL | Сохранённый response |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |
| `expires_at` | TIMESTAMPTZ NOT NULL | TTL = created_at + 24h |

**Index:** `(expires_at)` для cleanup job.

#### `outbox`
| Колонка | Тип | Описание |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `event_type` | VARCHAR(100) NOT NULL | `approval.request.created`, `approval.request.approved`, ... |
| `aggregate_type` | VARCHAR(50) NOT NULL | `approval_request` |
| `aggregate_id` | UUID NOT NULL | |
| `workspace_id` | UUID NOT NULL | |
| `payload` | JSONB NOT NULL | Event payload |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |
| `published_at` | TIMESTAMPTZ | NULL пока не опубликовано |
| `retry_count` | SMALLINT NOT NULL DEFAULT 0 | |

**Index:** `(published_at) WHERE published_at IS NULL` --- для polling.

---

## 4. ER-диаграмма (текст)

```
┌──────────────┐
│  workspaces  │
│──────────────│
│ PK id        │
│    name      │
│    is_active │
└──────┬───────┘
       │ 1
       │
       │ *
┌──────┴───────────┐         ┌──────────────────┐
│ approval_rules   │         │  idempotency_keys│
│──────────────────│         │──────────────────│
│ PK id            │         │ PK key           │
│ FK workspace_id  │         │    workspace_id  │
│    resource_type │         │    method, path  │
│    conditions    │         │    response_body │
│    steps (JSONB) │         │    expires_at    │
│    version       │         └──────────────────┘
└──────┬───────────┘
       │ 1
       │                      ┌──────────────────┐
       │ *                    │    audit_log     │
┌──────┴───────────┐         │──────────────────│
│approval_requests │         │ PK id (BIGSERIAL)│
│──────────────────│    *    │    workspace_id  │
│ PK id            │────────>│    entity_type   │
│ FK workspace_id  │ writes  │    entity_id     │
│ FK rule_id       │         │    action        │
│    ext_resource_id         │    old/new_state │
│    status        │         │    actor_id      │
│    requester_id  │         │    metadata      │
│    payload       │         └──────────────────┘
└──────┬───────────┘
       │ 1                    ┌──────────────────┐
       │                      │     outbox       │
       │ *                    │──────────────────│
┌──────┴───────────┐         │ PK id (BIGSERIAL)│
│ approval_steps   │         │    event_type    │
│──────────────────│    *    │    aggregate_id  │
│ PK id            │────────>│    workspace_id  │
│ FK request_id    │ emits   │    payload       │
│    workspace_id  │         │    published_at  │
│    step_order    │         └──────────────────┘
│    approver_role │
│    required_count│
│    current_count │
│    status        │
└──────┬───────────┘
       │ 1
       │
       │ *
┌──────┴───────────────┐
│ approval_decisions   │
│──────────────────────│
│ PK id                │
│ FK step_id           │
│    workspace_id      │
│    actor_id          │
│    action            │
│    comment           │
└──────────────────────┘
```

**Связи:**
- `workspace` 1 --- * `approval_rules`
- `workspace` 1 --- * `approval_requests`
- `approval_rule` 1 --- * `approval_requests`
- `approval_request` 1 --- * `approval_steps`
- `approval_step` 1 --- * `approval_decisions`
- Все мутации --- * `audit_log` (логическая связь, не FK)
- Все мутации --- * `outbox` (логическая связь, не FK)

---

## 5. REST API дизайн

### Base URL: `/api/v1`

Все endpoints требуют header `X-Workspace-Id` (или из JWT claim).

### 5.1 Approval Requests

| Method | Path | Описание | Idempotent |
|---|---|---|---|
| `POST` | `/requests` | Создать запрос на аппрув | Да (`Idempotency-Key`) |
| `GET` | `/requests` | Список запросов (фильтры: status, resource_type, requester_id; pagination) | Naturally |
| `GET` | `/requests/{id}` | Получить запрос с шагами | Naturally |
| `POST` | `/requests/{id}/cancel` | Отменить запрос (только из `pending` / `in_review`) | Да |

### 5.2 Decisions

| Method | Path | Описание | Idempotent |
|---|---|---|---|
| `POST` | `/requests/{id}/decisions` | Принять решение (approve/reject) по текущему шагу | Да |
| `GET` | `/requests/{id}/decisions` | История решений по запросу | Naturally |

### 5.3 Approval Rules

| Method | Path | Описание | Idempotent |
|---|---|---|---|
| `POST` | `/rules` | Создать правило | Да |
| `GET` | `/rules` | Список правил (фильтр: resource_type, is_active) | Naturally |
| `GET` | `/rules/{id}` | Получить правило | Naturally |
| `PUT` | `/rules/{id}` | Обновить правило (optimistic lock via `version`) | Idempotent by nature |
| `DELETE` | `/rules/{id}` | Soft-delete (is_active=false) | Idempotent by nature |

### 5.4 Audit

| Method | Path | Описание |
|---|---|---|
| `GET` | `/audit-log` | Список записей аудита (фильтры: entity_type, entity_id, actor_id, date range; cursor pagination) |

### 5.5 Health

| Method | Path | Описание |
|---|---|---|
| `GET` | `/health/live` | Liveness probe (always 200) |
| `GET` | `/health/ready` | Readiness probe (DB connectivity check) |

### 5.6 Response Envelope

```json
// Success
{
  "data": { ... },
  "meta": {
    "request_id": "corr-uuid",
    "timestamp": "2025-01-15T10:30:00Z"
  }
}

// Success (list)
{
  "data": [ ... ],
  "meta": { "request_id": "...", "timestamp": "..." },
  "pagination": {
    "total": 142,
    "limit": 20,
    "offset": 0,
    "has_more": true
  }
}

// Error
{
  "error": {
    "code": "APPROVAL_ALREADY_RESOLVED",
    "message": "This approval request has already been resolved.",
    "details": {}
  },
  "meta": {
    "request_id": "corr-uuid",
    "timestamp": "2025-01-15T10:30:00Z"
  }
}
```

### 5.7 HTTP Status Codes

| Код | Использование |
|---|---|
| 200 | GET success, idempotent replay |
| 201 | POST created (first time) |
| 204 | DELETE success |
| 400 | Validation error |
| 404 | Resource not found (в текущем workspace) |
| 409 | Conflict: invalid state transition, duplicate active request, optimistic lock failure |
| 422 | Unprocessable: бизнес-правило нарушено (например, approver = requester) |
| 429 | Rate limit exceeded |
| 500 | Internal server error (no details leaked) |

---

## 6. Стратегия идемпотентности

### 6.1 Механизм

```
Client                          Server
  |                                |
  |  POST /requests               |
  |  Idempotency-Key: uuid-abc    |
  |------------------------------->|
  |                                |
  |    1. SELECT FROM idempotency_keys WHERE key = 'uuid-abc'
  |       AND workspace_id = :ws
  |                                |
  |    [Key not found]             |
  |    2. BEGIN TX                 |
  |    3. INSERT idempotency_key (status=processing)
  |       -- advisory lock на key hash для concurrency
  |    4. Execute business logic   |
  |    5. UPDATE idempotency_key SET response=..., status_code=201
  |    6. COMMIT TX               |
  |                                |
  |  <--- 201 Created             |
  |                                |
  |  POST /requests (retry)       |
  |  Idempotency-Key: uuid-abc    |
  |------------------------------->|
  |                                |
  |    1. SELECT -> found, has response
  |    2. Return stored response   |
  |                                |
  |  <--- 201 Created (same body) |
```

### 6.2 Правила

1. **Scope:** `Idempotency-Key` обязателен для всех `POST` endpoints. Опционален для `PUT`/`DELETE` (они идемпотентны по природе).
2. **Uniqueness:** Ключ уникален в рамках `(workspace_id, key)`.
3. **TTL:** 24 часа. Cron job удаляет expired записи.
4. **Concurrency:** PostgreSQL advisory lock (`pg_advisory_xact_lock(hashtext(key))`) предотвращает race condition при параллельных retry.
5. **Request fingerprint:** При повторе проверяется совпадение `method + path`. Mismatch --- 422 ошибка ("Idempotency key already used for a different request").
6. **In-flight detection:** Если ключ в статусе `processing` --- ответ `409 Conflict` с `Retry-After: 1`.

### 6.3 Middleware

```python
# Псевдокод middleware (НЕ реализация)
async def idempotency_middleware(request, call_next):
    key = request.headers.get("Idempotency-Key")
    if request.method != "POST" or not key:
        return await call_next(request)
    
    existing = await repo.get_idempotency_key(key, workspace_id)
    if existing and existing.has_response:
        return Response(existing.response_body, existing.status_code)
    if existing and existing.is_processing:
        return Response(status=409, headers={"Retry-After": "1"})
    
    # acquire advisory lock, insert key, execute, save response
    ...
```

---

## 7. Стратегия аудита

### 7.1 Подход

**Append-only event sourcing-like audit**, но без полного event sourcing (primary store --- обычная CRUD-модель).

### 7.2 Что логируется

| Действие | entity_type | action | Содержимое |
|---|---|---|---|
| Создание запроса | `approval_request` | `created` | new_state: полный snapshot |
| Изменение статуса | `approval_request` | `status_changed` | old_state: {status: "pending"}, new_state: {status: "in_review"} |
| Решение (approve/reject) | `approval_decision` | `decision_made` | new_state: {action, step_order, actor_id, comment} |
| Шаг завершён | `approval_step` | `step_completed` | old/new state шага |
| Создание правила | `approval_rule` | `created` | new_state snapshot |
| Обновление правила | `approval_rule` | `updated` | diff old/new |
| Деактивация правила | `approval_rule` | `deactivated` | old_state |
| Отмена запроса | `approval_request` | `cancelled` | actor_id, reason |

### 7.3 Реализация

```python
# Псевдокод --- НЕ реализация
class AuditService:
    async def log(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        entity_type: str,
        entity_id: UUID,
        action: str,
        actor_id: UUID | None,
        old_state: dict | None,
        new_state: dict | None,
        metadata: dict | None,
    ):
        """Запись в той же транзакции, что и бизнес-операция."""
        entry = AuditLogEntry(...)
        session.add(entry)
        # НЕ делаем commit --- это часть внешней транзакции
```

### 7.4 Защита данных в аудите

- `old_state` / `new_state` **не содержат** PII сверх того, что уже в самой сущности.
- Поле `metadata` хранит: `correlation_id`, `ip_address` (hashed), `user_agent` (truncated).
- Ротация: партиционирование по месяцам, retention policy = конфигурируемый (default 2 года).
- Доступ к audit log --- отдельный RBAC permission `audit:read`.

---

## 8. Стратегия событий (Event-Driven)

### 8.1 Transactional Outbox Pattern

**Почему outbox, а не прямая публикация:**  
Прямая публикация в broker (Kafka/RabbitMQ) из HTTP handler создаёт dual-write problem --- если commit прошёл, а publish упал (или наоборот), данные расходятся. Outbox решает это.

```
┌─────────────────────────────────────────┐
│           HTTP Handler (POST)           │
│                                         │
│  BEGIN TX                               │
│    INSERT approval_request              │
│    INSERT audit_log                     │
│    INSERT outbox (event)                │
│  COMMIT TX                              │
│                                         │
│  --> Всё или ничего                     │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│        Outbox Publisher (worker)        │
│                                         │
│  POLL: SELECT FROM outbox              │
│        WHERE published_at IS NULL       │
│        ORDER BY id LIMIT 100            │
│        FOR UPDATE SKIP LOCKED           │
│                                         │
│  PUBLISH to broker                      │
│  UPDATE outbox SET published_at = now() │
└─────────────────────────────────────────┘
```

### 8.2 Типы событий

| Event Type | Trigger | Payload |
|---|---|---|
| `approval.request.created` | Новый запрос создан | request_id, resource_type, external_resource_id, requester_id |
| `approval.request.status_changed` | Статус изменился | request_id, old_status, new_status |
| `approval.request.approved` | Финальный аппрув | request_id, external_resource_id, resolved_at |
| `approval.request.rejected` | Финальный реджект | request_id, external_resource_id, resolved_at, last_rejector_id |
| `approval.request.cancelled` | Отмена | request_id, cancelled_by |
| `approval.step.activated` | Новый шаг стал активным | request_id, step_id, step_order, approver_role |
| `approval.decision.made` | Решение принято | request_id, step_id, actor_id, action |

### 8.3 Event Envelope

```json
{
  "event_id": "evt-uuid",
  "event_type": "approval.request.approved",
  "aggregate_type": "approval_request",
  "aggregate_id": "req-uuid",
  "workspace_id": "ws-uuid",
  "timestamp": "2025-01-15T10:30:00Z",
  "version": 1,
  "payload": {
    "external_resource_id": "INV-2025-001",
    "resource_type": "invoice",
    "resolved_at": "2025-01-15T10:30:00Z"
  },
  "metadata": {
    "correlation_id": "corr-uuid",
    "caused_by": "decision-uuid"
  }
}
```

### 8.4 Гарантии доставки

- **At-least-once delivery.** Consumers должны быть идемпотентными.
- `event_id` (UUID) --- consumer использует для дедупликации.
- Retry с exponential backoff (max 5 retries), после --- dead letter.
- Порядок гарантирован в рамках одного `aggregate_id` (partition key = aggregate_id).

---

## 9. Обработка ошибок

### 9.1 Иерархия исключений

```
AppError (base)
├── DomainError
│   ├── InvalidStateTransitionError    # FSM violation
│   ├── AlreadyResolvedError           # attempt to modify terminal state
│   ├── DuplicateActiveRequestError    # unique constraint on active requests
│   ├── SelfApprovalError              # requester == approver
│   └── StepNotActiveError             # decision on non-active step
├── NotFoundError
│   ├── RequestNotFoundError
│   ├── RuleNotFoundError
│   └── StepNotFoundError
├── ConflictError
│   ├── OptimisticLockError            # version mismatch on rule update
│   ├── IdempotencyKeyConflictError    # key reuse with different request
│   └── ConcurrentProcessingError      # idempotency key in-flight
├── AuthorizationError
│   ├── WorkspaceMismatchError         # cross-workspace access attempt
│   └── InsufficientPermissionsError
└── ValidationError                    # schema/input validation
```

### 9.2 Маппинг на HTTP коды

```python
ERROR_STATUS_MAP = {
    InvalidStateTransitionError: 409,
    AlreadyResolvedError: 409,
    DuplicateActiveRequestError: 409,
    SelfApprovalError: 422,
    StepNotActiveError: 422,
    NotFoundError: 404,           # все подклассы
    OptimisticLockError: 409,
    IdempotencyKeyConflictError: 422,
    ConcurrentProcessingError: 409,  # + Retry-After header
    WorkspaceMismatchError: 404,     # 404, NOT 403 (не раскрываем существование)
    InsufficientPermissionsError: 403,
    ValidationError: 400,
}
```

### 9.3 Global Exception Handler

```python
# Псевдокод
@app.exception_handler(AppError)
async def handle_app_error(request, exc):
    status = ERROR_STATUS_MAP.get(type(exc), 500)
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": exc.error_code,       # e.g. "ALREADY_RESOLVED"
                "message": exc.safe_message,   # user-facing, no internals
                "details": exc.details or {},
            },
            "meta": {"request_id": request.state.correlation_id, ...}
        }
    )

@app.exception_handler(Exception)
async def handle_unexpected(request, exc):
    logger.exception("Unhandled exception", extra={"correlation_id": ...})
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred.",  # NO details
            },
            "meta": {"request_id": ...}
        }
    )
```

### 9.4 Принципы безопасности ошибок

1. **Никогда** не возвращать stack trace, SQL, internal entity IDs в production.
2. `WorkspaceMismatchError` маппится на `404`, не `403` --- чтобы не подтверждать существование ресурса в другом workspace.
3. Все ошибки логируются с `correlation_id` для трейсинга.
4. Unhandled exceptions --- generic 500 + alert в мониторинг.

---

## 10. FSM (State Machine) --- Approval Request

```
                    ┌──────────┐
         ┌─────────│ pending  │──────────┐
         │         └────┬─────┘          │
         │              │                │
         │   [first step activated]      │
         │              │                │ [cancel]
         │         ┌────v─────┐          │
         │         │in_review │──────────┤
         │         └──┬────┬──┘          │
         │            │    │             │
         │  [all steps │    │ [any step  │
         │  approved]  │    │  rejected] │
         │            │    │             │
         │    ┌───────v┐  ┌v────────┐  ┌v─────────┐
         │    │approved│  │rejected │  │cancelled │
         │    └────────┘  └─────────┘  └──────────┘
         │         ▲           ▲            ▲
         │         │           │            │
         └─────────┴───────────┴────────────┘
                TERMINAL --- no transitions out
```

**Допустимые переходы:**

| From | To | Trigger |
|---|---|---|
| `pending` | `in_review` | Первый шаг активирован |
| `pending` | `cancelled` | Requester отменяет |
| `in_review` | `approved` | Все шаги пройдены |
| `in_review` | `rejected` | Любой шаг отклонён |
| `in_review` | `cancelled` | Requester отменяет |

**Запрещены:**
- Любой переход из `approved`, `rejected`, `cancelled` --- `AlreadyResolvedError(409)`.

---

## 11. Список тестов

### 11.1 Unit Tests (domain layer, без БД)

| # | Тест | Что проверяет |
|---|---|---|
| U-01 | `test_fsm_pending_to_in_review` | Переход pending -> in_review |
| U-02 | `test_fsm_in_review_to_approved` | Переход in_review -> approved |
| U-03 | `test_fsm_in_review_to_rejected` | Переход in_review -> rejected |
| U-04 | `test_fsm_pending_to_cancelled` | Отмена из pending |
| U-05 | `test_fsm_in_review_to_cancelled` | Отмена из in_review |
| U-06 | `test_fsm_approved_is_terminal` | Нельзя перейти из approved |
| U-07 | `test_fsm_rejected_is_terminal` | Нельзя перейти из rejected |
| U-08 | `test_fsm_cancelled_is_terminal` | Нельзя перейти из cancelled |
| U-09 | `test_fsm_invalid_transition_raises` | Невалидный переход -> исключение |
| U-10 | `test_step_approve_increments_count` | current_count += 1 при approve |
| U-11 | `test_step_completes_when_threshold_met` | step -> approved при required_count == current_count |
| U-12 | `test_step_rejects_entire_request` | reject на шаге -> request rejected |
| U-13 | `test_self_approval_rejected` | requester == actor -> SelfApprovalError |
| U-14 | `test_duplicate_decision_rejected` | Второй approve от того же actor -> ошибка |
| U-15 | `test_decision_on_inactive_step_rejected` | Решение на неактивный шаг -> ошибка |

### 11.2 Integration Tests (с тестовой БД)

| # | Тест | Что проверяет |
|---|---|---|
| I-01 | `test_create_request_201` | POST /requests -> 201, запись в БД |
| I-02 | `test_create_request_idempotent` | Повтор POST с тем же ключом -> тот же response |
| I-03 | `test_idempotency_key_mismatch` | Тот же ключ, другой path -> 422 |
| I-04 | `test_idempotency_concurrent_requests` | Параллельные retry -> один создаёт, второй получает stored |
| I-05 | `test_get_request_200` | GET /requests/{id} -> данные + шаги |
| I-06 | `test_get_request_other_workspace_404` | Запрос из чужого workspace -> 404 |
| I-07 | `test_list_requests_filtered` | GET /requests?status=pending -> фильтрация |
| I-08 | `test_list_requests_pagination` | Пагинация offset/limit |
| I-09 | `test_approve_decision_201` | POST /requests/{id}/decisions {action: approve} |
| I-10 | `test_reject_decision_201` | POST /requests/{id}/decisions {action: reject} |
| I-11 | `test_full_approval_flow` | Создание -> шаги -> all approved -> request approved |
| I-12 | `test_rejection_terminates_request` | Один reject -> весь request rejected |
| I-13 | `test_cancel_request_from_pending` | POST cancel из pending |
| I-14 | `test_cancel_request_from_in_review` | POST cancel из in_review |
| I-15 | `test_action_on_resolved_request_409` | Approve/reject на approved request -> 409 |
| I-16 | `test_workspace_isolation_rules` | Правила workspace A не видны workspace B |
| I-17 | `test_workspace_isolation_requests` | Запросы workspace A не видны workspace B |
| I-18 | `test_create_rule_201` | POST /rules -> 201 |
| I-19 | `test_update_rule_optimistic_lock` | PUT с неверной version -> 409 |
| I-20 | `test_soft_delete_rule` | DELETE -> is_active=false |
| I-21 | `test_audit_log_created_on_request` | После создания запроса -> запись в audit_log |
| I-22 | `test_audit_log_created_on_decision` | После решения -> запись в audit_log |
| I-23 | `test_audit_log_immutable` | Попытка UPDATE audit_log -> ошибка (PG permission) |
| I-24 | `test_outbox_event_created` | После мутации -> запись в outbox |
| I-25 | `test_outbox_publisher_marks_published` | Publisher обрабатывает -> published_at заполнен |
| I-26 | `test_duplicate_active_request_409` | Два запроса на один resource -> 409 |
| I-27 | `test_health_live` | GET /health/live -> 200 |
| I-28 | `test_health_ready` | GET /health/ready -> 200 (с БД) |
| I-29 | `test_error_response_no_internals` | 500 ошибка не содержит stack trace / SQL |
| I-30 | `test_idempotency_key_cleanup` | Expired ключи удаляются по cron |

### 11.3 Нагрузочные / Stress тесты (описание, не автоматизация)

| # | Тест | Что проверяет |
|---|---|---|
| S-01 | Concurrent approvals on same step | Race condition на current_count |
| S-02 | High-volume outbox processing | Publisher не теряет события под нагрузкой |
| S-03 | Idempotency under concurrency | Advisory lock работает корректно |

---

## 12. Дополнительные решения

### 12.1 Безопасное логирование

- **structlog** с JSON output.
- Middleware добавляет `correlation_id` (из `X-Request-Id` header или генерируется).
- PII filter: email, phone, имена маскируются в логах (`***@***.com`).
- Request/response body **не логируются** (кроме structured metadata).
- Уровни: `INFO` для бизнес-событий, `WARNING` для бизнес-ошибок, `ERROR` для unhandled.

### 12.2 Workspace Isolation --- имплементация

```python
# Подход: SQLAlchemy event listener
# Каждый SELECT/INSERT/UPDATE автоматически получает WHERE workspace_id = :ws
# через execution_options + query compilation event.
#
# Альтернатива: PostgreSQL Row-Level Security (RLS) policies,
# но это усложняет миграции и тестирование.
#
# Выбор: Application-level filtering через middleware + repository layer.
# Repository базовый класс принимает workspace_id и добавляет в каждый query.
```

### 12.3 Миграции (Alembic)

- `alembic/versions/` --- все миграции.
- Naming convention: `{rev}_{slug}.py` (auto-generated).
- Каждая миграция имеет `upgrade()` и `downgrade()`.
- CI проверяет: `alembic check` (нет расхождений модель vs. миграции).
- Zero-downtime: миграции разделены на backward-compatible (additive) и breaking (с feature flags).

### 12.4 Конфигурация

```python
# pydantic-settings
class Settings(BaseSettings):
    database_url: PostgresDsn          # обязательный
    database_pool_size: int = 10
    database_max_overflow: int = 5
    idempotency_key_ttl_hours: int = 24
    outbox_poll_interval_seconds: int = 5
    outbox_batch_size: int = 100
    log_level: str = "INFO"
    cors_origins: list[str] = []
    
    model_config = SettingsConfigDict(env_prefix="APPROVAL_")
```

---

## Резюме

Сервис спроектирован с учётом:

1. **Workspace isolation** --- каждый запрос фильтруется по workspace_id на уровне repository.
2. **Idempotency** --- `Idempotency-Key` + advisory lock + stored response pattern.
3. **Audit trail** --- append-only `audit_log`, запись в одной транзакции с бизнес-операцией.
4. **Immutable terminal states** --- FSM + CHECK constraint + domain validation.
5. **Event-driven readiness** --- Transactional Outbox pattern, at-least-once delivery.
6. **Safe responses** --- error hierarchy с маппингом на HTTP коды, no internals leaked, structured logging с PII masking.

Готов к code review вопросам.
