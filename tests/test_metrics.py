from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from app.api.metrics import router as metrics_router
from app.bot.health import bot_health
from app.observability.db_metrics_cache import invalidate_db_metrics_cache
from app.observability.prometheus_metrics import (
    DatabasePingCache,
    _fetch_one_c_last_successful_update_timestamp,
    one_c_last_successful_update_timestamp_seconds,
    refresh_database_up_if_needed,
)


@pytest.fixture
def metrics_app() -> FastAPI:
    app = FastAPI()
    app.include_router(metrics_router)
    return app


@pytest.fixture(autouse=True)
def reset_metrics_state() -> None:
    bot_health.runtime_running = False
    bot_health.handlers_registered = False
    one_c_last_successful_update_timestamp_seconds.set(0)
    invalidate_db_metrics_cache()
    yield
    one_c_last_successful_update_timestamp_seconds.set(0)
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
    assert (
        "# HELP one_c_last_successful_update_timestamp_seconds "
        "Unix timestamp of the last successfully processed 1C stock update"
    ) in body
    assert "# TYPE one_c_last_successful_update_timestamp_seconds gauge" in body


@pytest.mark.asyncio
async def test_database_metrics_cache_skips_db_fetch_within_ttl() -> None:
    with (
        patch(
            "app.observability.prometheus_metrics._fetch_database_up",
            new=AsyncMock(
                return_value=DatabasePingCache(
                    database_up=1,
                    fetched_at=time.monotonic(),
                )
            ),
        ) as database_fetch_mock,
        patch(
            "app.observability.prometheus_metrics."
            "_fetch_one_c_last_successful_update_timestamp",
            new=AsyncMock(return_value=1_784_200_000.0),
        ) as one_c_fetch_mock,
    ):
        await refresh_database_up_if_needed()
        await refresh_database_up_if_needed()

    database_fetch_mock.assert_awaited_once()
    one_c_fetch_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_database_snapshot_reads_last_successful_update_timestamp() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = datetime(2026, 7, 16, 13, 0)
    session.execute.return_value = result
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "app.observability.prometheus_metrics.async_session_maker",
        return_value=session_context,
    ):
        timestamp = await _fetch_one_c_last_successful_update_timestamp()

    expected = datetime(2026, 7, 16, 10, 0, tzinfo=timezone.utc).timestamp()
    assert timestamp == expected


@pytest.mark.asyncio
async def test_metrics_returns_last_successful_one_c_update(
    metrics_app: FastAPI,
) -> None:
    timestamp = 1_784_200_000.0
    snapshot = DatabasePingCache(database_up=1, fetched_at=time.monotonic())

    with (
        patch(
            "app.observability.prometheus_metrics._fetch_database_up",
            new=AsyncMock(return_value=snapshot),
        ),
        patch(
            "app.observability.prometheus_metrics."
            "_fetch_one_c_last_successful_update_timestamp",
            new=AsyncMock(return_value=timestamp),
        ),
    ):
        transport = ASGITransport(app=metrics_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/metrics")

    assert response.status_code == 200
    assert "one_c_last_successful_update_timestamp_seconds 1.7842e+09" in response.text


@pytest.mark.asyncio
async def test_metrics_returns_zero_when_one_c_updates_are_missing(
    metrics_app: FastAPI,
) -> None:
    snapshot = DatabasePingCache(database_up=1, fetched_at=time.monotonic())

    with (
        patch(
            "app.observability.prometheus_metrics._fetch_database_up",
            new=AsyncMock(return_value=snapshot),
        ),
        patch(
            "app.observability.prometheus_metrics."
            "_fetch_one_c_last_successful_update_timestamp",
            new=AsyncMock(return_value=0.0),
        ),
    ):
        transport = ASGITransport(app=metrics_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/metrics")

    assert response.status_code == 200
    assert "one_c_last_successful_update_timestamp_seconds 0.0" in response.text


@pytest.mark.asyncio
async def test_database_read_error_does_not_break_metrics_endpoint(
    metrics_app: FastAPI,
) -> None:
    snapshot = DatabasePingCache(database_up=1, fetched_at=time.monotonic())
    with (
        patch(
            "app.observability.prometheus_metrics._fetch_database_up",
            new=AsyncMock(return_value=snapshot),
        ),
        patch(
            "app.observability.prometheus_metrics."
            "_fetch_one_c_last_successful_update_timestamp",
            new=AsyncMock(side_effect=RuntimeError("db read failed")),
        ),
    ):
        transport = ASGITransport(app=metrics_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/metrics")

    assert response.status_code == 200
    assert "database_up 1.0" in response.text
    assert "one_c_last_successful_update_timestamp_seconds 0.0" in response.text


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
