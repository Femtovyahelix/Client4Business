# approval-service: Design Document

## 1. Service Boundaries

### What This Service Does

- Manages the lifecycle of multi-step approval workflows: create request, route through sequential approval steps, record decisions, reach terminal state (approved / rejected / cancelled).
- Provides CRUD for approval rules that define step chains (role, quorum) per resource type.
- Maintains an append-only audit trail for every mutation.
- Writes domain events to a transactional outbox for downstream consumers.

### What This Service Does Not Do

- **Authentication / Authorization.** Identity is delegated to the API gateway via `X-Workspace-Id` header and `actor_id` / `requester_id` in request bodies. The service enforces business rules (self-approval prevention, workspace isolation) but does not verify tokens or sessions.
- **Notification delivery.** The service publishes events (`approval.request.created`, `approval.step.activated`, etc.) via outbox. A separate consumer is responsible for sending emails, Slack messages, or push notifications.
- **File storage or rich content.** The `payload` field (JSONB) stores arbitrary metadata from the caller; the service treats it as opaque.
- **Rule evaluation / matching.** The `conditions` field on rules is stored but not evaluated. The caller selects the rule by ID or the service picks the first active rule matching the `resource_type`. Condition-based routing is a future extension point.

### API Boundary

All endpoints live under `/api/v1`. The service exposes 14 endpoints across 5 routers: `health`, `rules`, `requests`, `decisions`, `audit-log`. Every mutating endpoint is workspace-scoped via the `X-Workspace-Id` header.

---

## 2. Data Model

### Entity Relationship Diagram

```
┌──────────────┐       ┌──────────────────────┐
│  workspaces  │──1:N──│   approval_rules     │
│              │       │                      │
│  id (PK)     │       │  id (PK, UUID)       │
│  name        │       │  workspace_id (FK)   │
│  created_at  │       │  name                │
│              │       │  resource_type       │
│              │       │  conditions (JSONB)  │
│              │       │  steps (JSONB)       │
│              │       │  is_active           │
│              │       │  version (OCC)       │
└──────┬───────┘       └──────────┬───────────┘
       │                          │
       │ 1:N                      │ 1:N
       │                          │
       │       ┌──────────────────┴────────────┐
       └───────│     approval_requests         │
               │                               │
               │  id (PK, UUID)                │
               │  workspace_id (FK)            │
               │  rule_id (FK)                 │
               │  external_resource_id         │
               │  resource_type                │
               │  title, payload (JSONB)       │
               │  status (FSM)                 │
               │  requester_id                 │
               │  resolved_at                  │
               └──────────────┬────────────────┘
                              │ 1:N
                              │
               ┌──────────────┴────────────────┐
               │       approval_steps          │
               │                               │
               │  id (PK, UUID)                │
               │  request_id (FK, CASCADE)     │
               │  workspace_id                 │
               │  step_order                   │
               │  approver_role                │
               │  required_count / current_count│
               │  status (pending/active/...)  │
               │  activated_at, completed_at   │
               └──────────────┬────────────────┘
                              │ 1:N
                              │
               ┌──────────────┴────────────────┐
               │     approval_decisions        │
               │                               │
               │  id (PK, UUID)                │
               │  step_id (FK, CASCADE)        │
               │  workspace_id                 │
               │  actor_id                     │
               │  action (approve/reject)      │
               │  comment                      │
               │  (actor_id, step_id) UNIQUE   │
               └───────────────────────────────┘

               ┌───────────────────────────────┐
               │         audit_log             │
               │                               │
               │  id (PK, BIGSERIAL)           │
               │  workspace_id                 │
               │  entity_type, entity_id       │
               │  action                       │
               │  actor_id (nullable)          │
               │  old_state, new_state (JSONB) │
               │  metadata (JSONB)             │
               │  created_at                   │
               └───────────────────────────────┘

               ┌───────────────────────────────┐
               │           outbox              │
               │                               │
               │  id (PK, BIGSERIAL)           │
               │  event_type                   │
               │  aggregate_type, aggregate_id │
               │  workspace_id                 │
               │  payload (JSONB)              │
               │  published_at (nullable)      │
               │  retry_count                  │
               └───────────────────────────────┘

               ┌───────────────────────────────┐
               │      idempotency_keys         │
               │                               │
               │  id (PK, UUID)                │
               │  key, workspace_id (UNIQUE)   │
               │  method, path                 │
               │  status_code                  │
               │  response_body (JSONB)        │
               │  is_processing                │
               │  expires_at                   │
               └───────────────────────────────┘
```

