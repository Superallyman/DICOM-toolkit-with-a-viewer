from __future__ import annotations

import os
from typing import Protocol

from config.config import BASE_URL


class _RequestLike(Protocol):
    base_url: object


def _clean_url(value: str) -> str:
    return value.rstrip("/")


def public_api_base_url(request: _RequestLike | None = None) -> str:
    """Return the externally reachable API base URL without the /v1 suffix."""
    configured = os.getenv("BASE_URL") or BASE_URL
    if configured:
        return _clean_url(configured)
    if request is not None:
        return _clean_url(str(request.base_url))
    return ""


def public_api_v1_base_url(request: _RequestLike | None = None) -> str:
    return f"{public_api_base_url(request)}/v1"


def public_ohif_base_url(request: _RequestLike | None = None) -> str:
    configured = os.getenv("OHIF_PUBLIC_URL")
    if configured:
        return _clean_url(configured)
    return f"{public_api_v1_base_url(request)}/viewer"
