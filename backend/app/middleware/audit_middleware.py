"""
HTTP-level request logging middleware.

Logs every incoming request (method, path, status, duration) to Python's
logging system. This is infrastructure-level logging — semantic audit logs
(who changed what) are written per-endpoint in each router.
"""
import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("audit.http")


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        # Skip health-check noise in logs
        if request.url.path != "/health":
            logger.info(
                "%s %s → %d  (%.1fms)",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )

        return response