### Finite State Machine (Request Status)

```
                 ┌───────────┐
        ┌────────│  PENDING  │────────┐
        │        └─────┬─────┘        │
        │ cancel       │ first        │
        │              │ decision     │
        ▼              ▼              │
┌────────────┐  ┌───────────┐         │
│ CANCELLED  │  │ IN_REVIEW │─────────┤
└────────────┘  └─────┬─────┘  cancel │
                      │               │
           ┌──────────┼──────────┐    │
           │ all steps │ any     │    │
           │ approved  │ rejected│    │
           ▼           ▼         ▼    │
     ┌──────────┐ ┌──────────┐ ┌─────┴──────┐
     │ APPROVED │ │ REJECTED │ │ CANCELLED  │
     └──────────┘ └──────────┘ └────────────┘
```

Terminal states (`APPROVED`, `REJECTED`, `CANCELLED`) are immutable. Any attempt to mutate a resolved request returns `409 Conflict`.

### Key Constraints and Indexes

| Constraint | Purpose |
|-----------|---------|
| `ix_approval_requests_unique_active` | Partial unique index on `(workspace_id, external_resource_id, resource_type)` where `status NOT IN ('cancelled')`. Prevents duplicate active requests for the same resource. |
| `uq_approval_decisions_actor_step` | Unique constraint on `(actor_id, step_id)`. Prevents the same actor from voting twice on the same step. |
| `uq_approval_steps_request_order` | Unique constraint on `(request_id, step_order)`. Guarantees step ordering integrity. |
| `ck_approval_requests_status` | Check constraint limiting status to valid FSM states. |
| `version` on `approval_rules` | Optimistic concurrency control. PUT requires the current version; stale updates return `409`. |

---

## 3. Idempotency

### Problem

Network retries, queue redeliveries, and client-side retry logic can cause duplicate POST requests. Without idempotency, this creates duplicate resources or double-processes mutations.

### Strategy

The service implements header-based idempotency for all POST endpoints via `IdempotencyMiddleware`:

```
Client                       Middleware                         Service
  │                              │                                │
  │─── POST + Idempotency-Key ──▶│                                │
  │                              │── pg_advisory_xact_lock(hash) ─▶│
  │                              │── INSERT idempotency_keys ─────▶│
  │                              │                                │
  │                              │────── call_next(request) ──────▶│
  │                              │                                │
  │                              │◀──── response (201) ───────────│
  │                              │── UPDATE response_body ────────▶│
  │◀────── 201 + body ──────────│                                │
  │                              │                                │
  │─── POST + same Key ─────────▶│                                │
  │                              │── SELECT idempotency_keys ─────▶│
  │◀────── 201 (cached) ────────│   (returns stored response)    │
```

### Mechanics

1. **First request:** Middleware acquires a PostgreSQL advisory lock on `hash(key)`, inserts a row with `is_processing=true`, forwards to the handler, then updates the row with `status_code` + `response_body`.
2. **Replay (same key, same path):** Returns the cached response without touching the service layer.
3. **Key conflict (same key, different path):** Returns `422 IDEMPOTENCY_KEY_CONFLICT`.
4. **Concurrent duplicate (same key, still processing):** Returns `409 CONCURRENT_PROCESSING` with `Retry-After: 1`.
5. **Expiry:** Keys have a configurable TTL (default 24h). A cleanup function (`cleanup_expired_keys`) deletes expired rows.

