from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from fastapi import HTTPException

from config.config import OUTPUT_DIR, PERSISTENT_OUTPUT_DIR

logger = logging.getLogger(__name__)


def resolve_safe_download_path(file_path: str, extra_roots: Iterable[str | Path] = ()) -> Path:
    """Resolve a generated-file download while enforcing known output roots."""
    requested = Path(file_path).expanduser().resolve()
    if not requested.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    allowed_roots = [
        Path(PERSISTENT_OUTPUT_DIR),
        Path(OUTPUT_DIR),
        Path(__file__).resolve().parents[3] / "persistent_output",
        *[Path(root) for root in extra_roots],
    ]
    resolved_roots = [root.expanduser().resolve() for root in allowed_roots]

    if any(requested.is_relative_to(root) for root in resolved_roots):
        return requested

    logger.warning("[DOWNLOAD] Blocked unsafe file path: %s", requested)
    raise HTTPException(status_code=403, detail="File path is outside allowed download roots")
