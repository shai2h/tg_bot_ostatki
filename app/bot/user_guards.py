from __future__ import annotations

import logging
import random
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class _UserGuardState:
    search_busy: bool = False
    last_request_at: float = 0.0
    recent_requests: deque[float] = field(default_factory=deque)
    successful_searches: int = 0
    promo_every: int = field(default_factory=lambda: random.randint(5, 10))
    last_start_at: float = 0.0


class UserInteractionGuard:
    """In-memory soft limits, promo counters and inbound dedupe."""

    def __init__(
        self,
        *,
        min_interval_seconds: float = 2.0,
        max_requests_per_minute: int = 10,
        start_debounce_seconds: float = 3.0,
        message_dedupe_ttl_seconds: float = 120.0,
    ) -> None:
        self.min_interval_seconds = min_interval_seconds
        self.max_requests_per_minute = max_requests_per_minute
        self.start_debounce_seconds = start_debounce_seconds
        self.message_dedupe_ttl_seconds = message_dedupe_ttl_seconds
        self._users: dict[int, _UserGuardState] = defaultdict(_UserGuardState)
        self._seen_messages: dict[str, float] = {}
        self._seen_callbacks: dict[str, float] = {}

    def _state(self, user_id: int) -> _UserGuardState:
        return self._users[user_id]

    def _purge_seen(self, store: dict[str, float], now: float) -> None:
        ttl = self.message_dedupe_ttl_seconds
        expired = [key for key, ts in store.items() if now - ts > ttl]
        for key in expired:
            del store[key]

    def should_skip_duplicate_start(self, user_id: int) -> bool:
        state = self._state(user_id)
        now = time.monotonic()
        if state.last_start_at and (now - state.last_start_at) < self.start_debounce_seconds:
            return True
        state.last_start_at = now
        return False

    def should_skip_duplicate_message(self, message_key: str | None) -> bool:
        if not message_key:
            return False
        now = time.monotonic()
        self._purge_seen(self._seen_messages, now)
        if message_key in self._seen_messages:
            return True
        self._seen_messages[message_key] = now
        return False

    def should_skip_duplicate_callback(self, callback_key: str | None) -> bool:
        if not callback_key:
            return False
        now = time.monotonic()
        self._purge_seen(self._seen_callbacks, now)
        if callback_key in self._seen_callbacks:
            return True
        self._seen_callbacks[callback_key] = now
        return False

    def begin_search(self, user_id: int) -> str | None:
        """Return user-facing block reason or None if search may start."""
        state = self._state(user_id)
        now = time.monotonic()

        if state.search_busy:
            return "⏳ Выполняется предыдущий поиск. Пожалуйста, дождитесь результата."

        if state.last_request_at and (now - state.last_request_at) < self.min_interval_seconds:
            return "⏳ Подождите пару секунд перед следующим запросом."

        cutoff = now - 60.0
        while state.recent_requests and state.recent_requests[0] < cutoff:
            state.recent_requests.popleft()
        if len(state.recent_requests) >= self.max_requests_per_minute:
            return "⏳ Слишком много запросов. Подождите немного и попробуйте снова."

        state.search_busy = True
        state.last_request_at = now
        state.recent_requests.append(now)
        return None

    def end_search(self, user_id: int, *, success: bool = False) -> bool:
        """Finish search. Returns True when dealer promo should be shown."""
        state = self._state(user_id)
        state.search_busy = False
        if not success:
            return False
        state.successful_searches += 1
        if state.successful_searches < state.promo_every:
            return False
        state.successful_searches = 0
        state.promo_every = random.randint(5, 10)
        return True


def resolve_message_bot(message: Any) -> Any | None:
    return getattr(message, "_bot", None) or getattr(message, "bot", None)


def is_message_from_bot(message: Any) -> bool:
    """Return True for bot-authored inbound updates that must not enter search/UI handlers.

    maxbot Message.from_raw() does not populate User.is_bot, so we also compare
    sender id with bot.id from get_me() when available.
    """
    user = getattr(message, "from_user", None) or getattr(message, "sender", None)
    if user is not None and bool(getattr(user, "is_bot", False)):
        return True

    bot = resolve_message_bot(message)
    bot_id = getattr(bot, "id", None) if bot is not None else None
    user_id = getattr(user, "id", None) if user is not None else None
    if user_id is None:
        user_id = getattr(user, "user_id", None) if user is not None else None

    if bot_id is None or user_id is None:
        return False
    try:
        return int(bot_id) == int(user_id)
    except (TypeError, ValueError):
        return False


def inbound_message_key(message: Any) -> str | None:
    message_id = (
        getattr(message, "message_id", None)
        or getattr(message, "id", None)
        or getattr(message, "mid", None)
    )
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None) if chat is not None else None
    if message_id is None:
        return None
    return f"{chat_id}:{message_id}"


def inbound_callback_key(callback: Any) -> str | None:
    callback_id = (
        getattr(callback, "callback_id", None)
        or getattr(callback, "id", None)
        or getattr(callback, "update_id", None)
    )
    if callback_id is None:
        data = getattr(callback, "data", None) or getattr(callback, "payload", None)
        user = getattr(callback, "from_user", None) or getattr(callback, "user", None)
        user_id = getattr(user, "id", None) if user is not None else None
        if data is None or user_id is None:
            return None
        return f"{user_id}:{data}"
    return str(callback_id)


user_guards = UserInteractionGuard()
