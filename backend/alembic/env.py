# alembic/env.py
import os
import pathlib
import importlib.util
from logging.config import fileConfig
from urllib.parse import urlparse, urlunparse

from alembic import context
from sqlalchemy import create_engine, pool

# --- Alembic config / logging
config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

# --- Get DB URL from env (what docker-compose sets)
def _get_db_url() -> str:
    # What your app uses in Docker (async + host=db)
    return os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://dicom_admin:pass123@db:5432/dicomdb",
    )

def _to_sync_driver(url: str) -> str:
    """
    Alembic needs a sync driver. Convert asyncpg DSN to psycopg2 DSN.
    """
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    return url  # already sync (postgresql:// or postgresql+psycopg2://)

def _maybe_override_host(url: str) -> str:
    """
    Keep Docker behavior by default.
    If you're running locally, you can either:
      - define DATABASE_URL_SYNC with a full sync DSN, or
      - define ALEMBIC_DATABASE_URL (full DSN), or
      - define ALEMBIC_HOST_OVERRIDE=localhost to only change the host.
    """
    # Highest priority: full explicit sync URL
    explicit = os.getenv("DATABASE_URL_SYNC") or os.getenv("ALEMBIC_DATABASE_URL")
    if explicit:
        return explicit

    override_host = os.getenv("ALEMBIC_HOST_OVERRIDE")
    if not override_host:
        # If not in a container and host is "db", fall back to localhost automatically.
        # (Docker typically writes /.dockerenv)
        in_container = os.path.exists("/.dockerenv")
        if not in_container:
            parsed = urlparse(url)
            if parsed.hostname == "db":
                override_host = "localhost"

    if not override_host:
        return url  # no change

    parsed = urlparse(url)
    # rebuild netloc with same creds/port but new host
    userinfo = ""
    if parsed.username:
        userinfo = parsed.username
        if parsed.password:
            userinfo += f":{parsed.password}"
        userinfo += "@"

    port = f":{parsed.port}" if parsed.port else ""
    new_netloc = f"{userinfo}{override_host}{port}"
    return urlunparse(parsed._replace(netloc=new_netloc))

RAW_URL = _get_db_url()
SYNC_URL = _maybe_override_host(_to_sync_driver(RAW_URL))

# --- Load models.py directly (avoids importing app settings)
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]  # project root (/app)
MODELS_FILE = REPO_ROOT / "app" / "db" / "models.py"

spec = importlib.util.spec_from_file_location("alembic_models", MODELS_FILE)
models = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(models)
target_metadata = models.Base.metadata  # type: ignore[attr-defined]

def run_migrations_offline() -> None:
    context.configure(
        url=SYNC_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    engine = create_engine(SYNC_URL, poolclass=pool.NullPool, future=True)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