### Scope

Idempotency applies only to POST endpoints. GET, PUT, DELETE are naturally idempotent by HTTP semantics.

---

## 4. Audit Trail

### Design Principles

- **Append-only.** The `audit_log` table has no UPDATE or DELETE operations. Rows are only INSERTed.
- **Same-transaction.** Audit entries are written in the same database transaction as the mutation they record. If the transaction rolls back, the audit entry rolls back too. No orphaned logs, no missing entries.
- **State snapshots.** Each entry stores `old_state` and `new_state` as JSONB, enabling point-in-time reconstruction of entity state.

### What Gets Audited

| Mutation | `entity_type` | `action` | Notes |
|----------|---------------|----------|-------|
| Create rule | `approval_rule` | `created` | `new_state` = rule JSON |
| Update rule | `approval_rule` | `updated` | `old_state` + `new_state` |
| Deactivate rule | `approval_rule` | `deactivated` | `old_state` = last active state |
| Create request | `approval_request` | `created` | `new_state` = request JSON |
| Status change | `approval_request` | `status_changed` | `old_state.status` / `new_state.status` |
| Cancel request | `approval_request` | `cancelled` | Captures cancelling actor |
| Step activated | `approval_step` | `step_activated` | Includes step_order, approver_role |
| Step completed | `approval_step` | `step_completed` | Includes final count |
| Decision made | `approval_decision` | `decision_made` | actor_id, action, comment |

### Querying

```
GET /api/v1/audit-log?entity_type=approval_request&entity_id={id}&limit=50
```

Supports filtering by `entity_type`, `entity_id`, `actor_id` with cursor-based pagination. Indexed on `(workspace_id, entity_type, entity_id, created_at)`.

---

## 5. Events (Transactional Outbox)

### Problem

Publishing events directly to a message broker from the application introduces a dual-write problem: the database commit can succeed while the broker publish fails, or vice versa. This leads to inconsistency.

### Strategy: Transactional Outbox

```
Service Layer                Database                     Publisher (background)
     │                          │                              │
     │── BEGIN TX ──────────────▶│                              │
     │── INSERT request ────────▶│                              │
     │── INSERT audit_log ──────▶│                              │
     │── INSERT outbox ─────────▶│                              │
     │── COMMIT ────────────────▶│                              │
     │                          │                              │
     │                          │◀── SELECT unpublished ───────│
     │                          │── mark published_at ─────────▶│
     │                          │                              │── publish to broker
```

1. Domain events are written to the `outbox` table in the **same transaction** as the business data.
2. A background poller (`OutboxPublisher`) reads unpublished rows, publishes them, and marks `published_at`.
3. Failed publishes increment `retry_count`. After `max_retries` (default 5), rows are dead-lettered (not retried).

### Event Types

| Event | Trigger |
|-------|---------|
| `approval.request.created` | New request created |
| `approval.request.in_review` | First decision triggers review |
| `approval.request.approved` | All steps approved |
| `approval.request.rejected` | Any step rejected |
| `approval.request.cancelled` | Request cancelled |
| `approval.step.activated` | Next step becomes active |
| `approval.decision.made` | Actor submits a decision |

### Publisher Interface

```python
class EventPublisher(abc.ABC):
    @abc.abstractmethod
    async def publish(self, event: DomainEvent) -> None: ...
```

The concrete publisher is injected at startup. The current implementation uses the outbox table; swapping to Kafka, RabbitMQ, or SNS requires only a new `EventPublisher` implementation without changing the service layer.

---

## 6. Tradeoffs and Design Decisions

### Workspace Isolation via Header, Not JWT Claim

**Decision:** `X-Workspace-Id` is a plain UUID header, not extracted from a JWT.

**Rationale:** The service operates behind an API gateway that handles authentication. Coupling to a specific token format (JWT, opaque, session) would reduce portability. The header approach lets any gateway integrate without changes to this service.

