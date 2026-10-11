import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import tags
from app.const.config import settings
from app.logging_config import setup_logging
from app.utils.lifespan import lifespan
from app.views import router

setup_logging()

logger = logging.getLogger("main")

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    root_path=settings.BASEPATH,
    lifespan=lifespan,
    openapi_tags=tags,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
