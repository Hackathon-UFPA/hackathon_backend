from fastapi import APIRouter

from app.views.auth import router as auth
from app.views.health import router as health

router = APIRouter()

router.include_router(health)
router.include_router(auth)
