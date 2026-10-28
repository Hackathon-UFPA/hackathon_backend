from fastapi import APIRouter

from app.views.auth import router as auth
from app.views.convites import router as convites
from app.views.equipe import router as equipes
from app.views.health import router as health
from app.views.membro_equipe import router as membros_equipe
from app.views.termos import router as termos
from app.views.usuarios import router as usuarios

router = APIRouter()

router.include_router(health)
router.include_router(auth)
router.include_router(usuarios)
router.include_router(equipes)
router.include_router(membros_equipe)
router.include_router(convites)
router.include_router(termos)
