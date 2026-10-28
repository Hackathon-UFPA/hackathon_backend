from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import TipoTermo
from app.controllers.equipe import get_hackathon_by_id
from app.controllers.termo import listar_aceites, listar_termos_vigentes, registrar_aceites
from app.exceptions.convite import (
    aceite_incompleto,
    hackathon_nao_encontrado,
    termos_desatualizados,
    termos_nao_publicados,
)
from app.models import AceiteTermo, Termo, Usuario


async def termos_vigentes_do_hackathon(db: AsyncSession, hackathon_id: UUID) -> list[Termo]:
    if await get_hackathon_by_id(db, hackathon_id) is None:
        hackathon_nao_encontrado()
    return await listar_termos_vigentes(db, hackathon_id)


async def validar_termos_aceitos(
    db: AsyncSession, hackathon_id: UUID, termos_ids: list[UUID]
) -> list[UUID]:
    """Confere que a pessoa aceitou exatamente as versões vigentes do regulamento e do termo de
    consentimento (RF20, RN05). Devolve os ids a registrar."""
    vigentes = await listar_termos_vigentes(db, hackathon_id)
    if {termo.tipo for termo in vigentes} != set(TipoTermo):
        termos_nao_publicados()

    ids_vigentes = {termo.id for termo in vigentes}
    enviados = set(termos_ids)
    if not enviados <= ids_vigentes:
        termos_desatualizados()
    if enviados != ids_vigentes:
        aceite_incompleto()
    return list(ids_vigentes)


async def aceitar_termos(
    db: AsyncSession, usuario: Usuario, hackathon_id: UUID, termos_ids: list[UUID]
) -> list[AceiteTermo]:
    if await get_hackathon_by_id(db, hackathon_id) is None:
        hackathon_nao_encontrado()
    ids = await validar_termos_aceitos(db, hackathon_id, termos_ids)
    await registrar_aceites(db, usuario.id, ids)
    await db.commit()
    return await listar_aceites(db, usuario.id, ids)
