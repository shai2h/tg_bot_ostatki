from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from app.api.metrics import router as metrics_router
from app.bot.health import bot_health
from app.observability import prometheus_metrics as pm


@pytest.fixture
def metrics_app() -> FastAPI:
    app = FastAPI()
    app.include_router(metrics_router)
    return app


@pytest.fixture(autouse=True)
def reset_metrics_state() -> None:
    bot_health.runtime_running = False
    bot_health.handlers_registered = False
    pm.invalidate_db_metrics_cache()
    yield
    pm.invalidate_db_metrics_cache()


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_format(metrics_app: FastAPI) -> None:
    bot_health.mark_runtime_started("polling", handlers_registered=True)

    with patch(
        "app.observability.prometheus_metrics.refresh_db_metrics_if_needed",
        new=AsyncMock(),
    ):
        transport = ASGITransport(app=metrics_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    body = response.text
    assert "bot_up" in body
    assert "database_up" in body
    assert "user_queries_total" in body
    assert "bot_answers_total" in body


@pytest.mark.asyncio
async def test_db_metrics_cache_skips_refetch_within_ttl() -> None:
    pm._db_cache = pm.DbMetricsSnapshot(
        database_up=1,
        one_c_last_update_timestamp=1_700_000_000.0,
        one_c_seconds_since_last_update=100.0,
        warehouse_stock_rows=42,
        fetched_at=time.monotonic(),
    )

    with patch(
        "app.observability.prometheus_metrics._fetch_db_snapshot",
        new=AsyncMock(),
    ) as fetch_mock:
        await pm.refresh_db_metrics_if_needed()
        await pm.refresh_db_metrics_if_needed()

    fetch_mock.assert_not_called()
    assert pm.warehouse_stock_rows._value.get() == 42.0


def test_record_user_query_increments_counter() -> None:
    before = pm.user_queries_total._value.get()
    pm.record_user_query()
    assert pm.user_queries_total._value.get() == before + 1


def test_record_bot_answer_increments_counter() -> None:
    before = pm.bot_answers_total._value.get()
    pm.record_bot_answer()
    assert pm.bot_answers_total._value.get() == before + 1
