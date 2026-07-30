from __future__ import annotations

from unittest.mock import patch

import pytest

from app.bot.main import (
    BotHealthMiddleware,
    _register_health_middleware,
    get_bot_runtime,
)


class FakeObserver:
    def __init__(self) -> None:
        self.middleware_calls: list[object] = []

    def middleware(self, middleware: object) -> None:
        self.middleware_calls.append(middleware)


class FakeRouter:
    def __init__(self) -> None:
        self.message = FakeObserver()
        self.callback_query = FakeObserver()


class FakeProxyDispatcher:
    def message(self, *args, **kwargs):
        return lambda handler: handler

    def callback_query(self, *args, **kwargs):
        return lambda handler: handler


@pytest.fixture(autouse=True)
def reset_runtime() -> None:
    import app.bot.main as bot_main

    bot_main._runtime = None
    yield
    bot_main._runtime = None


def test_register_health_middleware_on_router_with_observer_api(caplog: pytest.LogCaptureFixture) -> None:
    router = FakeRouter()

    _register_health_middleware(dp=None, router=router)

    assert len(router.message.middleware_calls) == 1
    assert len(router.callback_query.middleware_calls) == 1
    assert isinstance(router.message.middleware_calls[0], BotHealthMiddleware)
    assert "Health middleware registered on router.message" in caplog.text


def test_register_health_middleware_skips_proxy_dispatcher_without_crash(
    caplog: pytest.LogCaptureFixture,
) -> None:
    dp = FakeProxyDispatcher()

    _register_health_middleware(dp=dp, router=None)

    assert "Health middleware was not registered" in caplog.text
    assert "FakeProxyDispatcher" in caplog.text


def test_register_health_middleware_prefers_router_over_dispatcher() -> None:
    router = FakeRouter()
    dp = FakeProxyDispatcher()

    _register_health_middleware(dp=dp, router=router)

    assert len(router.message.middleware_calls) == 1
    assert len(router.callback_query.middleware_calls) == 1


@pytest.mark.asyncio
async def test_get_bot_runtime_does_not_fail_when_dispatcher_has_no_middleware_api(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_bot = object()
    fake_dp = FakeProxyDispatcher()
    fake_router = FakeRouter()

    with patch("app.bot.main.settings.MAX_TOKEN", "test-token"):
        with patch("app.bot.main.settings.BOT_TOKEN", None):
            with patch("app.bot.main.create_bot", return_value=(fake_bot, fake_dp, fake_router)):
                with patch("app.bot.main.register_warehouse_handlers") as register_mock:
                    runtime = await get_bot_runtime()

    assert runtime.enabled is True
    assert runtime.router is fake_router
    register_mock.assert_called_once_with(fake_router)
    assert "Health middleware registered on router.message" in caplog.text
