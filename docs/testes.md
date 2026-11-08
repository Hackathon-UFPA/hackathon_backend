# Mapa e execução dos testes

Mapeamento atualizado em **08/11/2026**. Os números de casos vêm da coleta do pytest:
cada combinação de `parametrize` ou fixture parametrizada conta como um caso.
Isso é um inventário de cenários; não representa uma medição de cobertura de linhas.

O mapa atual contém **33 arquivos, 550 funções de teste e 1.192 casos**:
**307 unitários** e **885 de integração**. Todos os arquivos de teste ficam
diretamente em `tests/`, sem marcadores de classificação. Para escolher o que
executar, informe os arquivos ou o nome de uma função ao pytest.

Esta ampliação acrescentou **28 casos diferentes dos anteriores**: 11 no arquivo
de tokens, 10 sobre notificações e 7 sobre classificação e contexto decimal.
Os 279 casos unitários anteriores foram preservados.

## Mapa atual dos testes

Os caminhos abaixo são relativos a `tests/`. A coluna "Unitários" é parte do total
de casos da mesma linha e descreve os testes que rodam sem banco; não é um marcador
no código. As contagens foram conferidas pela coleta e pelo relatório de execução.

| Arquivo | Funções | Casos | Unitários | Principais verificações |
| --- | ---: | ---: | ---: | --- |
| `test_auth.py` | 23 | 38 | 0 | Cadastro, conta pendente, comprovante, e-mail duplicado, login e bloqueio por tentativas |
| `test_auth_schemas.py` | 10 | 37 | 37 | Campos do cadastro, tamanho e força da senha, login antigo, URLs de comprovantes e perfil ignorado |
| `test_auth_service.py` | 8 | 16 | 16 | Cadastro pendente, falhas de persistência, credenciais, bloqueio e limpeza das tentativas |
| `test_avaliacao_cientifica.py` | 21 | 50 | 1 | Rascunho, envio, notas por critério, cálculo decimal, permissões, concorrência e imutabilidade |
| `test_avaliacao_designacoes.py` | 44 | 71 | 0 | Quantidade de avaliadores, distribuição balanceada, redistribuição, elegibilidade e acesso |
| `test_banco_de_teste.py` | 2 | 2 | 0 | Banco separado com sufixo `_test` e conexão da API com esse banco |
| `test_comprovantes.py` | 22 | 32 | 0 | Fila, filtros, paginação, aprovação, recusa, reenvio e ativação da conta |
| `test_convite_service.py` | 9 | 16 | 16 | Liderança, vagas, destinatário, estado do convite, aceite dos termos e falhas de persistência |
| `test_convites.py` | 46 | 66 | 0 | Convites, aceite, recusa, cancelamento, vagas, prazos, termos e versões aceitas |
| `test_criar_usuario.py` | 4 | 4 | 0 | Script de criação de usuário, normalização do e-mail, senha fraca e duplicidade |
| `test_dependencias.py` | 8 | 16 | 16 | Credenciais, token, disponibilidade da conta, conta pendente e papéis permitidos |
| `test_edital_schemas.py` | 13 | 37 | 37 | Limites do hackathon, patch, normalização de temas, ODS, pesos, escalas e quantidade de critérios |
| `test_envio_proposta.py` | 18 | 81 | 16 | Envio definitivo, homologação da equipe, prazo, fusos, completude, protocolo e rollback |
| `test_equipes.py` | 28 | 83 | 0 | Criação, líder, vínculo por edição, consultas, edição, permissões e rollback |
| `test_hackathon.py` | 3 | 28 | 20 | Prazo de inscrições, datas com ou sem fuso e seleção da edição aberta |
| `test_hackathons_admin.py` | 17 | 29 | 0 | Cadastro, consulta, edição, exclusão, datas e autorização do organizador |
| `test_health.py` | 1 | 1 | 0 | Resposta da API e disponibilidade do banco |
| `test_homologacao_service.py` | 8 | 26 | 26 | Requisitos da equipe, comprovantes, termos, convite recente e transições da homologação |
| `test_inscricao.py` | 33 | 37 | 0 | Conclusão, tamanho da equipe, termos, comprovantes, homologação, painel e protocolo |
| `test_inscricao_service.py` | 4 | 11 | 11 | Conclusão, protocolo, impedimentos e solicitação de rollback em falhas de cada etapa |
| `test_membros_equipe.py` | 28 | 107 | 0 | Listagem, função do integrante, remoção, proteção do líder, prazo e histórico |
| `test_migrations.py` | 38 | 41 | 0 | Migrations, enums, models, defaults, índices únicos, chaves e constraints no PostgreSQL |
| `test_notificacao_service.py` | 9 | 10 | 10 | Resultados vazios, equipes sem integrantes, falhas no lote, consultas de pareceres sem repetição e sem dados desatualizados |
| `test_permissoes.py` | 27 | 88 | 42 | Autorização, `/auth/me`, validade do token e hierarquia de cadastro de perfis |
| `test_resultado.py` | 16 | 22 | 1 | Média e arredondamento, classificação, desempate, homologação e publicação |
| `test_resultado_service.py` | 5 | 7 | 7 | Desempate por data e identificador, envio sem data, nota zero e independência do contexto decimal |
| `test_rubrica.py` | 23 | 40 | 4 | Nomes normalizados, critérios mínimos, pesos, escalas, publicação e imutabilidade |
| `test_senha.py` | 7 | 10 | 10 | Força da senha, hash Argon2, salt, senha incorreta e hash inválido |
| `test_somente_leitura.py` | 9 | 9 | 0 | Bloqueio de escrita após resultado, consultas permitidas e notificações aos integrantes |
| `test_submissoes.py` | 26 | 108 | 0 | Rascunho, edição parcial, tema, ODS, permissões, concorrência e rollback |
| `test_temas.py` | 20 | 32 | 0 | Cadastro e edição, validação de ODS, listagem, ativação e exclusão de temas |
| `test_token.py` | 15 | 19 | 19 | JWT, validade, assinatura, adulteração, claims obrigatórias, algoritmo permitido e datas futuras |
| `test_validacao_submissao.py` | 5 | 18 | 18 | Textos obrigatórios, ODS, lista completa de pendências e campos opcionais da proposta |
| **Total atual** | **550** | **1.192** | **307** | **885 casos dependem da integração** |

