from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.health import router as health_router
from fastapi import FastAPI


@pytest.fixture
def health_app() -> FastAPI:
    app = FastAPI()
    app.include_router(health_router)
    return app


@pytest.mark.asyncio
async def test_health_live_returns_200(health_app: FastAPI) -> None:
    transport = ASGITransport(app=health_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_ready_returns_200_when_database_available(health_app: FastAPI) -> None:
    with patch("app.api.health.ping_database", new=AsyncMock()) as ping_mock:
        transport = ASGITransport(app=health_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    ping_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_health_ready_returns_503_when_database_unavailable(health_app: FastAPI) -> None:
    with patch(
        "app.api.health.ping_database",
        new=AsyncMock(side_effect=RuntimeError("db down")),
    ):
        transport = ASGITransport(app=health_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "unavailable"}
