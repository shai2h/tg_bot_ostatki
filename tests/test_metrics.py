from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from app.api.metrics import router as metrics_router
from app.bot.health import bot_health
from app.observability.db_metrics_cache import invalidate_db_metrics_cache, set_db_metrics_cache
from app.observability.prometheus_metrics import DatabasePingCache, refresh_database_up_if_needed


@pytest.fixture
def metrics_app() -> FastAPI:
    app = FastAPI()
    app.include_router(metrics_router)
    return app


@pytest.fixture(autouse=True)
def reset_metrics_state() -> None:
    bot_health.runtime_running = False
    bot_health.handlers_registered = False
    invalidate_db_metrics_cache()
    yield
    invalidate_db_metrics_cache()


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_format(metrics_app: FastAPI) -> None:
    bot_health.mark_runtime_started("polling", handlers_registered=True)

    with patch(
        "app.observability.prometheus_metrics.refresh_database_up_if_needed",
        new=AsyncMock(),
    ):
        transport = ASGITransport(app=metrics_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    body = response.text
    assert "# HELP bot_up" in body
    assert "# TYPE bot_up gauge" in body
    assert "bot_up 1.0" in body
    assert "# HELP database_up" in body
    assert "# TYPE database_up gauge" in body
    assert "database_up" in body


@pytest.mark.asyncio
async def test_database_up_cache_skips_ping_within_ttl() -> None:
    set_db_metrics_cache(DatabasePingCache(database_up=1, fetched_at=time.monotonic()))

    with patch(
        "app.observability.prometheus_metrics._fetch_database_up",
        new=AsyncMock(),
    ) as fetch_mock:
        await refresh_database_up_if_needed()
        await refresh_database_up_if_needed()

    fetch_mock.assert_not_called()


def test_bot_up_uses_runtime_running_only() -> None:
    import asyncio

    from app.observability.prometheus_metrics import _apply_bot_up, bot_up

    bot_health.runtime_running = True
    bot_health.handlers_registered = False
    _apply_bot_up()
    assert bot_up._value.get() == 1.0

    bot_health.runtime_running = False
    _apply_bot_up()
    assert bot_up._value.get() == 0.0