**Risk:** If the gateway is misconfigured, a client could pass an arbitrary workspace ID. Mitigation: the gateway must validate workspace membership before forwarding.

### Sequential Step Activation, Not Parallel

**Decision:** Steps execute in order (`step_order`). Step N+1 activates only after step N completes.

**Rationale:** Most approval workflows are inherently sequential (manager then director then CFO). Parallel steps add complexity (merge logic, partial completion semantics) without a current use case.

**Extension point:** The `step_order` and `status` per step allow future parallel activation by activating multiple steps simultaneously.

### Advisory Lock for Idempotency, Not SELECT FOR UPDATE

**Decision:** `pg_advisory_xact_lock(hash(key))` instead of row-level locking.

**Rationale:** Advisory locks work even before the idempotency key row exists (first-time insert). `SELECT FOR UPDATE` requires the row to already exist, leading to a two-phase check-then-insert that is vulnerable to race conditions without an additional mechanism.

**Risk:** Hash collisions in the advisory lock space (2^31) are theoretically possible but statistically negligible for the expected throughput.

### Outbox Over Direct Publish

**Decision:** All events go through the `outbox` table rather than direct broker publish.

**Rationale:** Eliminates the dual-write problem. Event delivery is guaranteed as long as the database transaction commits. The background poller provides at-least-once delivery.

**Cost:** Added latency (poll interval, default 5s). For sub-second event delivery, the poller interval can be reduced or replaced with PostgreSQL `LISTEN/NOTIFY` to wake the poller on new rows.

### Audit in Same Transaction, Not Async

**Decision:** Audit entries are written synchronously in the same transaction as the mutation.

**Rationale:** Guarantees consistency. If the business write succeeds, the audit exists. No need for compensating transactions or reconciliation jobs.

**Cost:** Slightly higher write latency per mutation (one extra INSERT). Acceptable given the append-only, un-indexed-on-write nature of the audit table.

### SQLite for Integration Tests, Not PostgreSQL

**Decision:** Integration tests use SQLite in-memory with compiler shims (JSONB to JSON, BigInteger to INTEGER).

**Rationale:** Tests run in ~8 seconds with zero external dependencies. No Docker, no test database management, no port conflicts in CI. The shims are minimal and confined to the test conftest.

**Risk:** SQLite does not support partial unique indexes (`postgresql_where`), advisory locks, or some PostgreSQL-specific behaviors. These features are tested via service-level error handling that accommodates both dialects.

### Rule `conditions` Stored But Not Evaluated

**Decision:** The `conditions` JSONB field on rules is persisted but never interpreted by the service.

**Rationale:** Condition evaluation logic (e.g. "if amount > 10000 then require CFO") is domain-specific and likely to change. Deferring evaluation to the caller or a future rules engine avoids premature abstraction.

### Soft Delete for Rules

**Decision:** `DELETE /rules/{id}` sets `is_active = false` rather than deleting the row.

**Rationale:** Existing requests reference the rule via foreign key. Hard delete would either cascade (destroying request history) or fail (FK violation). Soft delete preserves referential integrity and audit trail.

### Optimistic Concurrency on Rules, Not Requests

**Decision:** Rules use `version`-based OCC. Requests rely on FSM transitions and unique constraints.

**Rationale:** Rules are collaboratively edited (multiple admins may update the same rule). Requests have a strict FSM that naturally prevents conflicting mutations (e.g. you can't approve an already-rejected request).

### No Pagination Cursors (Offset-Based)

**Decision:** All list endpoints use `offset` + `limit` rather than cursor-based pagination.

**Rationale:** Simpler implementation, familiar API. For the expected data volumes (approval workflows, not high-frequency event streams), offset pagination performs adequately.

**Risk:** Large offsets degrade to sequential scans. If the audit log grows very large, cursor-based pagination (keyset on `created_at` + `id`) should be introduced.
