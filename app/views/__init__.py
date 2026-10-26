from fastapi import APIRouter

from app.views.auth import router as auth
from app.views.health import router as health
from app.views.usuarios import router as usuarios

router = APIRouter()

router.include_router(health)
router.include_router(auth)
router.include_router(usuarios)