## Novos cenários desta ampliação

Os caminhos abaixo também ficam diretamente em `tests/`. Os services usam mocks
de `AsyncSession` e dos controllers. Não há consultas ao banco, chamadas de rede
ou necessidade de iniciar a API.

| Arquivo | Casos | O que foi acrescentado |
| --- | ---: | --- |
| `test_token.py` | 11 novos | Payload contendo apenas identificador e datas; ausência de identificador; identificadores não textuais; HS384 e HS512 rejeitados mesmo com a chave correta; token sem assinatura; validade e emissão futuras; expiração não numérica |
| `test_notificacao_service.py` | 10 | Ausência de resultados ou destinatários; falha na leitura da segunda equipe sem enviar lote parcial à persistência; erro ao adicionar o lote; usuário sem notificações sem buscar pareceres; uma consulta por proposta mesmo com avisos intercalados; nova chamada consulta parecer atualizado; erro de consulta propagado; parecer sem comentário ou recomendação |
| `test_resultado_service.py` | 7 | Empate por data de envio; empate completo resolvido por identificador em três ordens de entrada; proposta sem data após proposta com data; nota zero classificada enquanto proposta sem nota permanece sem posição; média independente do arredondamento global sem alterar o contexto do chamador |
| **Total desta ampliação** | **28 novos** | **21 funções novas, em dois arquivos novos e um existente** |

Os testes com mocks verificam as decisões das funções, os valores enviados aos
colaboradores e quando uma transação deve ser confirmada. Eles não comprovam
constraints, rollback real, concorrência ou persistência; esses comportamentos
continuam cobertos pelos testes de integração existentes.

## Como executar

Na raiz do projeto, com as dependências de desenvolvimento instaladas:

```powershell
# Arquivos alterados ou criados nesta ampliação: 36 casos, sendo 28 novos
.\.venv\Scripts\python.exe -m pytest tests/test_token.py tests/test_notificacao_service.py tests/test_resultado_service.py -v

# Somente autenticação no service, com o nome de cada caso
.\.venv\Scripts\python.exe -m pytest tests/test_auth_service.py -v

# Somente uma função específica
.\.venv\Scripts\python.exe -m pytest tests/test_token.py::test_token_sem_assinatura_e_rejeitado -v

# Relatório JUnit para os arquivos desta ampliação
.\.venv\Scripts\python.exe -m pytest tests/test_token.py tests/test_notificacao_service.py tests/test_resultado_service.py --junitxml=.venv/relatorio-novos-testes.xml

# Listar todos os casos, sem executá-los
.\.venv\Scripts\python.exe -m pytest --collect-only -q
```

O projeto lê as configurações durante os imports. Mesmo sem banco, é preciso ter
`JWT_SECRET` com pelo menos 32 caracteres no `.env` ou no ambiente. Caso não tenha
um `.env`, uma chave exclusiva de testes pode ser definida só no terminal atual:

```powershell
$env:JWT_SECRET = "chave-exclusiva-dos-testes-locais-com-32-caracteres"
```

Com Poetry, use, por exemplo, `poetry run pytest tests/test_token.py -v`.
Para preparar as dependências, o fluxo do projeto é `poetry install --no-root`.

