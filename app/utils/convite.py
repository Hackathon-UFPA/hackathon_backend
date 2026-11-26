from uuid import UUID


def chave_do_envio(convite_id: UUID, envio: int) -> str:
    """Chave de idempotência do aviso de um convite (e-mail e central). O primeiro envio mantém
    a chave original `convite:{id}`; cada reenvio ou troca de e-mail ganha a sua
    (`convite:{id}:envio:{n}`), senão a fila ignoraria o aviso novo como repetido."""
    return f"convite:{convite_id}" if envio == 0 else f"convite:{convite_id}:envio:{envio}"
