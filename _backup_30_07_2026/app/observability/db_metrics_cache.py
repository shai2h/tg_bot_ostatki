"""Shared DB metrics cache invalidation for Prometheus gauges.

Kept separate from prometheus_metrics to avoid import cycles with business
services (e.g. ostatki_sync) that need to invalidate cache after writes.
"""

from __future__ import annotations

from typing import Any

_db_cache: Any = None


def get_db_metrics_cache() -> Any:
    return _db_cache


def set_db_metrics_cache(snapshot: Any) -> None:
    global _db_cache
    _db_cache = snapshot


def invalidate_db_metrics_cache() -> None:
    """Reset cached DB snapshot so the next scrape refreshes gauges."""
    global _db_cache
    _db_cache = None
