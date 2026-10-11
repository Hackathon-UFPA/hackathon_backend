from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.config import settings

async_engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)

async_session = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


# Gerador de sessão assíncrona, usado nas rotas com Depends(get_session)
async def get_session() -> AsyncGenerator[AsyncSession]:
    async with async_session() as session:
        yield session
