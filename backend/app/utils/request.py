"""Shared request utilities."""
from starlette.requests import Request


def get_real_ip(request: Request) -> str:
    """Extract real client IP, handling Cloudflare tunnel headers."""
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
