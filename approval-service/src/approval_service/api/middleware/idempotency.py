from __future__ import annotations

import datetime
import json
import logging
from typing import Any
from uuid import UUID

from fastapi import Request, Response
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from approval_service.infrastructure.database.models.idempotency_key import IdempotencyKeyModel

logger = logging.getLogger(__name__)


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Ensures POST idempotency via Idempotency-Key header.

    First request: acquires advisory lock, stores key with is_processing=True,
    forwards to handler, then caches the response.
    Replay: returns cached response without touching the service layer.
    On handler failure: cleans up the key so the client can safely retry.
    """

    def __init__(
        self,
        app: Any,
        session_factory: async_sessionmaker[AsyncSession],
        ttl_hours: int = 24,
    ) -> None:
        super().__init__(app)
        self._session_factory = session_factory
        self._ttl_hours = ttl_hours

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method != "POST":
            return await call_next(request)

        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return await call_next(request)

        workspace_header = request.headers.get("X-Workspace-Id")
        if not workspace_header:
            return await call_next(request)

        try:
            workspace_id = UUID(workspace_header)
        except ValueError:
            return await call_next(request)

        method = request.method
        path = request.url.path

        async with self._session_factory() as session, session.begin():
            existing = await self._get_existing_key(session, idempotency_key, workspace_id)

            if existing is not None:
                if existing.is_processing:
                    return JSONResponse(
                        status_code=409,
                        content={
                            "error": {
                                "code": "CONCURRENT_PROCESSING",
                                "message": "This request is currently being processed.",
                                "details": {},
                            },
                            "meta": {
                                "request_id": getattr(request.state, "correlation_id", ""),
                                "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                            },
                        },
                        headers={"Retry-After": "1"},
                    )

                if existing.method != method or existing.path != path:
                    return JSONResponse(
                        status_code=422,
                        content={
                            "error": {
                                "code": "IDEMPOTENCY_KEY_CONFLICT",
                                "message": "Idempotency key was used for a different request.",
                                "details": {},
                            },
                            "meta": {
                                "request_id": getattr(request.state, "correlation_id", ""),
                                "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                            },
                        },
                    )

                if existing.response_body is not None:
                    return JSONResponse(
                        status_code=existing.status_code,
                        content=existing.response_body,
                    )

            await self._acquire_advisory_lock(session, idempotency_key)

            now = datetime.datetime.now(datetime.UTC)
            key_model = IdempotencyKeyModel(
                key=idempotency_key,
                workspace_id=workspace_id,
                method=method,
                path=path,
                status_code=0,
                response_body=None,
                is_processing=True,
                expires_at=now + datetime.timedelta(hours=self._ttl_hours),
            )
            session.add(key_model)

        try:
            response = await call_next(request)
        except Exception:
            await self._cleanup_processing_key(idempotency_key, workspace_id)
            raise

        response_body = b""
        async for chunk in response.body_iterator:  # type: ignore[attr-defined]
            if isinstance(chunk, str):
                response_body += chunk.encode()
            else:
                response_body += chunk

        if response.status_code >= 500:
            await self._cleanup_processing_key(idempotency_key, workspace_id)
            return Response(
                content=response_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        try:
            parsed_body: dict[str, Any] = json.loads(response_body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            parsed_body = {}

        async with self._session_factory() as session, session.begin():
            stmt = select(IdempotencyKeyModel).where(
                IdempotencyKeyModel.key == idempotency_key,
                IdempotencyKeyModel.workspace_id == workspace_id,
            )
            result = await session.execute(stmt)
            key_record = result.scalar_one_or_none()
            if key_record is not None:
                key_record.status_code = response.status_code
                key_record.response_body = parsed_body
                key_record.is_processing = False

        return Response(
            content=response_body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )

    async def _cleanup_processing_key(
        self, idempotency_key: str, workspace_id: UUID
    ) -> None:
        """Remove a key stuck in is_processing=True after a handler failure."""
        try:
            async with self._session_factory() as session, session.begin():
                stmt = delete(IdempotencyKeyModel).where(
                    IdempotencyKeyModel.key == idempotency_key,
                    IdempotencyKeyModel.workspace_id == workspace_id,
                    IdempotencyKeyModel.is_processing.is_(True),
                )
                await session.execute(stmt)
        except Exception:
            logger.exception(
                "Failed to clean up idempotency key after handler error",
                extra={"idempotency_key": idempotency_key},
            )

    async def _get_existing_key(
        self,
        session: AsyncSession,
        key: str,
        workspace_id: UUID,
    ) -> IdempotencyKeyModel | None:
        stmt = select(IdempotencyKeyModel).where(
            IdempotencyKeyModel.key == key,
            IdempotencyKeyModel.workspace_id == workspace_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _acquire_advisory_lock(self, session: AsyncSession, key: str) -> None:
        lock_id = hash(key) % (2**31)
        await session.execute(text(f"SELECT pg_advisory_xact_lock({lock_id})"))


async def cleanup_expired_keys(
    session_factory: async_sessionmaker[AsyncSession],
) -> int:
    async with session_factory() as session, session.begin():
        now = datetime.datetime.now(datetime.UTC)
        stmt = delete(IdempotencyKeyModel).where(IdempotencyKeyModel.expires_at < now)
        result = await session.execute(stmt)
        return result.rowcount  # type: ignore[return-value]
