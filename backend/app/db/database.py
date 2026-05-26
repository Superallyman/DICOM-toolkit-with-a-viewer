# app/db/database.py

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from config.database_config import settings  # your DB URL config

engine = create_async_engine(settings.database_url, echo=False, future=True)

# Used with `async with SessionLocal()`
async_session_factory = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Alias for backwards compatibility
SessionLocal = async_session_factory
