from __future__ import annotations

from fastapi import APIRouter
from starlette.responses import Response

from app.observability.prometheus_metrics import (
    collect_metrics_for_scrape,
    export_prometheus_metrics,
)

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def prometheus_metrics() -> Response:
    await collect_metrics_for_scrape()
    body, content_type = export_prometheus_metrics()
    return Response(content=body, media_type=content_type)
