"""Exceptions da central de notificações (BE-S5-04)."""

from fastapi import HTTPException, status


def notificacao_nao_encontrada():
    # 404 (e não 403) também para a notificação de outra pessoa: não revela que ela existe
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notificação não encontrada.")
