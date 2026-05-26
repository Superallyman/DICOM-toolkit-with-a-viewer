# Import shared constants and configuration from `config.py`
from config.config import (
    RATE_LIMIT,
    AUTH_USERNAME,
    AUTH_PASSWORD,
    SUPPORTED_FORMATS,
    BASE_UID_PREFIX,
    general_config, 
    CLIENT_CREDENTIALS,
)

# Expose shared constants and configurations
__all__ = [
    "RATE_LIMIT",
    "AUTH_USERNAME",
    "AUTH_PASSWORD",
    "SUPPORTED_FORMATS",
    "BASE_UID_PREFIX",
    "general_config",
    "CLIENT_CREDENTIALS",
    "resolve_uid_hash",
]
