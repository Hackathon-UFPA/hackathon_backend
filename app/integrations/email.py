"""Ponto de extensão para o envio de e-mail (RF33).

Ainda não existe infraestrutura de e-mail: o canal definitivo das notificações depende da
decisão Q16 (plataforma, e-mail ou ambos). Quando for decidida, implemente aqui o envio e
chame esta função a partir de `app.services.notificacao`, registrando o resultado em
`notificacoes_resultado.status_envio` (ENVIADO ou FALHA com `erro`). Nada chama esta função hoje.
"""


async def enviar_email(destinatario: str, assunto: str, corpo: str) -> None:
    raise NotImplementedError("Envio de e-mail pendente da decisão Q16.")
