import argparse
from collections import defaultdict

import pytest

# Média por cenário, em milissegundos, estimada pelo progresso de duas execuções do CI.
# O custo por cenário permite que arquivos novos ou ampliados entrem no balanceamento.
MILLISECONDS_PER_TEST = {
    "tests/test_atribuicoes_mentor.py": 800,
    "tests/test_auth.py": 190,
    "tests/test_autodeclaracao.py": 650,
    "tests/test_avaliacao_cientifica.py": 490,
    "tests/test_avaliacao_designacoes.py": 420,
    "tests/test_banco_de_teste.py": 10,
    "tests/test_cadastro_equipe_integrantes.py": 490,
    "tests/test_cadastro_por_hackathon.py": 940,
    "tests/test_cadastro_profissional.py": 170,
    "tests/test_categoria_equipe.py": 10,
    "tests/test_comprovantes.py": 370,
    "tests/test_conteudo_institucional.py": 390,
    "tests/test_convites.py": 440,
    "tests/test_criar_usuario.py": 140,
    "tests/test_email_api.py": 120,
    "tests/test_email_envio.py": 150,
    "tests/test_email_eventos.py": 690,
    "tests/test_email_fila.py": 60,
    "tests/test_email_provedores.py": 10,
    "tests/test_email_templates.py": 10,
    "tests/test_envio_proposta.py": 370,
    "tests/test_equipes.py": 270,
    "tests/test_equipes_categoria.py": 460,
    "tests/test_equipes_publicas.py": 830,
    "tests/test_gestao_usuarios.py": 260,
    "tests/test_hackathon.py": 30,
    "tests/test_hackathons_admin.py": 260,
    "tests/test_health.py": 10,
    "tests/test_inscricao.py": 610,
    "tests/test_membros_equipe.py": 490,
    "tests/test_mentores.py": 270,
    "tests/test_migrations.py": 20,
    "tests/test_notificacoes.py": 390,
    "tests/test_organizacoes.py": 680,
    "tests/test_perfil_senha.py": 250,
    "tests/test_permissoes.py": 100,
    "tests/test_resultado.py": 870,
    "tests/test_rubrica.py": 380,
    "tests/test_senha.py": 40,
    "tests/test_somente_leitura.py": 1070,
    "tests/test_submissoes.py": 400,
    "tests/test_temas.py": 630,
    "tests/test_temas_rubricas_comite.py": 520,
    "tests/test_token.py": 10,
    "tests/test_versionamento_proposta.py": 640,
}
DEFAULT_MILLISECONDS_PER_TEST = 400


class TestShard:
    def __init__(self, index: int, count: int):
        self.index = index
        self.count = count

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, config, items):
        modules = defaultdict(list)
        for item in items:
            path = item.path.relative_to(config.rootpath).as_posix()
            modules[path].append(item)

        estimated_times = {
            path: len(tests) * MILLISECONDS_PER_TEST.get(path, DEFAULT_MILLISECONDS_PER_TEST)
            for path, tests in modules.items()
        }
        shard_times = [0] * self.count
        selected = set()
        # Mantém cada arquivo inteiro e coloca o próximo mais lento no grupo com menor custo.
        for path in sorted(modules, key=lambda path: (-estimated_times[path], path)):
            shard = min(range(self.count), key=shard_times.__getitem__)
            shard_times[shard] += estimated_times[path]
            if shard == self.index:
                selected.update(modules[path])

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
