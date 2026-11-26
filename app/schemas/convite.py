from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.const.enums import StatusConvite, TipoIntegrante


# O líder informa só nome e e-mail; o resto a pessoa completa ao confirmar (RF18, RV20)
class ConviteCreate(BaseModel):
    equipe_id: UUID
    convidado_por: UUID
    nome: str = Field(max_length=255, examples=["Maria Souza"])
    email: EmailStr = Field(examples=["maria@example.com"])


class ConviteUpdate(BaseModel):
    status: StatusConvite


# Sem o token: ele só vai no link do e-mail
class ConviteResponse(ConviteCreate):
    id: UUID
    usuario_id: UUID | None = None
    tipo_integrante: TipoIntegrante
    status: StatusConvite
    enviado_em: datetime | None = None
    respondido_em: datetime | None = None
    # BE-S5-06: quantas vezes o aviso foi renovado e quando o líder pode reenviar de novo.
    # `proximo_reenvio_em` considera só o intervalo mínimo e é nulo quando o limite se esgotou
    # (ou o convite já não está pendente); uma data passada significa que já pode reenviar
    reenvios: int = 0
    proximo_reenvio_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# O que o líder envia: a equipe vem da rota e quem convida, do token
class ConviteEnvio(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    nome: str = Field(min_length=1, max_length=255, examples=["Maria Souza"])
    email: EmailStr = Field(examples=["maria@example.com"])
    tipo_integrante: TipoIntegrante | None = Field(
        default=None,
        description=(
            "Indicado pelo líder (BE-S5-01). Omitido, vale o tipo da categoria da equipe; "
            "obrigatório na categoria MISTA"
        ),
    )


# Correção de um convite pendente (BE-S5-06): nome e/ou e-mail. Trocar o e-mail invalida o link
# anterior e envia um novo ao endereço corrigido
class ConviteCorrecao(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    nome: str | None = Field(default=None, min_length=1, max_length=255, examples=["Maria Souza"])
    email: EmailStr | None = Field(default=None, examples=["maria@example.com"])

    @model_validator(mode="after")
    def exigir_algum_campo(self):
        if self.nome is None and self.email is None:
            raise ValueError("Informe o nome e/ou o e-mail a corrigir.")
        return self


# Ids das versões de termo que a pessoa leu e aceita (GET /hackathons/{id}/termos/vigentes)
class ConviteAceite(BaseModel):
    termos_ids: list[UUID] = Field(
        min_length=1,
        examples=[["3fa85f64-5717-4562-b3fc-2c963f66afa6", "7c9e6679-7425-40de-944b-e07fc1f90ae7"]],
    )


# Convite visto por quem recebe (RF19: aparece no painel)
class ConviteRecebidoResponse(BaseModel):
    id: UUID
    equipe_id: UUID
    equipe_nome: str | None = None
    hackathon_id: UUID
    nome: str
    status: StatusConvite
    enviado_em: datetime | None = None
