# app/db/dependencies.py
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import async_session_factory
from loguru import logger

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    session: AsyncSession = async_session_factory()
    try:
        yield session
        # optional: commit on success so writes done in endpoints get saved automatically
        await session.commit()
    except Exception:
        # better: include traceback
        logger.exception("[DB] Session rollback due to error")
        await session.rollback()
        raise
    finally:
        await session.close()

        
