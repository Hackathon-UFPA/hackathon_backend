from fastapi import APIRouter

from app.views.health import router as health

router = APIRouter()

router.include_router(health)
