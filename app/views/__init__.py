from fastapi import APIRouter

from app.views.auth import router as auth
from app.views.convites import router as convites
from app.views.health import router as health
from app.views.termos import router as termos
from app.views.usuarios import router as usuarios

router = APIRouter()

router.include_router(health)
router.include_router(auth)
router.include_router(usuarios)
router.include_router(convites)
router.include_router(termos)