Para repetir a verificação completa dos **307 casos que rodam sem banco**, use
esta seleção explícita no PowerShell. Ela inclui os arquivos inteiramente
unitários e as funções isoladas que já existiam nos arquivos mistos:

```powershell
$testes = @(
    'tests/test_auth_schemas.py',
    'tests/test_auth_service.py',
    'tests/test_convite_service.py',
    'tests/test_dependencias.py',
    'tests/test_edital_schemas.py',
    'tests/test_homologacao_service.py',
    'tests/test_inscricao_service.py',
    'tests/test_notificacao_service.py',
    'tests/test_resultado_service.py',
    'tests/test_senha.py',
    'tests/test_token.py',
    'tests/test_validacao_submissao.py',
    'tests/test_avaliacao_cientifica.py::test_calculo_usa_decimal_com_escalas_diferentes',
    'tests/test_envio_proposta.py::test_prazo_normaliza_fusos_e_inclui_limites',
    'tests/test_envio_proposta.py::test_periodo_invertido_nao_abre_envio',
    'tests/test_hackathon.py::test_periodo_compativel_com_utc_com_ou_sem_fuso',
    'tests/test_permissoes.py::test_hierarquia_de_cadastro',
    'tests/test_permissoes.py::test_todo_perfil_listado_pode_ser_cadastrado',
    'tests/test_resultado.py::test_media_arredonda_so_no_fim_com_half_up',
    'tests/test_rubrica.py::test_normalizar_nome_ignora_acentos_maiusculas_e_espacos',
    'tests/test_rubrica.py::test_criterios_minimos_faltantes',
    'tests/test_rubrica.py::test_pendencias_para_publicar',
    'tests/test_rubrica.py::test_prazo_de_publicacao'
)
.\.venv\Scripts\python.exe -m pytest @testes -q --junitxml=.venv/relatorio-unitarios.xml
```

Para integração, inicie o Docker Desktop e os serviços previstos pelo projeto:

```powershell
docker compose up -d --build

# Suíte completa
docker compose exec app pytest -q
```

O Compose cria o banco de testes e aplica as migrations. `tests/__init__.py`
seleciona `<POSTGRES_DB>_test` antes da criação do engine, separando os dados de
teste. Os testes de integração gravam dados reais nesse banco.

## Resultado da execução de 08/11/2026

- Coleta: **1.192 casos**, sendo **307 unitários** e **885 de integração**.
- Seleção sem banco: **307 aprovados, nenhuma falha e nenhum erro**, incluindo os 28 casos novos.
- Os três arquivos desta ampliação também foram executados separadamente:
  **36 aprovados**, sendo 8 casos anteriores de token e 28 novos.
- Organização: todos os 33 arquivos de teste estão diretamente em `tests/`, sem marcadores de classificação.
- Ruff: lint aprovado e formatação de `app/` e `tests/` aprovada.
- Aviso do ambiente: o Starlette informa que o uso de `httpx` pelo `TestClient`
  está obsoleto. O aviso vem das dependências existentes no lock e não reprovou os unitários.
- Integração: **885 casos não executados nesta rodada**; a execução selecionou arquivos e funções sem banco.
  Eles não devem ser contabilizados como aprovados.
- Na verificação anterior do ambiente, `tests/test_health.py::test_health` reprovou:
  esperava `{"status": "ok", "database": "ok"}`, mas recebeu
  `{"status": "ok", "database": "indisponivel"}`. O log registrou `WinError 1225`
  (conexão recusada) e o Docker estava parado. Essa falha de integração não foi
  reexecutada nesta ampliação.

Na preparação local, o Poetry falhou na validação do certificado de download.
As dependências foram instaladas com `pip`, preservando as versões e hashes
registrados no `poetry.lock`. O lock não foi alterado.

## Próximas lacunas para ampliar

1. Distribuição de avaliadores: equilíbrio de carga, exclusão de inelegíveis e
   insuficiência de avaliadores, isolando os controllers.
2. Consolidação do resultado com designações incompletas ou avaliações de
   propostas fora da lista de enviadas, isolando as consultas ao banco.
3. Fluxos de recusa e cancelamento de convites e reenvio de comprovantes com
   erros simulados de persistência.

## Prompt para pedir um novo relatório

```text
Execute os testes deste backend selecionando arquivos e funções conforme docs/testes.md.
Mantenha todos os arquivos de teste em tests/ e não adicione marcadores de classificação.
Informe quantos casos passaram, falharam ou não foram executados e o que foi testado.
Se houver erro, mostre o arquivo, o cenário, o resultado esperado, o resultado obtido
e a causa identificada. Separe defeitos do código de problemas do ambiente.
Não conte testes de integração sem execução como aprovados.
Atualize docs/testes.md se novos cenários forem acrescentados.
```
