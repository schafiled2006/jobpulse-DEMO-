"""Rate limiting configuration for the API using slowapi."""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

# Default limiter tracking client IP address
limiter: Limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    headers_enabled=False,
)
