from __future__ import annotations

import logging

import structlog
from fastapi import FastAPI

from approval_service.api.middleware.error_handler import (
    app_error_handler,
    unhandled_error_handler,
)
from approval_service.api.middleware.logging_ctx import LoggingContextMiddleware
from approval_service.api.v1.routers import audit, decisions, health, requests, rules
from approval_service.config import Settings, get_settings
from approval_service.domain.exceptions import AppError
from approval_service.infrastructure.database.session import (
    create_engine,
    create_session_factory,
)


def configure_logging(settings: Settings) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
    )
    logging.basicConfig(
        level=logging.getLevelName(settings.log_level),
        format="%(message)s",
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = get_settings()

    configure_logging(settings)

    app = FastAPI(
        title="Approval Service",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    app.state.session_factory = session_factory
    app.state.settings = settings

    app.add_middleware(LoggingContextMiddleware)

    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)

    prefix = "/api/v1"
    app.include_router(health.router, prefix=prefix)
    app.include_router(rules.router, prefix=prefix)
    app.include_router(requests.router, prefix=prefix)
    app.include_router(decisions.router, prefix=prefix)
    app.include_router(audit.router, prefix=prefix)

    return app
