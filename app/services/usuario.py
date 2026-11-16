import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from app.const.enums import FinalidadeToken, PapelUsuario
from app.controllers.token_usuario import invalidar_tokens
from app.controllers.usuario import (
    contar_organizadores_ativos,
    criar_usuario,
    get_usuario,
    listar_usuarios,
    serializar_gestao_de_usuarios,
)
from app.exceptions.auth import (
    acesso_negado,
    gestao_de_mentor_em_rota_propria,
    operacao_sobre_si_mesmo,
    troca_de_papel_nao_permitida,
    ultimo_organizador,
    usuario_nao_encontrado,
)
from app.models import Usuario
from app.schemas.auth import UsuarioAdminCreate
from app.schemas.perfil import UsuarioAdminUpdate
from app.security.permissoes import (
    perfis_cadastraveis,
    pode_cadastrar,
    pode_gerenciar,
    pode_trocar_papel,
)
from app.security.senha import gerar_hash


async def cadastrar_usuario_por_perfil(
    db: AsyncSession, quem_cadastra: Usuario, dados: UsuarioAdminCreate
) -> Usuario:
    """RF07/RF08: demais perfis ativos; mentores seguem obrigatoriamente a RN33."""
    if not pode_cadastrar(quem_cadastra.papel, dados.papel):
        acesso_negado()

    if dados.papel == PapelUsuario.MENTOR:
        from app.schemas.mentor import MentorCreate
        from app.services.mentor import cadastrar

        return await cadastrar(
            db,
            MentorCreate.model_validate(
                dados.model_dump(
                    include={
                        "nome",
                        "email",
                        "empresa_parceira",
                        "area_atuacao",
                        "max_equipes",
                        "hackathon_id",
                    }
                )
            ),
        )

    usuario = await criar_usuario(
        db,
        Usuario(
            **dados.model_dump(exclude={"senha", "email", "hackathon_id"}),
            email=dados.email.lower(),
            senha_hash=await asyncio.to_thread(gerar_hash, dados.senha),
        ),
    )
    await db.commit()
    return usuario


# --- Gestão administrativa (RN24, BE-S5-07) ---


async def _alvo_da_gestao(
    db: AsyncSession, quem_gerencia: Usuario, usuario_id: UUID, *, bloquear: bool = False
) -> Usuario:
    """O usuário a gerenciar, se `quem_gerencia` tem alcance sobre o perfil dele (RN24)."""
    alvo = await get_usuario(db, usuario_id, bloquear=bloquear)
    if alvo is None:
        usuario_nao_encontrado()
    if not pode_gerenciar(quem_gerencia.papel, alvo.papel):
        acesso_negado()
    return alvo


async def listar(
    db: AsyncSession,
    quem_gerencia: Usuario,
    *,
    papel: PapelUsuario | None,
    ativo: bool | None,
    busca: str | None,
    limite: int,
    deslocamento: int,
) -> list[Usuario]:
    """Só aparecem os perfis que `quem_gerencia` pode gerenciar. Se pedir um perfil fora do
    alcance, a resposta é uma lista vazia, e não um erro que confirme a existência."""
    return await listar_usuarios(
        db,
        perfis_cadastraveis(quem_gerencia.papel),
        papel=papel,
        ativo=ativo,
        busca=busca.strip() if busca else None,
        limite=limite,
        deslocamento=deslocamento,
    )


async def consultar(db: AsyncSession, quem_gerencia: Usuario, usuario_id: UUID) -> Usuario:
    return await _alvo_da_gestao(db, quem_gerencia, usuario_id)


async def atualizar(
    db: AsyncSession, quem_gerencia: Usuario, usuario_id: UUID, dados: UsuarioAdminUpdate
) -> Usuario:
    await serializar_gestao_de_usuarios(db)
    alvo = await _alvo_da_gestao(db, quem_gerencia, usuario_id, bloquear=True)
    if alvo.papel == PapelUsuario.MENTOR:
        gestao_de_mentor_em_rota_propria()

    valores = dados.model_dump(exclude_unset=True)
    novo_papel = valores.pop("papel", None)
    if novo_papel is not None and novo_papel != alvo.papel:
        if alvo.id == quem_gerencia.id:
            operacao_sobre_si_mesmo()
        if not pode_gerenciar(quem_gerencia.papel, novo_papel):
            # Escalada de privilégio: ninguém entrega a uma conta um perfil acima do seu alcance
            acesso_negado()
        if not pode_trocar_papel(quem_gerencia.papel, alvo.papel, novo_papel):
            troca_de_papel_nao_permitida()
        if (
            alvo.papel == PapelUsuario.ORGANIZADOR
            and alvo.ativo
            and await contar_organizadores_ativos(db) <= 1
        ):
            ultimo_organizador()
        alvo.papel = novo_papel

    for campo, valor in valores.items():
        setattr(alvo, campo, valor)
    alvo.atualizado_em = datetime.now(UTC)
    db.add(alvo)
    await db.commit()
    return alvo


async def desativar(db: AsyncSession, quem_gerencia: Usuario, usuario_id: UUID) -> Usuario:
    """Bloqueia o acesso na hora (o token passa a dar 401), encerra as sessões e gasta os links
    pendentes de redefinição e de confirmação. O histórico da conta fica preservado."""
    await serializar_gestao_de_usuarios(db)
    alvo = await _alvo_da_gestao(db, quem_gerencia, usuario_id, bloquear=True)
    if alvo.id == quem_gerencia.id:
        operacao_sobre_si_mesmo()
    if alvo.papel == PapelUsuario.MENTOR:
        gestao_de_mentor_em_rota_propria()
    if not alvo.ativo:
        return alvo
    if alvo.papel == PapelUsuario.ORGANIZADOR and await contar_organizadores_ativos(db) <= 1:
        ultimo_organizador()
    agora = datetime.now(UTC)
    alvo.ativo = False
    alvo.versao_sessao += 1
    alvo.atualizado_em = agora
    db.add(alvo)
    for finalidade in FinalidadeToken:
        await invalidar_tokens(db, alvo.id, finalidade, agora)
    await db.commit()
    return alvo


async def reativar(db: AsyncSession, quem_gerencia: Usuario, usuario_id: UUID) -> Usuario:
    await serializar_gestao_de_usuarios(db)
    alvo = await _alvo_da_gestao(db, quem_gerencia, usuario_id, bloquear=True)
    if alvo.papel == PapelUsuario.MENTOR:
        gestao_de_mentor_em_rota_propria()
    if alvo.ativo:
        return alvo
    alvo.ativo = True
    alvo.atualizado_em = datetime.now(UTC)
    db.add(alvo)
    await db.commit()
    return alvo
