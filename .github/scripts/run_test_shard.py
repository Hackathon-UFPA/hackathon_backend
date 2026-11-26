import argparse
from collections import defaultdict

import pytest

# Média por cenário, em milissegundos, estimada pelo progresso do pytest no CI 44942635832.
# O custo por cenário permite que arquivos novos ou ampliados entrem no balanceamento.
MILLISECONDS_PER_TEST = {
    "tests/test_atribuicoes_mentor.py": 680,
    "tests/test_auth.py": 220,
    "tests/test_autodeclaracao.py": 540,
    "tests/test_avaliacao_cientifica.py": 500,
    "tests/test_avaliacao_designacoes.py": 450,
    "tests/test_banco_de_teste.py": 10,
    "tests/test_cadastro_equipe_integrantes.py": 510,
    "tests/test_cadastro_por_hackathon.py": 980,
    "tests/test_cadastro_profissional.py": 180,
    "tests/test_categoria_equipe.py": 10,
    "tests/test_comprovantes.py": 320,
    "tests/test_confirmacao_email_service.py": 10,
    "tests/test_conteudo_institucional.py": 430,
    "tests/test_convites.py": 470,
    "tests/test_criar_usuario.py": 150,
    "tests/test_email_api.py": 100,
    "tests/test_email_envio.py": 140,
    "tests/test_email_eventos.py": 680,
    "tests/test_email_fila.py": 60,
    "tests/test_email_provedores.py": 10,
    "tests/test_email_templates.py": 10,
    "tests/test_envio_proposta.py": 360,
    "tests/test_equipes.py": 280,
    "tests/test_equipes_categoria.py": 470,
    "tests/test_equipes_publicas.py": 860,
    "tests/test_gestao_usuarios.py": 290,
    "tests/test_hackathon.py": 30,
    "tests/test_hackathons_admin.py": 260,
    "tests/test_health.py": 10,
    "tests/test_inscricao.py": 500,
    "tests/test_membros_equipe.py": 470,
    "tests/test_mentores.py": 220,
    "tests/test_migrations.py": 20,
    "tests/test_notificacao_service.py": 10,
    "tests/test_notificacoes.py": 330,
    "tests/test_organizacoes.py": 720,
    "tests/test_perfil_senha.py": 220,
    "tests/test_permissoes.py": 80,
    "tests/test_resultado.py": 800,
    "tests/test_resultado_service.py": 10,
    "tests/test_rubrica.py": 380,
    "tests/test_senha.py": 40,
    "tests/test_somente_leitura.py": 1010,
    "tests/test_submissoes.py": 320,
    "tests/test_temas.py": 520,
    "tests/test_temas_rubricas_comite.py": 530,
    "tests/test_token.py": 10,
    "tests/test_token_usuario.py": 50,
    "tests/test_validacao_links.py": 10,
    "tests/test_validacao_submissao.py": 10,
    "tests/test_versionamento_proposta.py": 640,
}
DEFAULT_MILLISECONDS_PER_TEST = 400
# Esse arquivo é o mais demorado e usa fixtures de função, com dados próprios por cenário.
SPLIT_BY_FUNCTION = {"tests/test_conteudo_institucional.py"}


class TestShard:
    def __init__(self, index: int, count: int):
        self.index = index
        self.count = count

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, config, items):
        test_groups = defaultdict(list)
        for item in items:
            path = item.path.relative_to(config.rootpath).as_posix()
            # Os IDs de parâmetros podem conter UUIDs gerados durante a coleta.
            function = item.originalname if path in SPLIT_BY_FUNCTION else ""
            test_groups[path, function].append(item)

        estimated_times = {
            group: len(tests) * MILLISECONDS_PER_TEST.get(group[0], DEFAULT_MILLISECONDS_PER_TEST)
            for group, tests in test_groups.items()
        }
        shard_times = [0] * self.count
        selected = set()
        for group in sorted(test_groups, key=lambda group: (-estimated_times[group], group)):
            shard = min(range(self.count), key=shard_times.__getitem__)
            shard_times[shard] += estimated_times[group]
            if shard == self.index:
                selected.update(test_groups[group])

        deselected = [item for item in items if item not in selected]
        config.hook.pytest_deselected(items=deselected)
        items[:] = [item for item in items if item in selected]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Executa um grupo de testes do CI.")
    parser.add_argument("shard", type=int)
    parser.add_argument("shard_count", type=int)
    args, pytest_args = parser.parse_known_args()
    if not 1 <= args.shard <= args.shard_count:
        parser.error("O número do grupo deve estar entre 1 e o total de grupos.")

    plugin = TestShard(args.shard - 1, args.shard_count)
    raise SystemExit(pytest.main(pytest_args, plugins=[plugin]))
