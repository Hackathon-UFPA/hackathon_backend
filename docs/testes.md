# Mapa dos testes

Inventário conferido com a coleta do pytest. O índice indica onde acrescentar novos testes. A lista por arquivo aponta para cada função e agrupa suas parametrizações com a contagem de cenários.

**68 arquivos · 1.351 funções · 2.594 cenários** (557 unitários e 2.037 na seleção de integração do CI).

[Como adicionar um teste](#como-adicionar-um-teste) · [Índice por área](#índice-por-área) · [Cenários por arquivo](#cenários-por-arquivo)

## Como adicionar um teste

1. Localize a regra no [índice por área](#índice-por-área) e abra a lista de funções do arquivo. Procure também pelo nome da regra ou da rota em `tests/` quando ela aparecer em mais de um fluxo.
2. Cubra a regra no arquivo que já testa aquele comportamento. Use `pytest.mark.parametrize` para variações do mesmo contrato. Dê IDs descritivos aos parâmetros quando o valor por si só dificultar identificar a falha.
3. Use `@pytest.mark.unit` para regras isoladas com valores, dublês ou `monkeypatch`. Em arquivos mistos, aplique o marcador na função. Para contratos HTTP, persistência, migrations e concorrência, use o PostgreSQL de testes e as fixtures da integração.
4. Prepare os dados de cada cenário com as fixtures existentes. Nas escritas feitas pela API ou pela fixture `sql`, verifique a limpeza dos registros criados pelo teste. Para regras de acesso, teste a permissão e a recusa. Para regras de escrita, confira o efeito persistido quando fizer parte do contrato.
5. Rode o teste novo e o arquivo correspondente. Ao adicionar, renomear ou remover testes, atualize as contagens, os links e a classificação do arquivo neste mapa. Consulte `pytest --collect-only` para obter os nomes completos e as variantes parametrizadas.

### Fixtures e utilitários reutilizáveis

| Recurso | Uso | Origem |
| --- | --- | --- |
| `client` | `TestClient` compartilhado para exercitar a API. | [conftest.py](../tests/conftest.py) |
| `sql` | Executa SQL e confirma a transação. Serve para preparar dados e conferir o que a API persistiu. | [conftest.py](../tests/conftest.py) |
| `usuario_no_banco`, `novo_email`, `emails_criados` | Criam contas ou endereços exclusivos. A fixture de e-mails limpa os usuários e registros associados ao final. | [conftest.py](../tests/conftest.py) |
| `periodo_inscricoes`, `hackathon_aberto`, `edicoes_fora_do_periodo` | Preparam datas e status para regras de prazo e seleção da edição. | [conftest.py](../tests/conftest.py) |
| `com_token(usuario_id)`, `headers(usuario)` | Montam cabeçalhos com JWT para testar rotas autenticadas. | [test_convites.py](../tests/test_convites.py), [test_atribuicoes_mentor.py](../tests/test_atribuicoes_mentor.py) |
| `s`, `calendario`, `tecnico` | Preparam cenários reutilizados de atribuição de mentores, calendário da mentoria e designação técnica. | [test_atribuicoes_mentor.py](../tests/test_atribuicoes_mentor.py), [test_painel_mentor.py](../tests/test_painel_mentor.py), [test_designacao_projetos_finais.py](../tests/test_designacao_projetos_finais.py) |
| `fila_vazia`, `processar` | Isolam a fila e executam lotes de e-mail com um provedor controlado pelo teste. | [conftest.py](../tests/conftest.py) |
| `inserir_email`, `linha_do_email`, `emails_de` | Semeiam e consultam a fila, incluindo destinatário, tipo e horários relativos. | [helpers_email.py](../tests/helpers_email.py) |

A configuração em `tests/__init__.py` seleciona um banco com sufixo `_test` e desativa o worker automático de e-mail durante a suíte. [Configuração de testes](../tests/__init__.py)

### Executar, coletar e medir cobertura

Com as dependências de desenvolvimento instaladas e `JWT_SECRET` configurado, a coleta e os unitários dispensam um servidor PostgreSQL. A suíte completa e os testes de integração precisam do banco de testes com as migrations aplicadas. [Configuração do projeto](../README.md#testes)

| Objetivo | Comando |
| --- | --- |
| Listar todos os casos, incluindo IDs de parâmetros | `poetry run pytest --collect-only -q` |
| Listar os casos de um arquivo | `poetry run pytest --collect-only -q tests/test_entregas_mentoria.py` |
| Rodar um teste pelo nome completo | `poetry run pytest tests/test_entregas_mentoria.py::test_calendario_aceita_um_final_depois_dos_parciais` |
| Rodar os testes unitários | `poetry run pytest -m unit` |
| Rodar a integração | `poetry run pytest -m "not unit"` |
| Rodar toda a suíte no Docker Compose | `make test` |

Com o banco de testes preparado, meça as linhas e ramificações em `app` com o Coverage.py.

```sh
poetry run python -m pip install coverage
poetry run python -m coverage run --branch --concurrency=greenlet,thread --source=app -m pytest
poetry run python -m coverage report -m
```

O CI já seleciona os unitários pelo marcador e distribui a integração em oito grupos. [Workflow](../.github/workflows/ci.yml) · [Divisão dos grupos](../.github/scripts/run_test_shard.py)

## Índice por área

As colunas **Unitários** e **Integração** seguem os filtros `-m unit` e `-m "not unit"` usados no CI. As contagens incluem as variantes de cada teste parametrizado.

### Autenticação, perfis e permissões

| Arquivo | O que cobre | Unitários | Integração |
| --- | --- | ---: | ---: |
| [`test_auth.py`](#test_auth) | Cadastro e login via API, conta pendente, comprovantes e bloqueio por tentativas. | 0 | 44 |
| [`test_auth_schemas.py`](#test_auth_schemas) | Campos e formatos de cadastro e login, incluindo os dados exigidos por perfil. | 43 | 0 |
| [`test_auth_service.py`](#test_auth_service) | Regras do cadastro, autenticação e consistência da transação. | 26 | 0 |
| [`test_confirmacao_email_service.py`](#test_confirmacao_email_service) | Emissão de token de confirmação e enfileiramento do aviso. | 3 | 0 |
| [`test_criar_usuario.py`](#test_criar_usuario) | Comando de criação de usuários, normalização de e-mail e política de senha. | 0 | 5 |
| [`test_dependencias.py`](#test_dependencias) | Dependências de autenticação, conta ativa e autorização por papel. | 26 | 0 |
| [`test_gestao_usuarios.py`](#test_gestao_usuarios) | Consulta, edição, filtros e permissões da administração de usuários. | 0 | 52 |
| [`test_perfil_senha.py`](#test_perfil_senha) | Perfil do usuário, troca e recuperação de senha e confirmação de e-mail pela API. | 0 | 63 |
| [`test_perfil_service.py`](#test_perfil_service) | Campos editáveis, atualização parcial e regras do serviço de perfil. | 25 | 0 |
| [`test_permissoes.py`](#test_permissoes) | Identidade do usuário autenticado e acesso às rotas por papel e situação da conta. | 47 | 46 |
| [`test_recuperacao_senha_service.py`](#test_recuperacao_senha_service) | Elegibilidade, emissão do link e consumo do token na redefinição. | 11 | 0 |
| [`test_senha.py`](#test_senha) | Política de senha, geração de hash e verificação. | 10 | 0 |
| [`test_token.py`](#test_token) | Conteúdo, validade e expiração do JWT. | 16 | 0 |
| [`test_token_usuario.py`](#test_token_usuario) | Emissão, invalidação e consumo de tokens de finalidade específica. | 8 | 0 |

### Edições, organizações e conteúdo público

| Arquivo | O que cobre | Unitários | Integração |
| --- | --- | ---: | ---: |
| [`test_conteudo_institucional.py`](#test_conteudo_institucional) | Apoiadores, FAQ, cronograma, página pública, publicação e permissões. | 0 | 219 |
| [`test_edital_schemas.py`](#test_edital_schemas) | Limites e datas do edital, validação de atualização parcial e regras dos schemas. | 37 | 0 |
| [`test_hackathon.py`](#test_hackathon) | Seleção da edição disponível e interpretação dos períodos do edital. | 20 | 8 |
| [`test_hackathons_admin.py`](#test_hackathons_admin) | Cadastro e gestão de edições, datas em UTC e permissões administrativas. | 0 | 30 |
| [`test_organizacao_security.py`](#test_organizacao_security) | Autorização por organização e escopo da edição ou do recurso. | 34 | 0 |
| [`test_organizacoes.py`](#test_organizacoes) | Isolamento entre organizações, painel administrativo e vitrine pública. | 0 | 30 |

### Cadastro, inscrições e vínculos

| Arquivo | O que cobre | Unitários | Integração |
| --- | --- | ---: | ---: |
| [`test_autodeclaracao.py`](#test_autodeclaracao) | Declaração de vínculo, histórico e efeitos na elegibilidade da equipe. | 0 | 41 |
| [`test_cadastro_equipe_integrantes.py`](#test_cadastro_equipe_integrantes) | Cadastro de equipe com integrantes existentes e por convite, com idempotência. | 0 | 43 |
| [`test_cadastro_por_hackathon.py`](#test_cadastro_por_hackathon) | Vínculo, cadastro e comprovantes separados por edição. | 0 | 41 |
| [`test_cadastro_profissional.py`](#test_cadastro_profissional) | Cadastro profissional, dados de empresa e cargo e contrato por tipo de vínculo. | 0 | 9 |
| [`test_comprovantes.py`](#test_comprovantes) | Envio, consulta, fila e revisão de comprovantes de vínculo. | 0 | 35 |
| [`test_edicao_participante.py`](#test_edicao_participante) | Resolução de edição explícita ou legada para o participante. | 6 | 0 |
| [`test_homologacao_service.py`](#test_homologacao_service) | Elegibilidade e requisitos para homologação da equipe. | 28 | 0 |
| [`test_inscricao.py`](#test_inscricao) | Conclusão da inscrição, composição, prazo, protocolo e homologação. | 0 | 37 |
| [`test_inscricao_service.py`](#test_inscricao_service) | Regras de conclusão, atomicidade e tratamento de erros. | 13 | 0 |
| [`test_somente_leitura.py`](#test_somente_leitura) | Permissões de consulta e bloqueios de escrita após reprovação ou encerramento de períodos. | 0 | 9 |

### Equipes, integrantes e convites

| Arquivo | O que cobre | Unitários | Integração |
| --- | --- | ---: | ---: |
| [`test_categoria_equipe.py`](#test_categoria_equipe) | Compatibilidade entre categorias da equipe e tipos de integrantes. | 30 | 0 |
| [`test_convite_service.py`](#test_convite_service) | Regras do envio de convites, capacidade e autorização do líder. | 16 | 0 |
| [`test_convites.py`](#test_convites) | Envio, aceite, cancelamento, prazos e termos associados. | 0 | 66 |
| [`test_equipes.py`](#test_equipes) | Criação e gestão de equipes, escolha do líder inicial e permissões. | 0 | 83 |
| [`test_equipes_categoria.py`](#test_equipes_categoria) | Composição por categoria, políticas da edição e atualização de equipes. | 0 | 49 |
| [`test_equipes_publicas.py`](#test_equipes_publicas) | Listagem pública de equipes homologadas e proteção de dados pessoais. | 0 | 2 |
| [`test_membros_equipe.py`](#test_membros_equipe) | Listagem e alteração dos membros, papéis e restrições por equipe e prazo. | 0 | 107 |
| [`test_reenvio_convite.py`](#test_reenvio_convite) | Reenvio, troca de endereço, renovação de links, limites e idempotência. | 0 | 42 |

### Propostas e avaliação científica

| Arquivo | O que cobre | Unitários | Integração |
| --- | --- | ---: | ---: |
| [`test_avaliacao_cientifica.py`](#test_avaliacao_cientifica) | Rascunho e envio de parecer, notas por critério e escopo do avaliador. | 1 | 49 |
| [`test_avaliacao_designacoes.py`](#test_avaliacao_designacoes) | Configuração, distribuição, redistribuição, elegibilidade e conflitos de avaliadores. | 0 | 72 |
| [`test_envio_proposta.py`](#test_envio_proposta) | Envio da proposta, validação do prazo, permissões e protocolo. | 16 | 65 |
| [`test_resultado.py`](#test_resultado) | Consolidação das avaliações, classificação, homologação e publicação. | 1 | 21 |
| [`test_resultado_service.py`](#test_resultado_service) | Desempates e regras de classificação entre propostas. | 7 | 0 |
| [`test_rubrica.py`](#test_rubrica) | Critérios, pesos, publicação e validações da rubrica. | 5 | 36 |
| [`test_submissoes.py`](#test_submissoes) | Criação, edição e consulta de rascunhos de proposta, vínculo com tema e permissões. | 0 | 108 |
| [`test_temas.py`](#test_temas) | Cadastro, edição, ativação e consulta de temas por edição. | 0 | 34 |
| [`test_temas_rubricas_comite.py`](#test_temas_rubricas_comite) | Catálogo de temas e configuração ou consulta de rubricas por fase e comitê. | 0 | 27 |
| [`test_validacao_links.py`](#test_validacao_links) | Validação de links externos em HTTPS, campos permitidos e tamanho máximo. | 17 | 0 |
| [`test_validacao_submissao.py`](#test_validacao_submissao) | Datas de envio, conteúdo obrigatório, ODS e demais regras da proposta. | 13 | 0 |
| [`test_versionamento_proposta.py`](#test_versionamento_proposta) | Reenvio versionado, histórico, protocolos e avisos por versão. | 0 | 33 |

### Mentoria e avaliação técnica

| Arquivo | O que cobre | Unitários | Integração |
| --- | --- | ---: | ---: |
| [`test_atribuicoes_mentor.py`](#test_atribuicoes_mentor) | Elegibilidade e capacidade do mentor, atribuição, troca, encerramento e histórico. | 0 | 53 |
| [`test_designacao_projetos_finais.py`](#test_designacao_projetos_finais) | Designação técnica, distribuição, conflitos e acesso a projetos finais. | 0 | 47 |
| [`test_entregas_mentoria.py`](#test_entregas_mentoria) | Marcos, calendário, entregas parciais, submissão final e download do relatório. | 0 | 8 |
| [`test_feedbacks_mentoria.py`](#test_feedbacks_mentoria) | Registro e correção de feedbacks, histórico, acesso e idempotência. | 0 | 70 |
| [`test_mentores.py`](#test_mentores) | Cadastro, convites, ativação, perfil, termos e gestão dos mentores. | 0 | 112 |
| [`test_painel_mentor.py`](#test_painel_mentor) | Progresso das equipes, pendências, calendário, paginação e acesso do mentor. | 0 | 35 |
| [`test_validacao_submissao_final.py`](#test_validacao_submissao_final) | Formato do repositório, respostas do GitHub, mídia, tamanho e estrutura do PDF. | 31 | 0 |

### E-mails e notificações

| Arquivo | O que cobre | Unitários | Integração |
| --- | --- | ---: | ---: |
| [`test_email_api.py`](#test_email_api) | Permissões e operações administrativas da fila de e-mails. | 0 | 48 |
| [`test_email_envio.py`](#test_email_envio) | Processamento em lotes, tentativas, espera e concorrência do envio. | 1 | 19 |
| [`test_email_eventos.py`](#test_email_eventos) | Geração de e-mails transacionais por eventos de negócio. | 0 | 16 |
| [`test_email_fila.py`](#test_email_fila) | Persistência de e-mails, idempotência, agendamento e consulta à fila. | 1 | 26 |
| [`test_email_provedores.py`](#test_email_provedores) | Montagem da mensagem e comportamento dos provedores de envio. | 28 | 0 |
| [`test_email_templates.py`](#test_email_templates) | Templates de texto e HTML, contexto obrigatório e renderização de links. | 32 | 0 |
| [`test_notificacao_service.py`](#test_notificacao_service) | Listagem paginada e composição de notificações com dados de pareceres. | 5 | 0 |
| [`test_notificacoes.py`](#test_notificacoes) | Criação, idempotência, listagem, leitura e acesso à central de notificações. | 0 | 53 |

### Banco, migrations e saúde da API

| Arquivo | O que cobre | Unitários | Integração |
| --- | --- | ---: | ---: |
| [`test_banco_de_teste.py`](#test_banco_de_teste) | Banco exclusivo de testes e conexão compartilhada com a API. | 0 | 2 |
| [`test_health.py`](#test_health) | Contrato de resposta da rota de saúde. | 0 | 1 |
| [`test_migrations.py`](#test_migrations) | Migrations aplicadas, coerência entre enums, modelos e esquema e restrições do banco. | 0 | 41 |

## Cenários por arquivo

Abra a lista para ver as funções. Cada nome aponta para a definição no código. A indicação de modalidade nas linhas aparece nos arquivos que misturam unitários e integração.

### test_auth

Arquivo [`tests/test_auth.py`](../tests/test_auth.py) · integração · 26 funções · 44 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_cadastro_cria_participante_com_conta_pendente`](../tests/test_auth.py#L49)
- [`test_cadastro_registra_comprovante_pendente_no_hackathon_aberto`](../tests/test_auth.py#L68)
- [`test_cadastro_ignora_edicoes_mais_recentes_fora_do_periodo`](../tests/test_auth.py#L84)
- [`test_cadastro_guarda_email_em_minusculas`](../tests/test_auth.py#L98)
- [`test_cadastro_ignora_o_perfil_enviado_pelo_cliente`](../tests/test_auth.py#L107)
- [`test_cadastro_com_email_repetido`](../tests/test_auth.py#L114)
- [`test_cadastro_com_email_repetido_em_outras_maiusculas`](../tests/test_auth.py#L121)
- [`test_cadastro_com_senha_fraca`](../tests/test_auth.py#L129) · 4 cenários
- [`test_cadastro_sem_campo_obrigatorio`](../tests/test_auth.py#L136) · 7 cenários
- [`test_cadastro_com_comprovante_invalido`](../tests/test_auth.py#L152) · 4 cenários
- [`test_cadastro_aceita_pdf_e_imagens`](../tests/test_auth.py#L157) · 4 cenários
- [`test_cadastro_sem_hackathon_com_inscricoes`](../tests/test_auth.py#L163)
- [`test_cadastro_de_organizacao_cria_organizador_e_entra`](../tests/test_auth.py#L196)
- [`test_cadastro_de_organizacao_com_email_repetido_nao_cria_organizacao`](../tests/test_auth.py#L229)
- [`test_cadastro_de_organizacao_com_dados_invalidos`](../tests/test_auth.py#L254) · 4 cenários
- [`test_login_devolve_token_do_usuario`](../tests/test_auth.py#L265)
- [`test_login_sem_diferenciar_maiusculas_no_email`](../tests/test_auth.py#L277)
- [`test_conta_pendente_consegue_entrar`](../tests/test_auth.py#L283)
- [`test_senha_errada_e_email_inexistente_dao_a_mesma_resposta`](../tests/test_auth.py#L289)
- [`test_login_de_conta_desativada`](../tests/test_auth.py#L299)
- [`test_login_de_conta_sem_senha`](../tests/test_auth.py#L308)
- [`test_login_com_email_invalido`](../tests/test_auth.py#L317)
- [`test_conta_bloqueia_depois_de_varias_falhas_seguidas`](../tests/test_auth.py#L324)
- [`test_bloqueio_acaba_com_o_tempo`](../tests/test_auth.py#L337)
- [`test_login_correto_zera_as_falhas`](../tests/test_auth.py#L354)
- [`test_login_devolve_os_dados_do_usuario`](../tests/test_auth.py#L369)

</details>

### test_auth_schemas

Arquivo [`tests/test_auth_schemas.py`](../tests/test_auth_schemas.py) · unitário · 14 funções · 43 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_textos_do_cadastro_removem_espacos_nas_extremidades`](../tests/test_auth_schemas.py#L26) · 3 cenários
- [`test_textos_do_cadastro_rejeitam_vazios_e_excesso_de_caracteres`](../tests/test_auth_schemas.py#L36) · 9 cenários
- [`test_profissional_informa_empresa_e_cargo_no_lugar_de_dados_academicos`](../tests/test_auth_schemas.py#L52)
- [`test_profissional_precisa_dos_dois_dados_de_vinculo`](../tests/test_auth_schemas.py#L61) · 2 cenários
- [`test_profissional_recusa_dados_academicos`](../tests/test_auth_schemas.py#L69) · 2 cenários
- [`test_cadastro_legado_e_estudante_e_recusa_cargo`](../tests/test_auth_schemas.py#L74)
- [`test_periodo_precisa_ser_positivo`](../tests/test_auth_schemas.py#L82) · 2 cenários
- [`test_senha_aceita_limites_de_oito_e_128_caracteres`](../tests/test_auth_schemas.py#L92) · 2 cenários
- [`test_cadastro_rejeita_senha_fora_do_tamanho_ou_sem_letra_e_numero`](../tests/test_auth_schemas.py#L99) · 4 cenários
- [`test_comprovante_aceita_extensoes_permitidas_com_query_e_fragmento`](../tests/test_auth_schemas.py#L109) · 4 cenários
- [`test_comprovante_rejeita_protocolo_e_caminho_invalidos`](../tests/test_auth_schemas.py#L127) · 6 cenários
- [`test_cadastro_nao_aceita_perfil_privilegiado_enviado_pelo_cliente`](../tests/test_auth_schemas.py#L136)
- [`test_login_aceita_senha_antiga_sem_aplicar_regra_de_forca`](../tests/test_auth_schemas.py#L143) · 4 cenários
- [`test_login_rejeita_senha_vazia_ou_acima_do_limite`](../tests/test_auth_schemas.py#L148) · 2 cenários

</details>

### test_auth_service

Arquivo [`tests/test_auth_service.py`](../tests/test_auth_service.py) · unitário · 12 funções · 26 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_cadastro_cria_conta_pendente_e_comprovante_na_mesma_sessao`](../tests/test_auth_service.py#L74)
- [`test_cadastro_sem_edicao_aberta_nao_cria_conta`](../tests/test_auth_service.py#L105)
- [`test_cadastro_nao_confirma_transacao_se_a_persistencia_falhar`](../tests/test_auth_service.py#L123) · 4 cenários
- [`test_cadastro_profissional_vincula_comprovante_a_declaracao_da_edicao`](../tests/test_auth_service.py#L137)
- [`test_cadastro_de_organizacao_cria_responsavel_ativo_na_mesma_transacao`](../tests/test_auth_service.py#L168) · 2 cenários
- [`test_credenciais_indisponiveis_tem_resposta_generica_sem_alterar_conta`](../tests/test_auth_service.py#L207) · 3 cenários
- [`test_conta_bloqueada_informa_espera_sem_verificar_senha`](../tests/test_auth_service.py#L228) · 3 cenários
- [`test_senha_errada_registra_falha_antes_de_devolver_401`](../tests/test_auth_service.py#L241)
- [`test_login_correto_sem_falhas_retorna_usuario_sem_gravacao`](../tests/test_auth_service.py#L264) · 2 cenários
- [`test_login_correto_limpa_historico_e_aceita_fim_do_bloqueio`](../tests/test_auth_service.py#L276) · 3 cenários
- [`test_confirmacao_de_senha_aplica_bloqueio_e_preserva_sessao`](../tests/test_auth_service.py#L292) · 3 cenários
- [`test_confirmacao_de_senha_correta_delega_commit_a_operacao`](../tests/test_auth_service.py#L315) · 2 cenários

</details>

### test_confirmacao_email_service

Arquivo [`tests/test_confirmacao_email_service.py`](../tests/test_confirmacao_email_service.py) · unitário · 2 funções · 3 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_confirmacao_envia_para_o_endereco_a_confirmar`](../tests/test_confirmacao_email_service.py#L23) · 2 cenários
- [`test_falha_ao_emitir_confirmacao_nao_enfileira_email`](../tests/test_confirmacao_email_service.py#L55)

</details>

### test_criar_usuario

Arquivo [`tests/test_criar_usuario.py`](../tests/test_criar_usuario.py) · integração · 5 funções · 5 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_cria_usuario_ativo_que_consegue_entrar`](../tests/test_criar_usuario.py#L33)
- [`test_guarda_o_email_em_minusculas`](../tests/test_criar_usuario.py#L45)
- [`test_recusa_senha_fraca`](../tests/test_criar_usuario.py#L51)
- [`test_script_nao_contorna_ativacao_de_mentor`](../tests/test_criar_usuario.py#L56)
- [`test_recusa_email_ja_cadastrado`](../tests/test_criar_usuario.py#L61)

</details>

### test_dependencias

Arquivo [`tests/test_dependencias.py`](../tests/test_dependencias.py) · unitário · 12 funções · 26 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_sem_credenciais_responde_401_sem_consultar_banco`](../tests/test_dependencias.py#L29)
- [`test_token_invalido_responde_401_sem_consultar_banco`](../tests/test_dependencias.py#L38)
- [`test_token_valido_de_conta_indisponivel_responde_401`](../tests/test_dependencias.py#L52) · 3 cenários
- [`test_usuario_atual_retorna_conta_do_banco_inclusive_pendente`](../tests/test_dependencias.py#L70) · 2 cenários
- [`test_usuario_ativo_rejeita_conta_pendente`](../tests/test_dependencias.py#L84)
- [`test_usuario_ativo_aceita_conta_aprovada`](../tests/test_dependencias.py#L94)
- [`test_visitante_pode_consultar_rota_publica_sem_consultar_banco`](../tests/test_dependencias.py#L98)
- [`test_token_invalido_na_rota_publica_ainda_retorna_401`](../tests/test_dependencias.py#L103)
- [`test_mentor_precisa_concluir_ativacao_nas_duas_dependencias`](../tests/test_dependencias.py#L118) · 6 cenários
- [`test_participante_pendente_pode_responder_convite`](../tests/test_dependencias.py#L133)
- [`test_exigir_papeis_permite_somente_papel_configurado_e_dev`](../tests/test_dependencias.py#L139) · 6 cenários
- [`test_exigir_papeis_aceita_mais_de_um_perfil`](../tests/test_dependencias.py#L152) · 2 cenários

</details>

### test_gestao_usuarios

Arquivo [`tests/test_gestao_usuarios.py`](../tests/test_gestao_usuarios.py) · integração · 37 funções · 52 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_perfis_sem_gestao_recebem_403_em_todas_as_rotas`](../tests/test_gestao_usuarios.py#L76) · 3 cenários
- [`test_conta_pendente_nao_gerencia`](../tests/test_gestao_usuarios.py#L89)
- [`test_sem_token_recebe_401`](../tests/test_gestao_usuarios.py#L95)
- [`test_comite_cientifico_so_alcanca_comite_tecnico_e_mentor`](../tests/test_gestao_usuarios.py#L105)
- [`test_organizador_nao_alcanca_dev`](../tests/test_gestao_usuarios.py#L118)
- [`test_dev_alcanca_todos`](../tests/test_gestao_usuarios.py#L126)
- [`test_organizador_lista_menos_dev`](../tests/test_gestao_usuarios.py#L136)
- [`test_comite_cientifico_lista_so_o_que_gerencia`](../tests/test_gestao_usuarios.py#L149)
- [`test_filtrar_perfil_fora_do_alcance_devolve_lista_vazia`](../tests/test_gestao_usuarios.py#L161)
- [`test_filtros_de_busca_e_situacao`](../tests/test_gestao_usuarios.py#L170)
- [`test_paginacao_e_parametros_invalidos`](../tests/test_gestao_usuarios.py#L187)
- [`test_resposta_nao_traz_senha_nem_versao_de_sessao`](../tests/test_gestao_usuarios.py#L204)
- [`test_consultar_inexistente_e_id_invalido`](../tests/test_gestao_usuarios.py#L214)
- [`test_editar_dados_pessoais`](../tests/test_gestao_usuarios.py#L224)
- [`test_editar_recusa_campos_fora_da_lista`](../tests/test_gestao_usuarios.py#L253) · 7 cenários
- [`test_editar_recusa_nulos`](../tests/test_gestao_usuarios.py#L265)
- [`test_editar_inexistente`](../tests/test_gestao_usuarios.py#L275)
- [`test_organizador_troca_perfil_entre_os_de_gestao`](../tests/test_gestao_usuarios.py#L283)
- [`test_troca_de_perfil_fora_do_conjunto_permitido`](../tests/test_gestao_usuarios.py#L308) · 5 cenários
- [`test_comite_cientifico_nao_promove_ninguem`](../tests/test_gestao_usuarios.py#L320)
- [`test_ninguem_altera_o_proprio_perfil`](../tests/test_gestao_usuarios.py#L331)
- [`test_editar_o_proprio_nome_pela_rota_admin_e_permitido`](../tests/test_gestao_usuarios.py#L342)
- [`test_rebaixar_o_ultimo_organizador_e_recusado`](../tests/test_gestao_usuarios.py#L350)
- [`test_mentor_nao_se_edita_por_aqui`](../tests/test_gestao_usuarios.py#L364)
- [`test_desativar_bloqueia_o_acesso_na_hora`](../tests/test_gestao_usuarios.py#L378)
- [`test_desativar_gasta_links_pendentes`](../tests/test_gestao_usuarios.py#L393)
- [`test_desativar_duas_vezes_nao_muda_nada`](../tests/test_gestao_usuarios.py#L407)
- [`test_desativar_a_propria_conta`](../tests/test_gestao_usuarios.py#L418)
- [`test_desativar_inexistente`](../tests/test_gestao_usuarios.py#L429)
- [`test_desativar_o_ultimo_organizador_ativo`](../tests/test_gestao_usuarios.py#L436)
- [`test_desativar_organizador_havendo_outro_ativo`](../tests/test_gestao_usuarios.py#L445)
- [`test_mentor_nao_se_desativa_nem_reativa_por_aqui`](../tests/test_gestao_usuarios.py#L454)
- [`test_reativar_devolve_o_acesso`](../tests/test_gestao_usuarios.py#L463)
- [`test_reativar_conta_ativa_nao_muda_nada`](../tests/test_gestao_usuarios.py#L474)
- [`test_conta_desativada_nao_gerencia`](../tests/test_gestao_usuarios.py#L483)
- [`test_desativacoes_cruzadas_dos_dois_ultimos_organizadores`](../tests/test_gestao_usuarios.py#L495)
- [`test_ninguem_se_promove_pela_rota_do_proprio_perfil`](../tests/test_gestao_usuarios.py#L522) · 4 cenários

</details>

### test_perfil_senha

Arquivo [`tests/test_perfil_senha.py`](../tests/test_perfil_senha.py) · integração · 51 funções · 63 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_me_devolve_os_dados_e_o_alias_antigo`](../tests/test_perfil_senha.py#L81)
- [`test_me_sem_token_ou_com_conta_desativada`](../tests/test_perfil_senha.py#L93)
- [`test_patch_me_altera_so_o_que_foi_enviado`](../tests/test_perfil_senha.py#L102)
- [`test_patch_me_recusa_campos_que_a_pessoa_nao_controla`](../tests/test_perfil_senha.py#L131) · 8 cenários
- [`test_patch_me_recusa_nulo_e_nome_vazio`](../tests/test_perfil_senha.py#L143)
- [`test_dados_de_mentor_so_para_mentor`](../tests/test_perfil_senha.py#L155)
- [`test_conta_pendente_consulta_e_edita_o_proprio_perfil`](../tests/test_perfil_senha.py#L173)
- [`test_pedido_responde_igual_com_ou_sem_conta`](../tests/test_perfil_senha.py#L185)
- [`test_pedido_ignora_maiusculas_no_email`](../tests/test_perfil_senha.py#L198)
- [`test_email_de_recuperacao_traz_so_o_link`](../tests/test_perfil_senha.py#L206)
- [`test_token_guardado_so_como_hash`](../tests/test_perfil_senha.py#L217)
- [`test_sem_email_para_conta_que_nao_pode_entrar`](../tests/test_perfil_senha.py#L243) · 2 cenários
- [`test_conta_pendente_pode_recuperar_a_senha`](../tests/test_perfil_senha.py#L254)
- [`test_pedidos_em_sequencia_nao_geram_outro_email`](../tests/test_perfil_senha.py#L262)
- [`test_novo_pedido_gasta_o_link_anterior`](../tests/test_perfil_senha.py#L272)
- [`test_redefinir_troca_a_senha_e_encerra_as_sessoes`](../tests/test_perfil_senha.py#L284)
- [`test_redefinir_libera_conta_bloqueada_e_confirma_o_email`](../tests/test_perfil_senha.py#L304)
- [`test_link_so_funciona_uma_vez`](../tests/test_perfil_senha.py#L321)
- [`test_link_vencido_e_recusado`](../tests/test_perfil_senha.py#L335)
- [`test_token_inventado_tem_a_mesma_resposta_do_vencido`](../tests/test_perfil_senha.py#L348)
- [`test_token_com_tamanho_invalido`](../tests/test_perfil_senha.py#L356) · 2 cenários
- [`test_senha_fraca_nao_gasta_o_link`](../tests/test_perfil_senha.py#L360)
- [`test_link_de_conta_desativada_depois_do_pedido_e_recusado`](../tests/test_perfil_senha.py#L371)
- [`test_dois_usos_simultaneos_do_mesmo_link`](../tests/test_perfil_senha.py#L384)
- [`test_trocar_senha_devolve_novo_token_e_derruba_os_antigos`](../tests/test_perfil_senha.py#L408)
- [`test_trocar_senha_com_senha_atual_errada`](../tests/test_perfil_senha.py#L429)
- [`test_senha_atual_errada_repetida_bloqueia_a_conta`](../tests/test_perfil_senha.py#L448)
- [`test_trocar_senha_recusa_senha_nova_ruim`](../tests/test_perfil_senha.py#L472) · 4 cenários
- [`test_trocar_senha_gasta_pedido_de_redefinicao_aberto`](../tests/test_perfil_senha.py#L485)
- [`test_logout_invalida_todos_os_tokens_da_conta`](../tests/test_perfil_senha.py#L504)
- [`test_logout_sem_token_e_com_token_ja_encerrado`](../tests/test_perfil_senha.py#L518)
- [`test_conta_pendente_pode_encerrar_a_sessao`](../tests/test_perfil_senha.py#L527)
- [`test_sessao_informa_quando_vence`](../tests/test_perfil_senha.py#L533)
- [`test_token_com_versao_de_sessao_diferente_e_recusado`](../tests/test_perfil_senha.py#L547)
- [`test_token_antigo_sem_versao_vale_como_zero`](../tests/test_perfil_senha.py#L554)
- [`test_versao_de_sessao_invalida_no_token`](../tests/test_perfil_senha.py#L568)
- [`test_cadastro_envia_o_link_de_confirmacao`](../tests/test_perfil_senha.py#L604)
- [`test_confirmar_email_marca_o_endereco_e_nao_exige_login`](../tests/test_perfil_senha.py#L618)
- [`test_confirmacao_nao_bloqueia_o_login`](../tests/test_perfil_senha.py#L636)
- [`test_confirmar_com_token_de_outra_finalidade`](../tests/test_perfil_senha.py#L643)
- [`test_reenviar_confirmacao`](../tests/test_perfil_senha.py#L655)
- [`test_reenviar_confirmacao_em_sequencia_nao_duplica`](../tests/test_perfil_senha.py#L670)
- [`test_reenviar_confirmacao_de_email_ja_confirmado`](../tests/test_perfil_senha.py#L680)
- [`test_troca_de_email_so_vale_depois_de_confirmar`](../tests/test_perfil_senha.py#L699)
- [`test_troca_de_email_exige_a_senha`](../tests/test_perfil_senha.py#L721)
- [`test_troca_para_email_de_outra_conta`](../tests/test_perfil_senha.py#L730)
- [`test_troca_para_o_mesmo_email`](../tests/test_perfil_senha.py#L737)
- [`test_troca_com_email_invalido`](../tests/test_perfil_senha.py#L743)
- [`test_outro_pedido_de_troca_gasta_o_anterior`](../tests/test_perfil_senha.py#L749)
- [`test_endereco_tomado_antes_da_confirmacao`](../tests/test_perfil_senha.py#L765)
- [`test_confirmacao_de_conta_desativada_e_recusada`](../tests/test_perfil_senha.py#L782)

</details>

### test_perfil_service

Arquivo [`tests/test_perfil_service.py`](../tests/test_perfil_service.py) · unitário · 12 funções · 25 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_dados_reservados_nao_fazem_parte_do_contrato_de_edicao`](../tests/test_perfil_service.py#L53) · 5 cenários
- [`test_edicao_rejeita_nulo_mas_aceita_ausencia`](../tests/test_perfil_service.py#L60)
- [`test_edicao_altera_somente_os_campos_enviados`](../tests/test_perfil_service.py#L67)
- [`test_campos_de_mentoria_exigem_o_papel_de_mentor`](../tests/test_perfil_service.py#L84) · 2 cenários
- [`test_conta_e_sessao_sao_revalidadas_apos_a_trava`](../tests/test_perfil_service.py#L101) · 2 cenários
- [`test_reenvio_de_confirmacao_respeita_situacao_e_intervalo`](../tests/test_perfil_service.py#L121) · 3 cenários
- [`test_troca_de_email_so_enfileira_confirmacao_para_endereco_novo`](../tests/test_perfil_service.py#L145) · 3 cenários
- [`test_confirmacao_desfaz_uso_do_link_quando_nao_pode_atualizar`](../tests/test_perfil_service.py#L170) · 3 cenários
- [`test_confirmacao_grava_endereco_normalizado_e_revoga_links_anteriores`](../tests/test_perfil_service.py#L189) · 2 cenários
- [`test_troca_de_senha_rejeita_senha_igual`](../tests/test_perfil_service.py#L207)
- [`test_troca_de_senha_revoga_sessoes_e_links_de_redefinicao`](../tests/test_perfil_service.py#L217)
- [`test_logout_em_todos_os_dispositivos_confirma_revogacao`](../tests/test_perfil_service.py#L235)

</details>

### test_permissoes

Arquivo [`tests/test_permissoes.py`](../tests/test_permissoes.py) · misto · 28 funções · 93 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_me_devolve_os_dados_de_quem_esta_logado`](../tests/test_permissoes.py#L53) · integração
- [`test_conta_pendente_consulta_os_proprios_dados`](../tests/test_permissoes.py#L64) · integração
- [`test_fluxo_completo_login_e_consulta`](../tests/test_permissoes.py#L73) · integração
- [`test_sem_token`](../tests/test_permissoes.py#L90) · integração
- [`test_token_invalido`](../tests/test_permissoes.py#L105) · 3 cenários · integração
- [`test_token_vencido`](../tests/test_permissoes.py#L109) · integração
- [`test_token_adulterado`](../tests/test_permissoes.py#L118) · integração
- [`test_token_de_usuario_que_nao_existe`](../tests/test_permissoes.py#L127) · integração
- [`test_token_de_conta_desativada_deixa_de_valer`](../tests/test_permissoes.py#L131) · integração
- [`test_troca_de_perfil_vale_no_pedido_seguinte`](../tests/test_permissoes.py#L140) · integração
- [`test_cadastro_de_usuario_sem_token`](../tests/test_permissoes.py#L162) · integração
- [`test_perfil_sem_permissao_nao_cadastra_usuarios`](../tests/test_permissoes.py#L169) · 3 cenários · integração
- [`test_conta_pendente_nao_cadastra_usuarios`](../tests/test_permissoes.py#L181) · integração
- [`test_organizador_cadastra_qualquer_perfil_de_negocio`](../tests/test_permissoes.py#L194) · 5 cenários · integração
- [`test_organizador_nao_cadastra_dev`](../tests/test_permissoes.py#L214) · integração
- [`test_comite_cientifico_cadastra_comite_tecnico_e_mentor`](../tests/test_permissoes.py#L226) · 2 cenários · integração
- [`test_comite_cientifico_nao_cadastra_os_demais_perfis`](../tests/test_permissoes.py#L240) · 4 cenários · integração
- [`test_dev_acessa_a_rota_e_cadastra_qualquer_perfil`](../tests/test_permissoes.py#L254) · 6 cenários · integração
- [`test_usuario_cadastrado_consegue_entrar`](../tests/test_permissoes.py#L267) · integração
- [`test_cadastro_de_mentor_guarda_os_dados_do_perfil`](../tests/test_permissoes.py#L279) · integração
- [`test_cadastro_de_usuario_com_email_repetido`](../tests/test_permissoes.py#L301) · integração
- [`test_cadastro_de_usuario_com_senha_fraca`](../tests/test_permissoes.py#L316) · integração
- [`test_hierarquia_de_cadastro`](../tests/test_permissoes.py#L348) · 36 cenários · unitário
- [`test_lista_os_perfis_que_o_usuario_pode_cadastrar`](../tests/test_permissoes.py#L358) · 3 cenários · integração
- [`test_perfil_sem_permissao_nao_lista_perfis`](../tests/test_permissoes.py#L369) · 3 cenários · integração
- [`test_lista_de_perfis_sem_token`](../tests/test_permissoes.py#L377) · integração
- [`test_todo_perfil_listado_pode_ser_cadastrado`](../tests/test_permissoes.py#L383) · 6 cenários · unitário
- [`test_gestor_precisa_poder_gerenciar_a_origem_e_o_destino_da_troca`](../tests/test_permissoes.py#L401) · 5 cenários · unitário

</details>

### test_recuperacao_senha_service

Arquivo [`tests/test_recuperacao_senha_service.py`](../tests/test_recuperacao_senha_service.py) · unitário · 4 funções · 11 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_solicitacao_inelegivel_nao_emite_token_ou_email`](../tests/test_recuperacao_senha_service.py#L54) · 5 cenários
- [`test_solicitacao_valida_emite_e_enfileira_o_link_na_mesma_transacao`](../tests/test_recuperacao_senha_service.py#L80) · 2 cenários
- [`test_redefinicao_desfaz_consumo_quando_a_conta_nao_pode_ser_alterada`](../tests/test_recuperacao_senha_service.py#L107) · 2 cenários
- [`test_redefinicao_revoga_sessoes_e_links_e_desbloqueia_a_conta`](../tests/test_recuperacao_senha_service.py#L125) · 2 cenários

</details>

### test_senha

Arquivo [`tests/test_senha.py`](../tests/test_senha.py) · unitário · 7 funções · 10 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_senha_valida`](../tests/test_senha.py#L13)
- [`test_senha_fraca`](../tests/test_senha.py#L26) · 4 cenários
- [`test_hash_nao_guarda_a_senha_e_confere`](../tests/test_senha.py#L31)
- [`test_senha_errada_nao_confere`](../tests/test_senha.py#L39)
- [`test_hash_invalido_nao_confere`](../tests/test_senha.py#L43)
- [`test_mesma_senha_gera_hashes_diferentes`](../tests/test_senha.py#L47)
- [`test_verificacao_falsa_nao_levanta_erro`](../tests/test_senha.py#L51)

</details>

### test_token

Arquivo [`tests/test_token.py`](../tests/test_token.py) · unitário · 12 funções · 16 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_token_devolve_o_id_do_usuario`](../tests/test_token.py#L17)
- [`test_token_expira_no_prazo_configurado`](../tests/test_token.py#L23)
- [`test_token_vencido`](../tests/test_token.py#L30)
- [`test_token_assinado_com_outra_chave`](../tests/test_token.py#L36)
- [`test_token_adulterado`](../tests/test_token.py#L43)
- [`test_token_sem_expiracao`](../tests/test_token.py#L51)
- [`test_token_com_id_invalido`](../tests/test_token.py#L55)
- [`test_texto_qualquer_nao_e_token`](../tests/test_token.py#L61)
- [`test_token_carrega_a_versao_da_sessao`](../tests/test_token.py#L65)
- [`test_token_sem_versao_vale_como_zero`](../tests/test_token.py#L72)
- [`test_versao_de_sessao_que_nao_e_inteiro`](../tests/test_token.py#L80) · 5 cenários
- [`test_segundos_restantes`](../tests/test_token.py#L86)

</details>

### test_token_usuario

Arquivo [`tests/test_token_usuario.py`](../tests/test_token_usuario.py) · unitário · 4 funções · 8 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_emitir_invalida_tokens_anteriores_antes_de_salvar_o_hash`](../tests/test_token_usuario.py#L45) · 2 cenários
- [`test_consumir_busca_por_hash_e_finalidade_com_trava`](../tests/test_token_usuario.py#L75)
- [`test_tokens_indisponiveis_falham_sem_gravar`](../tests/test_token_usuario.py#L98) · 4 cenários
- [`test_consumir_reavalia_o_uso_apos_atualizar_o_registro`](../tests/test_token_usuario.py#L112)

</details>

### test_conteudo_institucional

Arquivo [`tests/test_conteudo_institucional.py`](../tests/test_conteudo_institucional.py) · integração · 73 funções · 219 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_sem_token_recebe_401`](../tests/test_conteudo_institucional.py#L139) · 24 cenários
- [`test_perfis_sem_gestao_recebem_403`](../tests/test_conteudo_institucional.py#L145) · 96 cenários
- [`test_conta_pendente_recebe_403`](../tests/test_conteudo_institucional.py#L153)
- [`test_organizador_e_dev_gerenciam`](../tests/test_conteudo_institucional.py#L160) · 2 cenários
- [`test_edicao_inexistente_recebe_404`](../tests/test_conteudo_institucional.py#L170)
- [`test_pagina_publica_abre_sem_login`](../tests/test_conteudo_institucional.py#L179)
- [`test_inscricoes_abertas_segue_a_rn06`](../tests/test_conteudo_institucional.py#L199)
- [`test_edicao_em_rascunho_nao_aparece_para_o_publico`](../tests/test_conteudo_institucional.py#L207)
- [`test_edicao_inexistente_e_404_no_publico`](../tests/test_conteudo_institucional.py#L216)
- [`test_lista_publica_traz_so_divulgadas_e_pagina`](../tests/test_conteudo_institucional.py#L221)
- [`test_crud_de_hackathon_aceita_descricao_sem_quebrar_o_contrato`](../tests/test_conteudo_institucional.py#L234)
- [`test_apoiador_nasce_nao_publicado_e_so_aparece_depois`](../tests/test_conteudo_institucional.py#L264)
- [`test_apoiadores_agrupados_por_categoria_na_ordem`](../tests/test_conteudo_institucional.py#L277)
- [`test_apoiadores_aparecem_na_pagina_publica`](../tests/test_conteudo_institucional.py#L289)
- [`test_listar_apoiadores_filtra_e_pagina`](../tests/test_conteudo_institucional.py#L295)
- [`test_editar_apoiador_limpa_links_e_muda_a_ordem`](../tests/test_conteudo_institucional.py#L314)
- [`test_editar_apoiador_recusa_nulo`](../tests/test_conteudo_institucional.py#L332) · 4 cenários
- [`test_excluir_apoiador`](../tests/test_conteudo_institucional.py#L342)
- [`test_item_de_outra_edicao_nao_e_encontrado`](../tests/test_conteudo_institucional.py#L349)
- [`test_logo_fora_da_politica`](../tests/test_conteudo_institucional.py#L381) · 11 cenários
- [`test_espacos_e_quebras_nas_pontas_do_link_sao_aparados`](../tests/test_conteudo_institucional.py#L391)
- [`test_site_fora_da_politica`](../tests/test_conteudo_institucional.py#L403) · 3 cenários
- [`test_logo_aceita_imagens`](../tests/test_conteudo_institucional.py#L414) · 6 cenários
- [`test_a_api_nao_aceita_arquivo`](../tests/test_conteudo_institucional.py#L428)
- [`test_faq_so_publicadas_e_na_ordem`](../tests/test_conteudo_institucional.py#L448)
- [`test_reordenar_faq`](../tests/test_conteudo_institucional.py#L461)
- [`test_reordenar_exige_todas_as_perguntas`](../tests/test_conteudo_institucional.py#L474)
- [`test_editar_e_excluir_pergunta`](../tests/test_conteudo_institucional.py#L493)
- [`test_pergunta_invalida`](../tests/test_conteudo_institucional.py#L521) · 4 cenários
- [`test_listar_faq_filtra_e_pagina`](../tests/test_conteudo_institucional.py#L525)
- [`test_criacoes_simultaneas_recebem_posicoes_distintas`](../tests/test_conteudo_institucional.py#L537)
- [`test_reordenacoes_simultaneas_deixam_uma_ordem_valida`](../tests/test_conteudo_institucional.py#L546)
- [`test_cronograma_traz_as_datas_do_edital_em_ordem_e_destaca_a_atual`](../tests/test_conteudo_institucional.py#L574)
- [`test_cronograma_segue_as_datas_do_hackathon`](../tests/test_conteudo_institucional.py#L598)
- [`test_cronograma_sem_datas_do_edital_comeca_vazio`](../tests/test_conteudo_institucional.py#L613)
- [`test_fases_publicadas_entram_em_ordem_cronologica`](../tests/test_conteudo_institucional.py#L617)
- [`test_fase_atual_e_destacada`](../tests/test_conteudo_institucional.py#L632)
- [`test_cronograma_aparece_na_pagina_publica`](../tests/test_conteudo_institucional.py#L646)
- [`test_fase_com_fim_antes_do_inicio`](../tests/test_conteudo_institucional.py#L652)
- [`test_editar_fase_valida_o_periodo_final`](../tests/test_conteudo_institucional.py#L662)
- [`test_fase_sem_fuso_vale_como_utc_e_com_fuso_e_convertida`](../tests/test_conteudo_institucional.py#L676)
- [`test_fase_invalida`](../tests/test_conteudo_institucional.py#L694) · 3 cenários
- [`test_excluir_fase`](../tests/test_conteudo_institucional.py#L698)
- [`test_rascunho_nao_aparece_para_o_publico`](../tests/test_conteudo_institucional.py#L728)
- [`test_publicar_torna_vigente_e_mostra_a_data`](../tests/test_conteudo_institucional.py#L743)
- [`test_nova_versao_substitui_a_vigente`](../tests/test_conteudo_institucional.py#L760)
- [`test_publicar_de_novo_a_vigente_nao_muda_nada`](../tests/test_conteudo_institucional.py#L776)
- [`test_versao_substituida_nao_volta_a_vigorar`](../tests/test_conteudo_institucional.py#L785)
- [`test_versao_publicada_e_imutavel`](../tests/test_conteudo_institucional.py#L793)
- [`test_editar_e_excluir_rascunho`](../tests/test_conteudo_institucional.py#L802)
- [`test_versao_repetida_e_documento_obrigatorio`](../tests/test_conteudo_institucional.py#L823)
- [`test_o_mesmo_numero_vale_em_tipos_e_edicoes_diferentes`](../tests/test_conteudo_institucional.py#L844)
- [`test_publicar_um_tipo_nao_mexe_no_outro`](../tests/test_conteudo_institucional.py#L855)
- [`test_aceite_antigo_continua_ligado_a_versao_aceita`](../tests/test_conteudo_institucional.py#L866)
- [`test_listar_versoes_filtra_e_pagina`](../tests/test_conteudo_institucional.py#L881)
- [`test_versao_de_outra_edicao_nao_e_encontrada`](../tests/test_conteudo_institucional.py#L897)
- [`test_publicacoes_simultaneas_deixam_uma_unica_vigente`](../tests/test_conteudo_institucional.py#L905)
- [`test_sessao_exige_data_e_local_ou_link`](../tests/test_conteudo_institucional.py#L999)
- [`test_materiais_sao_so_links`](../tests/test_conteudo_institucional.py#L1024)
- [`test_materiais_na_ordem_e_remocao`](../tests/test_conteudo_institucional.py#L1043)
- [`test_materiais_simultaneos_recebem_posicoes_distintas`](../tests/test_conteudo_institucional.py#L1062)
- [`test_editar_sessao_valida_o_resultado_final`](../tests/test_conteudo_institucional.py#L1084)
- [`test_excluir_sessao_leva_os_materiais`](../tests/test_conteudo_institucional.py#L1110)
- [`test_listar_sessoes_filtra_e_pagina`](../tests/test_conteudo_institucional.py#L1134)
- [`test_equipe_aprovada_ve_so_o_publicado`](../tests/test_conteudo_institucional.py#L1149)
- [`test_equipe_nao_aprovada_nao_ve`](../tests/test_conteudo_institucional.py#L1168)
- [`test_quem_nao_tem_equipe_nao_ve`](../tests/test_conteudo_institucional.py#L1179)
- [`test_aprovada_em_outra_edicao_nao_vale`](../tests/test_conteudo_institucional.py#L1189)
- [`test_organizacao_ve_o_treinamento`](../tests/test_conteudo_institucional.py#L1199) · 3 cenários
- [`test_treinamento_sem_login_conta_pendente_e_edicao_inexistente`](../tests/test_conteudo_institucional.py#L1206)
- [`test_sessoes_em_ordem_cronologica`](../tests/test_conteudo_institucional.py#L1218)
- [`test_edicao_com_conteudo_nao_pode_ser_excluida`](../tests/test_conteudo_institucional.py#L1232)
- [`test_swagger_documenta_todas_as_rotas_novas`](../tests/test_conteudo_institucional.py#L1240)

</details>

### test_edital_schemas

Arquivo [`tests/test_edital_schemas.py`](../tests/test_edital_schemas.py) · unitário · 13 funções · 37 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_hackathon_aceita_limites_positivos_inclusive_iguais`](../tests/test_edital_schemas.py#L27) · 3 cenários
- [`test_hackathon_rejeita_limites_zero_ou_invertidos`](../tests/test_edital_schemas.py#L34) · 3 cenários
- [`test_atualizacao_de_hackathon_rejeita_null_em_campo_obrigatorio`](../tests/test_edital_schemas.py#L40) · 3 cenários
- [`test_patch_vazio_preserva_diferenca_entre_campo_omitido_e_null`](../tests/test_edital_schemas.py#L48) · 2 cenários
- [`test_tema_normaliza_textos_e_ordena_ods_sem_repeticao`](../tests/test_edital_schemas.py#L52)
- [`test_tema_rejeita_ods_vazios_ou_fora_do_intervalo`](../tests/test_edital_schemas.py#L61) · 4 cenários
- [`test_atualizacao_de_tema_rejeita_null_em_campo_obrigatorio`](../tests/test_edital_schemas.py#L69) · 4 cenários
- [`test_peso_da_rubrica_e_decimal_com_duas_casas`](../tests/test_edital_schemas.py#L76)
- [`test_peso_rejeita_valores_invalidos_ou_precisao_excessiva`](../tests/test_edital_schemas.py#L84) · 6 cenários
- [`test_escala_da_rubrica_precisa_ser_crescente_e_respeitar_limites`](../tests/test_edital_schemas.py#L92) · 4 cenários
- [`test_rubrica_rejeita_nomes_repetidos_apos_normalizacao`](../tests/test_edital_schemas.py#L98) · 3 cenários
- [`test_rascunho_de_rubrica_aceita_lista_vazia`](../tests/test_edital_schemas.py#L103)
- [`test_rubrica_aceita_no_maximo_50_criterios`](../tests/test_edital_schemas.py#L108) · 2 cenários

</details>

### test_hackathon

Arquivo [`tests/test_hackathon.py`](../tests/test_hackathon.py) · misto · 3 funções · 28 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_periodo_compativel_com_utc_com_ou_sem_fuso`](../tests/test_hackathon.py#L23) · 20 cenários · unitário
- [`test_selecao_respeita_periodo_do_edital`](../tests/test_hackathon.py#L38) · 7 cenários · integração
- [`test_selecao_recusa_ambiguidade_e_ignora_edicoes_fora_do_periodo`](../tests/test_hackathon.py#L57) · integração

</details>

### test_hackathons_admin

Arquivo [`tests/test_hackathons_admin.py`](../tests/test_hackathons_admin.py) · integração · 18 funções · 30 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_organizador_e_dev_cadastram_hackathon`](../tests/test_hackathons_admin.py#L74) · 2 cenários
- [`test_datas_com_fuso_sao_gravadas_em_utc`](../tests/test_hackathons_admin.py#L87)
- [`test_cadastro_so_com_nome`](../tests/test_hackathons_admin.py#L93)
- [`test_outros_perfis_nao_cadastram_hackathon`](../tests/test_hackathons_admin.py#L102) · 3 cenários
- [`test_cadastro_exige_token`](../tests/test_hackathons_admin.py#L107)
- [`test_cadastro_valida_campos`](../tests/test_hackathons_admin.py#L132) · 7 cenários
- [`test_edicao_altera_apenas_os_campos_enviados`](../tests/test_hackathons_admin.py#L136)
- [`test_edicao_valida_com_os_valores_ja_gravados`](../tests/test_hackathons_admin.py#L151)
- [`test_edicao_nao_aceita_null_em_campo_obrigatorio`](../tests/test_hackathons_admin.py#L167) · 3 cenários
- [`test_edicao_de_hackathon_inexistente`](../tests/test_hackathons_admin.py#L172)
- [`test_participante_nao_edita_nem_exclui`](../tests/test_hackathons_admin.py#L176)
- [`test_exclui_hackathon_sem_dados`](../tests/test_hackathons_admin.py#L187) · 2 cenários
- [`test_nao_exclui_hackathon_com_dados_ligados`](../tests/test_hackathons_admin.py#L196)
- [`test_exclusao_de_hackathon_inexistente`](../tests/test_hackathons_admin.py#L209)
- [`test_qualquer_conta_ativa_lista_hackathons`](../tests/test_hackathons_admin.py#L213)
- [`test_consulta_hackathon_por_id`](../tests/test_hackathons_admin.py#L229)
- [`test_vitrine_e_publica_e_esconde_rascunhos`](../tests/test_hackathons_admin.py#L241)
- [`test_hackathon_guarda_descricao_e_local`](../tests/test_hackathons_admin.py#L269)

</details>

### test_organizacao_security

Arquivo [`tests/test_organizacao_security.py`](../tests/test_organizacao_security.py) · unitário · 4 funções · 34 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_gestor_do_hackathon_valida_diretamente_a_edicao`](../tests/test_organizacao_security.py#L18) · 2 cenários
- [`test_dependencia_confere_a_organizacao_da_edicao_do_recurso`](../tests/test_organizacao_security.py#L46) · 24 cenários
- [`test_gestor_de_mentor_responde_404_para_mentor_de_outra_organizacao`](../tests/test_organizacao_security.py#L81) · 4 cenários
- [`test_atribuicao_consulta_mentor_quando_ha_id`](../tests/test_organizacao_security.py#L106) · 4 cenários

</details>

### test_organizacoes

Arquivo [`tests/test_organizacoes.py`](../tests/test_organizacoes.py) · integração · 15 funções · 30 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_hackathon_criado_pertence_a_organizacao_de_quem_cria`](../tests/test_organizacoes.py#L87)
- [`test_painel_lista_so_os_hackathons_da_organizacao`](../tests/test_organizacoes.py#L99)
- [`test_vitrine_filtra_por_organizacao`](../tests/test_organizacoes.py#L107)
- [`test_organizador_de_outra_organizacao_recebe_403`](../tests/test_organizacoes.py#L133) · 9 cenários
- [`test_dev_gerencia_hackathon_de_qualquer_organizacao`](../tests/test_organizacoes.py#L144)
- [`test_termos_publicados_pela_organizacao_viram_os_vigentes`](../tests/test_organizacoes.py#L156)
- [`test_comprovantes_ficam_na_fila_da_organizacao_dona`](../tests/test_organizacoes.py#L187)
- [`test_usuario_cadastrado_por_gestor_entra_na_organizacao_dele`](../tests/test_organizacoes.py#L212)
- [`test_minha_organizacao`](../tests/test_organizacoes.py#L228)
- [`test_rotas_do_hackathon_e_da_equipe_ficam_na_organizacao`](../tests/test_organizacoes.py#L265) · 8 cenários
- [`test_mentor_pertence_a_organizacao_e_some_para_as_outras`](../tests/test_organizacoes.py#L289)
- [`test_outra_organizacao_nao_convida_mentor_para_o_hackathon_dela`](../tests/test_organizacoes.py#L310)
- [`test_fila_de_emails_mostra_so_a_organizacao`](../tests/test_organizacoes.py#L322)
- [`test_gestao_de_usuarios_fica_na_organizacao`](../tests/test_organizacoes.py#L339)
- [`test_ultimo_organizador_conta_por_organizacao`](../tests/test_organizacoes.py#L356)

</details>

### test_autodeclaracao

Arquivo [`tests/test_autodeclaracao.py`](../tests/test_autodeclaracao.py) · integração · 27 funções · 41 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_participante_declara_estudante_e_profissional`](../tests/test_autodeclaracao.py#L132)
- [`test_declaracao_invalida_da_422_e_nao_grava`](../tests/test_autodeclaracao.py#L185) · 12 cenários
- [`test_mudar_a_declaracao_grava_linha_nova_e_repetir_nao_grava`](../tests/test_autodeclaracao.py#L192)
- [`test_banco_barra_alterar_declaracao_gravada_e_declaracao_incompleta`](../tests/test_autodeclaracao.py#L213)
- [`test_so_o_proprio_usuario_declara_e_a_declaracao_do_lider_nao_vale_para_outro`](../tests/test_autodeclaracao.py#L255)
- [`test_so_participante_declara`](../tests/test_autodeclaracao.py#L270) · 4 cenários
- [`test_sem_token_conta_pendente_e_dev`](../tests/test_autodeclaracao.py#L278)
- [`test_sem_edicao_aberta_nao_declara`](../tests/test_autodeclaracao.py#L289)
- [`test_declaracao_e_comprovacao_ficam_separadas`](../tests/test_autodeclaracao.py#L306)
- [`test_comprovante_de_outro_tipo_nao_comprova_o_vinculo_declarado`](../tests/test_autodeclaracao.py#L330)
- [`test_equipe_de_estudantes_homologa_como_antes`](../tests/test_autodeclaracao.py#L343)
- [`test_equipe_de_profissionais_so_homologa_com_comprovante_profissional`](../tests/test_autodeclaracao.py#L349)
- [`test_equipe_mista_exige_cada_comprovante_do_tipo_de_cada_pessoa`](../tests/test_autodeclaracao.py#L372)
- [`test_politica_da_edicao_dispensa_o_comprovante_do_tipo`](../tests/test_autodeclaracao.py#L391)
- [`test_politica_da_edicao_dispensa_o_comprovante_do_estudante`](../tests/test_autodeclaracao.py#L402)
- [`test_edicao_que_exige_autodeclaracao_so_homologa_com_a_de_todos`](../tests/test_autodeclaracao.py#L409)
- [`test_declarar_tipo_diferente_do_indicado_tira_a_equipe_da_homologacao`](../tests/test_autodeclaracao.py#L424)
- [`test_lider_corrige_o_tipo_indicado_e_resolve_a_divergencia`](../tests/test_autodeclaracao.py#L455)
- [`test_recusa_e_reenvio_do_comprovante_profissional`](../tests/test_autodeclaracao.py#L472)
- [`test_reenvio_simultaneo_gera_um_so_comprovante`](../tests/test_autodeclaracao.py#L510)
- [`test_conferente_ve_o_tipo_e_a_declaracao_ao_lado_do_documento`](../tests/test_autodeclaracao.py#L521)
- [`test_so_conferente_ve_a_fila_de_comprovantes`](../tests/test_autodeclaracao.py#L538)
- [`test_o_link_do_documento_so_chega_ao_dono_e_ao_conferente`](../tests/test_autodeclaracao.py#L553)
- [`test_organizador_configura_a_politica_de_verificacao`](../tests/test_autodeclaracao.py#L582)
- [`test_declaracoes_simultaneas_iguais_viram_uma_e_diferentes_viram_duas`](../tests/test_autodeclaracao.py#L600)
- [`test_migration_comprovante_por_tipo_e_defaults_legados`](../tests/test_autodeclaracao.py#L616)
- [`test_swagger_documenta_a_autodeclaracao`](../tests/test_autodeclaracao.py#L653)

</details>

### test_cadastro_equipe_integrantes

Arquivo [`tests/test_cadastro_equipe_integrantes.py`](../tests/test_cadastro_equipe_integrantes.py) · integração · 27 funções · 43 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_equipe_com_conta_existente_e_pessoa_sem_conta`](../tests/test_cadastro_equipe_integrantes.py#L87)
- [`test_email_de_quem_tem_conta_vai_para_convites_e_de_quem_nao_tem_traz_o_link`](../tests/test_cadastro_equipe_integrantes.py#L109)
- [`test_convite_avulso_e_composicao_substituida_tambem_geram_o_link`](../tests/test_cadastro_equipe_integrantes.py#L132)
- [`test_cadastro_pelo_link_cria_conta_pendente_com_a_propria_senha`](../tests/test_cadastro_equipe_integrantes.py#L153)
- [`test_conta_pendente_aceita_o_convite_e_a_equipe_segue_nao_homologada`](../tests/test_cadastro_equipe_integrantes.py#L183)
- [`test_cadastro_associa_o_convite_a_conta_e_mostra_na_central`](../tests/test_cadastro_equipe_integrantes.py#L208)
- [`test_cadastro_com_comprovante_opcional_registra_o_documento`](../tests/test_cadastro_equipe_integrantes.py#L222)
- [`test_comprovante_do_cadastro_por_convite_vale_para_o_tipo_indicado_pelo_lider`](../tests/test_cadastro_equipe_integrantes.py#L235)
- [`test_o_link_serve_uma_vez_so`](../tests/test_cadastro_equipe_integrantes.py#L266)
- [`test_link_que_nao_vale_mais_da_a_mesma_resposta_400`](../tests/test_cadastro_equipe_integrantes.py#L284) · 6 cenários
- [`test_se_ja_existe_conta_com_o_email_do_convite_responde_409`](../tests/test_cadastro_equipe_integrantes.py#L319)
- [`test_cadastro_por_convite_invalido_da_422_e_nao_gasta_o_link`](../tests/test_cadastro_equipe_integrantes.py#L364) · 11 cenários
- [`test_token_curto_demais_da_422`](../tests/test_cadastro_equipe_integrantes.py#L375)
- [`test_dois_cadastros_simultaneos_com_o_mesmo_link_criam_uma_conta`](../tests/test_cadastro_equipe_integrantes.py#L380)
- [`test_cadastro_publico_associa_convites_pendentes`](../tests/test_cadastro_equipe_integrantes.py#L399)
- [`test_conta_pendente_nao_cria_equipe_nem_convida_mas_mentor_sem_ativacao_segue_barrado`](../tests/test_cadastro_equipe_integrantes.py#L429)
- [`test_o_token_nao_aparece_em_nenhuma_resposta_da_api`](../tests/test_cadastro_equipe_integrantes.py#L447)
- [`test_repetir_o_pedido_com_a_mesma_chave_devolve_a_equipe_sem_duplicar`](../tests/test_cadastro_equipe_integrantes.py#L470)
- [`test_chave_reutilizada_com_outro_conteudo_da_409`](../tests/test_cadastro_equipe_integrantes.py#L486)
- [`test_o_hash_ignora_maiusculas_nos_emails`](../tests/test_cadastro_equipe_integrantes.py#L496)
- [`test_sem_a_chave_o_comportamento_e_o_de_antes`](../tests/test_cadastro_equipe_integrantes.py#L507)
- [`test_a_chave_vale_por_lider`](../tests/test_cadastro_equipe_integrantes.py#L513)
- [`test_chave_vazia_ou_longa_demais_da_422`](../tests/test_cadastro_equipe_integrantes.py#L524) · 2 cenários
- [`test_pedidos_simultaneos_com_a_mesma_chave_geram_uma_equipe`](../tests/test_cadastro_equipe_integrantes.py#L529)
- [`test_falha_na_validacao_nao_consome_a_chave`](../tests/test_cadastro_equipe_integrantes.py#L546)
- [`test_swagger_documenta_o_cadastro_por_convite_e_a_chave`](../tests/test_cadastro_equipe_integrantes.py#L560)
- [`test_migration_token_do_convite_e_idempotencia_da_equipe`](../tests/test_cadastro_equipe_integrantes.py#L575)

</details>

### test_cadastro_por_hackathon

Arquivo [`tests/test_cadastro_por_hackathon.py`](../tests/test_cadastro_por_hackathon.py) · integração · 22 funções · 41 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_aprovacao_nao_comprova_nem_homologa_outra_edicao`](../tests/test_cadastro_por_hackathon.py#L139)
- [`test_declaracao_divergente_so_retira_homologacao_da_edicao_escolhida`](../tests/test_cadastro_por_hackathon.py#L172)
- [`test_cadastro_explicito_usa_edicao_escolhida`](../tests/test_cadastro_por_hackathon.py#L195) · 2 cenários
- [`test_fluxos_sem_id_recusam_ambiguidade_sem_gravar`](../tests/test_cadastro_por_hackathon.py#L207)
- [`test_escritas_validam_id_status_e_periodo_sem_fallback`](../tests/test_cadastro_por_hackathon.py#L236) · 6 cenários
- [`test_declaracoes_historico_e_comprovantes_ficam_na_edicao`](../tests/test_cadastro_por_hackathon.py#L273)
- [`test_consulta_historica_explicita_nao_reabre_prazo`](../tests/test_cadastro_por_hackathon.py#L299) · 3 cenários
- [`test_consulta_id_inexistente_e_rascunho`](../tests/test_cadastro_por_hackathon.py#L313)
- [`test_privacidade_do_rascunho_reutiliza_autorizacao_publica`](../tests/test_cadastro_por_hackathon.py#L321) · 5 cenários
- [`test_id_da_edicao_nao_da_acesso_a_dados_de_terceiros`](../tests/test_cadastro_por_hackathon.py#L351)
- [`test_organizacao_so_valida_sua_edicao_e_dev_preserva_excecao`](../tests/test_cadastro_por_hackathon.py#L377) · 2 cenários
- [`test_cliente_legado_com_uma_edicao_usa_a_unica_e_nao_a_mais_recente`](../tests/test_cadastro_por_hackathon.py#L413)
- [`test_falha_no_cadastro_reverte_conta_comprovante_e_registros`](../tests/test_cadastro_por_hackathon.py#L448) · 3 cenários
- [`test_sem_edicoes_abertas_preserva_409_nos_quatro_contratos`](../tests/test_cadastro_por_hackathon.py#L497)
- [`test_email_existente_nao_cria_conta_nem_comprovante_em_outra_edicao`](../tests/test_cadastro_por_hackathon.py#L515)
- [`test_consulta_historica_respeita_prazo_encerrado_mesmo_com_status_inscricoes`](../tests/test_cadastro_por_hackathon.py#L530)
- [`test_cadastros_concorrentes_em_edicoes_diferentes_nao_duplicam_conta`](../tests/test_cadastro_por_hackathon.py#L540)
- [`test_comprovantes_concorrentes_respeitam_unicidade_por_edicao`](../tests/test_cadastro_por_hackathon.py#L560)
- [`test_declaracoes_concorrentes_nao_deduplicam_entre_edicoes`](../tests/test_cadastro_por_hackathon.py#L574)
- [`test_cadastro_por_convite_ignora_outras_edicoes_abertas`](../tests/test_cadastro_por_hackathon.py#L591) · 2 cenários
- [`test_uuid_invalido_retorna_422`](../tests/test_cadastro_por_hackathon.py#L631) · 4 cenários
- [`test_openapi_documenta_contratos_por_edicao`](../tests/test_cadastro_por_hackathon.py#L645)

</details>

### test_cadastro_profissional

Arquivo [`tests/test_cadastro_profissional.py`](../tests/test_cadastro_profissional.py) · integração · 4 funções · 9 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_profissional_se_cadastra_com_organizacao_e_cargo`](../tests/test_cadastro_profissional.py#L17)
- [`test_estudante_continua_como_antes`](../tests/test_cadastro_profissional.py#L57)
- [`test_campos_do_tipo_errados_dao_422`](../tests/test_cadastro_profissional.py#L88) · 6 cenários
- [`test_falha_no_cadastro_do_profissional_nao_deixa_declaracao`](../tests/test_cadastro_profissional.py#L97)

</details>

### test_comprovantes

Arquivo [`tests/test_comprovantes.py`](../tests/test_comprovantes.py) · integração · 25 funções · 35 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_fila_traz_so_os_pendentes_com_o_arquivo_e_quem_enviou`](../tests/test_comprovantes.py#L74)
- [`test_fila_ordena_do_mais_antigo_e_pagina`](../tests/test_comprovantes.py#L103)
- [`test_fila_filtra_por_situacao`](../tests/test_comprovantes.py#L114) · 2 cenários
- [`test_fila_filtra_por_hackathon`](../tests/test_comprovantes.py#L121)
- [`test_quem_confere_comprovantes`](../tests/test_comprovantes.py#L134) · 3 cenários
- [`test_outros_perfis_nao_conferem`](../tests/test_comprovantes.py#L141) · 3 cenários
- [`test_fila_exige_login`](../tests/test_comprovantes.py#L154)
- [`test_aprovar_registra_quem_validou_e_ativa_a_conta`](../tests/test_comprovantes.py#L161)
- [`test_aprovar_duas_vezes_ou_decidir_o_decidido`](../tests/test_comprovantes.py#L179)
- [`test_comprovante_inexistente`](../tests/test_comprovantes.py#L188)
- [`test_recusar_exige_o_motivo`](../tests/test_comprovantes.py#L196)
- [`test_recusar_guarda_o_motivo_e_mantem_a_conta_pendente`](../tests/test_comprovantes.py#L204)
- [`test_recusado_ve_o_motivo_com_a_conta_pendente_e_reenvia`](../tests/test_comprovantes.py#L220)
- [`test_reenvio_aprovado_ativa_a_conta`](../tests/test_comprovantes.py#L249)
- [`test_envio_para_hackathon_fora_do_periodo_preserva_historico`](../tests/test_comprovantes.py#L263)
- [`test_envio_para_hackathon_inexistente`](../tests/test_comprovantes.py#L280)
- [`test_comprovantes_de_hackathons_diferentes_sao_independentes`](../tests/test_comprovantes.py#L292)
- [`test_aprovacao_de_comprovante_continua_permitida_apos_prazo`](../tests/test_comprovantes.py#L311)
- [`test_nao_reenvia_com_comprovante_pendente_ou_aprovado`](../tests/test_comprovantes.py#L326) · 2 cenários
- [`test_quem_nunca_enviou_comprovante_pode_enviar`](../tests/test_comprovantes.py#L339)
- [`test_reenvio_valida_o_link_como_no_cadastro`](../tests/test_comprovantes.py#L362) · 5 cenários
- [`test_rotas_do_proprio_comprovante_exigem_login`](../tests/test_comprovantes.py#L375)
- [`test_cada_um_ve_so_os_seus_comprovantes`](../tests/test_comprovantes.py#L380)
- [`test_reenvio_ignora_edicoes_mais_recentes_fora_do_periodo`](../tests/test_comprovantes.py#L394)
- [`test_reenvio_sem_edicao_aberta_preserva_erro_e_historico`](../tests/test_comprovantes.py#L410)

</details>

### test_edicao_participante

Arquivo [`tests/test_edicao_participante.py`](../tests/test_edicao_participante.py) · unitário · 3 funções · 6 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_sem_id_usa_a_selecao_legada`](../tests/test_edicao_participante.py#L22) · 2 cenários
- [`test_id_explicito_consulta_edicao_autorizada`](../tests/test_edicao_participante.py#L48) · 3 cenários
- [`test_edicao_inacessivel_preserva_404_sem_revelar_o_prazo`](../tests/test_edicao_participante.py#L72)

</details>

### test_homologacao_service

Arquivo [`tests/test_homologacao_service.py`](../tests/test_homologacao_service.py) · unitário · 9 funções · 28 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_equipe_completa_e_homologavel_e_mostra_lider_primeiro_sem_gravar`](../tests/test_homologacao_service.py#L94)
- [`test_comprovante_pendente_bloqueia_homologacao_mas_permite_conclusao`](../tests/test_homologacao_service.py#L116) · 3 cenários
- [`test_comprovante_profissional_segue_a_politica_da_edicao`](../tests/test_homologacao_service.py#L134) · 2 cenários
- [`test_requisito_do_integrante_bloqueia_conclusao`](../tests/test_homologacao_service.py#L162) · 3 cenários
- [`test_exige_publicacao_dos_dois_tipos_de_termo`](../tests/test_homologacao_service.py#L181) · 2 cenários
- [`test_tamanho_da_equipe_respeita_limites_do_hackathon`](../tests/test_homologacao_service.py#L199) · 2 cenários
- [`test_prazo_encerrado_bloqueia_somente_equipe_em_formacao`](../tests/test_homologacao_service.py#L213) · 3 cenários
- [`test_painel_considera_apenas_convite_mais_recente_por_email`](../tests/test_homologacao_service.py#L227) · 4 cenários
- [`test_reavaliacao_aplica_transicoes_e_preserva_estados_nao_elegiveis`](../tests/test_homologacao_service.py#L253) · 8 cenários

</details>

### test_inscricao

Arquivo [`tests/test_inscricao.py`](../tests/test_inscricao.py) · integração · 33 funções · 37 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_lider_conclui_com_tres_integrantes_e_recebe_a_confirmacao`](../tests/test_inscricao.py#L97)
- [`test_aceita_os_limites_de_tres_e_cinco_integrantes`](../tests/test_inscricao.py#L117) · 2 cenários
- [`test_conclusao_homologa_quando_todos_ja_tem_vinculo_aprovado`](../tests/test_inscricao.py#L122)
- [`test_so_o_lider_conclui`](../tests/test_inscricao.py#L134) · 2 cenários
- [`test_dev_conclui_pela_excecao_tecnica`](../tests/test_inscricao.py#L143)
- [`test_sem_token_e_equipe_inexistente`](../tests/test_inscricao.py#L150)
- [`test_conta_pendente_do_lider_nao_conclui`](../tests/test_inscricao.py#L158)
- [`test_exige_o_minimo_de_integrantes`](../tests/test_inscricao.py#L167)
- [`test_exige_o_maximo_de_integrantes`](../tests/test_inscricao.py#L178)
- [`test_o_tamanho_vem_do_hackathon`](../tests/test_inscricao.py#L188)
- [`test_o_lider_tambem_precisa_ter_aceitado_os_termos`](../tests/test_inscricao.py#L197)
- [`test_termos_desatualizados_de_um_integrante_bloqueiam`](../tests/test_inscricao.py#L209)
- [`test_sem_termos_publicados_nao_conclui`](../tests/test_inscricao.py#L219)
- [`test_conta_desativada_de_integrante_bloqueia`](../tests/test_inscricao.py#L231)
- [`test_fora_do_prazo_pelo_status`](../tests/test_inscricao.py#L241)
- [`test_fora_do_prazo_pelas_datas_do_edital`](../tests/test_inscricao.py#L249)
- [`test_dentro_das_datas_do_edital`](../tests/test_inscricao.py#L260)
- [`test_nao_conclui_duas_vezes`](../tests/test_inscricao.py#L271)
- [`test_conclusao_fecha_a_composicao_e_cancela_convites_em_aberto`](../tests/test_inscricao.py#L282)
- [`test_aprovar_o_ultimo_comprovante_homologa_a_equipe`](../tests/test_inscricao.py#L299)
- [`test_recusar_um_comprovante_nao_homologa`](../tests/test_inscricao.py#L323)
- [`test_homologacao_volta_a_pendente_e_retorna_quando_os_requisitos_voltam`](../tests/test_inscricao.py#L341)
- [`test_reavaliacao_ignora_equipes_em_formacao_e_nao_homologadas`](../tests/test_inscricao.py#L383)
- [`test_so_o_organizador_reavalia`](../tests/test_inscricao.py#L397) · 3 cenários
- [`test_reavaliar_hackathon_inexistente`](../tests/test_inscricao.py#L405)
- [`test_painel_mostra_cada_integrante_e_o_que_falta`](../tests/test_inscricao.py#L418)
- [`test_painel_lista_o_que_impede_a_conclusao`](../tests/test_inscricao.py#L470)
- [`test_painel_depois_da_conclusao_traz_o_protocolo`](../tests/test_inscricao.py#L480)
- [`test_painel_da_equipe_homologada_nao_tem_pendencias`](../tests/test_inscricao.py#L493)
- [`test_so_o_lider_ve_a_acao_de_concluir`](../tests/test_inscricao.py#L504)
- [`test_painel_restrito_a_integrantes`](../tests/test_inscricao.py#L513)
- [`test_painel_nao_expoe_dados_alem_do_necessario`](../tests/test_inscricao.py#L524)
- [`test_banco_barra_segundo_protocolo_de_inscricao_da_mesma_equipe`](../tests/test_inscricao.py#L536)

</details>

### test_inscricao_service

Arquivo [`tests/test_inscricao_service.py`](../tests/test_inscricao_service.py) · unitário · 4 funções · 13 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_conclusao_emite_protocolo_e_informa_se_a_equipe_foi_homologada`](../tests/test_inscricao_service.py#L79) · 2 cenários
- [`test_impedimentos_da_inscricao_nao_geram_protocolo_nem_gravacao`](../tests/test_inscricao_service.py#L126) · 4 cenários
- [`test_falha_na_conclusao_solicita_rollback_e_preserva_erro_original`](../tests/test_inscricao_service.py#L168) · 6 cenários
- [`test_falha_na_reavaliacao_do_hackathon_solicita_rollback`](../tests/test_inscricao_service.py#L183)

</details>

### test_somente_leitura

Arquivo [`tests/test_somente_leitura.py`](../tests/test_somente_leitura.py) · integração · 9 funções · 9 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_equipe_reprovada_recebe_409_em_cada_rota_de_escrita`](../tests/test_somente_leitura.py#L117)
- [`test_dev_tambem_e_bloqueado_nas_rotas_de_escrita`](../tests/test_somente_leitura.py#L127)
- [`test_equipe_reprovada_continua_consultando`](../tests/test_somente_leitura.py#L140)
- [`test_equipe_aprovada_e_hackathon_sem_homologacao_nao_sao_bloqueados`](../tests/test_somente_leitura.py#L165)
- [`test_equipe_sem_proposta_enviada_nao_e_bloqueada`](../tests/test_somente_leitura.py#L177)
- [`test_homologacao_cria_notificacao_para_todos_os_integrantes`](../tests/test_somente_leitura.py#L200)
- [`test_falha_ao_notificar_desfaz_a_homologacao`](../tests/test_somente_leitura.py#L235)
- [`test_integrante_le_o_proprio_resultado_e_parecer`](../tests/test_somente_leitura.py#L251)
- [`test_outra_equipe_nao_acessa_o_resultado`](../tests/test_somente_leitura.py#L278)

</details>

### test_categoria_equipe

Arquivo [`tests/test_categoria_equipe.py`](../tests/test_categoria_equipe.py) · unitário · 12 funções · 30 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_coerencia_entre_categoria_e_tipos`](../tests/test_categoria_equipe.py#L59) · 8 cenários
- [`test_tipo_padrao_e_compatibilidade`](../tests/test_categoria_equipe.py#L63)
- [`test_resolver_tipo`](../tests/test_categoria_equipe.py#L72)
- [`test_politica_padrao_libera_as_tres_categorias_e_pode_restringir`](../tests/test_categoria_equipe.py#L84)
- [`test_composicao_valida_devolve_tipos_normalizados`](../tests/test_categoria_equipe.py#L99)
- [`test_composicao_invalida_da_422`](../tests/test_categoria_equipe.py#L126) · 7 cenários
- [`test_email_repetido_e_lider_na_lista_dao_422`](../tests/test_categoria_equipe.py#L139)
- [`test_categoria_que_a_edicao_nao_aceita_da_422_com_as_aceitas`](../tests/test_categoria_equipe.py#L165)
- [`test_limites_seguem_a_configuracao_da_edicao`](../tests/test_categoria_equipe.py#L180)
- [`test_lider_nao_envia_termos_nem_comprovante_de_terceiros`](../tests/test_categoria_equipe.py#L197) · 6 cenários
- [`test_teto_de_integrantes_por_pedido`](../tests/test_categoria_equipe.py#L209)
- [`test_hackathon_precisa_aceitar_ao_menos_uma_categoria`](../tests/test_categoria_equipe.py#L215)

</details>

### test_convite_service

Arquivo [`tests/test_convite_service.py`](../tests/test_convite_service.py) · unitário · 9 funções · 16 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_envio_normaliza_email_e_vincula_usuario_quando_existente`](../tests/test_convite_service.py#L93) · 2 cenários
- [`test_envio_conta_convites_pendentes_para_impedir_excesso_de_integrantes`](../tests/test_convite_service.py#L122) · 2 cenários
- [`test_envio_exige_funcao_de_lider`](../tests/test_convite_service.py#L138) · 2 cenários
- [`test_aceite_nao_revela_convite_ausente_ou_de_outra_pessoa`](../tests/test_convite_service.py#L160) · 2 cenários
- [`test_convite_respondido_nao_pode_ser_aceito`](../tests/test_convite_service.py#L179) · 3 cenários
- [`test_aceite_registra_termos_integrante_e_resposta_na_mesma_sessao`](../tests/test_convite_service.py#L190)
- [`test_falha_nos_termos_nao_adiciona_integrante_nem_confirma_aceite`](../tests/test_convite_service.py#L213) · 2 cenários
- [`test_conflito_de_vinculo_no_commit_exige_rollback_e_retorna_409`](../tests/test_convite_service.py#L226)
- [`test_falha_ao_criar_convite_nao_confirma_transacao`](../tests/test_convite_service.py#L240)

</details>

### test_convites

Arquivo [`tests/test_convites.py`](../tests/test_convites.py) · integração · 46 funções · 66 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_convites_respeitam_periodo_do_edital`](../tests/test_convites.py#L147) · 21 cenários
- [`test_cancelamento_continua_permitido_apos_prazo`](../tests/test_convites.py#L178)
- [`test_aceite_de_termos_continua_permitido_apos_prazo`](../tests/test_convites.py#L194)
- [`test_lider_convida_por_nome_e_email`](../tests/test_convites.py#L213)
- [`test_convite_a_quem_ja_tem_conta_guarda_o_usuario`](../tests/test_convites.py#L225)
- [`test_sem_token_nao_convida`](../tests/test_convites.py#L234)
- [`test_quem_nao_e_da_equipe_nao_convida`](../tests/test_convites.py#L242)
- [`test_integrante_que_nao_e_lider_nao_convida`](../tests/test_convites.py#L248)
- [`test_conta_pendente_nao_convida`](../tests/test_convites.py#L255)
- [`test_equipe_inexistente`](../tests/test_convites.py#L263)
- [`test_email_invalido_e_nome_vazio`](../tests/test_convites.py#L273)
- [`test_convite_repetido_para_o_mesmo_email`](../tests/test_convites.py#L289)
- [`test_nao_convida_quem_ja_e_integrante`](../tests/test_convites.py#L296)
- [`test_respeita_o_maximo_de_integrantes_contando_pendentes`](../tests/test_convites.py#L300)
- [`test_nao_convida_fora_do_periodo_de_inscricoes`](../tests/test_convites.py#L308)
- [`test_equipe_lista_os_convites_com_o_estado`](../tests/test_convites.py#L317)
- [`test_quem_nao_e_da_equipe_nao_ve_os_convites`](../tests/test_convites.py#L331)
- [`test_convidado_ve_o_convite_no_painel`](../tests/test_convites.py#L341)
- [`test_convite_respondido_sai_do_painel`](../tests/test_convites.py#L355)
- [`test_aceitar_entra_na_equipe_e_registra_os_termos`](../tests/test_convites.py#L365)
- [`test_aceitar_mantem_a_versao_dos_termos_aceita`](../tests/test_convites.py#L394)
- [`test_aceitar_duas_vezes`](../tests/test_convites.py#L408)
- [`test_aceitar_exige_os_dois_termos`](../tests/test_convites.py#L415)
- [`test_aceitar_sem_enviar_termos`](../tests/test_convites.py#L425)
- [`test_aceitar_versao_que_deixou_de_ser_vigente`](../tests/test_convites.py#L431)
- [`test_aceitar_sem_termos_publicados`](../tests/test_convites.py#L441)
- [`test_nao_aceita_quem_ja_esta_em_outra_equipe`](../tests/test_convites.py#L448)
- [`test_pode_aceitar_quem_esta_em_equipe_de_outro_hackathon`](../tests/test_convites.py#L462)
- [`test_nao_aceita_com_a_equipe_cheia`](../tests/test_convites.py#L477)
- [`test_nao_aceita_fora_do_periodo_de_inscricoes`](../tests/test_convites.py#L496)
- [`test_so_o_destinatario_responde`](../tests/test_convites.py#L503)
- [`test_convite_inexistente`](../tests/test_convites.py#L511)
- [`test_responder_exige_login`](../tests/test_convites.py#L515)
- [`test_recusar_libera_a_vaga_e_o_lider_ve`](../tests/test_convites.py#L526)
- [`test_pode_convidar_de_novo_quem_recusou`](../tests/test_convites.py#L539)
- [`test_recusar_duas_vezes`](../tests/test_convites.py#L546)
- [`test_nao_recusa_fora_do_periodo_de_inscricoes`](../tests/test_convites.py#L553)
- [`test_lider_cancela_convite_pendente`](../tests/test_convites.py#L563)
- [`test_so_o_lider_cancela`](../tests/test_convites.py#L575)
- [`test_nao_cancela_convite_ja_aceito`](../tests/test_convites.py#L583)
- [`test_termos_vigentes_para_ler_antes_de_aceitar`](../tests/test_convites.py#L597)
- [`test_termos_de_hackathon_inexistente`](../tests/test_convites.py#L611)
- [`test_aceitar_termos_registra_data_e_versao`](../tests/test_convites.py#L619)
- [`test_aceitar_termos_de_novo_nao_duplica`](../tests/test_convites.py#L632)
- [`test_aceitar_termos_exige_os_dois`](../tests/test_convites.py#L649)
- [`test_aceitar_termos_de_outro_hackathon`](../tests/test_convites.py#L659)

</details>

### test_equipes

Arquivo [`tests/test_equipes.py`](../tests/test_equipes.py) · integração · 28 funções · 83 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_criar_equipe_com_lider_automatico_sem_minimo_ou_termos`](../tests/test_equipes.py#L54)
- [`test_perfis_sem_permissao_nao_criam_equipe`](../tests/test_equipes.py#L74) · 4 cenários
- [`test_perfis_permitidos_criam_equipe_respeitando_regras`](../tests/test_equipes.py#L85) · 2 cenários
- [`test_criar_sem_nome_e_com_maximo_configurado_em_um`](../tests/test_equipes.py#L105)
- [`test_impedir_segundo_vinculo_na_mesma_edicao`](../tests/test_equipes.py#L113) · 3 cenários
- [`test_participar_em_edicoes_diferentes_e_listar_apenas_minhas`](../tests/test_equipes.py#L132)
- [`test_minhas_inclui_integrante_sem_funcao_de_lider`](../tests/test_equipes.py#L147)
- [`test_minhas_sem_vinculo_retorna_lista_vazia`](../tests/test_equipes.py#L163) · 2 cenários
- [`test_consultar_equipe_por_lider`](../tests/test_equipes.py#L170)
- [`test_intruso_nao_consulta_dados_da_equipe`](../tests/test_equipes.py#L177)
- [`test_dev_consulta_e_edita_sem_ser_integrante`](../tests/test_equipes.py#L184)
- [`test_equipe_inexistente`](../tests/test_equipes.py#L194) · 2 cenários
- [`test_criar_com_hackathon_inexistente`](../tests/test_equipes.py#L202)
- [`test_lider_edita_somente_nome_sem_exigir_minimo`](../tests/test_equipes.py#L206)
- [`test_patch_vazio_preserva_equipe_e_nome_nulo_e_permitido`](../tests/test_equipes.py#L227)
- [`test_apenas_lider_edita`](../tests/test_equipes.py#L237) · 2 cenários
- [`test_exigir_login_e_conta_ativa`](../tests/test_equipes.py#L264) · 8 cenários
- [`test_criar_fora_das_inscricoes`](../tests/test_equipes.py#L277) · 6 cenários
- [`test_equipes_respeitam_periodo_do_edital`](../tests/test_equipes.py#L284) · 14 cenários
- [`test_editar_fora_das_inscricoes`](../tests/test_equipes.py#L309) · 6 cenários
- [`test_editar_apenas_em_formacao`](../tests/test_equipes.py#L324) · 3 cenários
- [`test_criacao_rejeita_campos_controlados_pelo_sistema`](../tests/test_equipes.py#L351) · 8 cenários
- [`test_patch_rejeita_campos_controlados_pelo_sistema`](../tests/test_equipes.py#L368) · 7 cenários
- [`test_rejeitar_nome_acima_do_limite`](../tests/test_equipes.py#L379) · 2 cenários
- [`test_rollback_sem_equipe_orfa_quando_unicidade_e_decidida_pelo_banco`](../tests/test_equipes.py#L390)
- [`test_rollback_em_falha_apos_persistir_equipe`](../tests/test_equipes.py#L420)
- [`test_equipe_criada_permite_enviar_e_listar_convites`](../tests/test_equipes.py#L433)
- [`test_swagger_documenta_endpoints_e_rejeicao_de_campos`](../tests/test_equipes.py#L447)

</details>

### test_equipes_categoria

Arquivo [`tests/test_equipes_categoria.py`](../tests/test_equipes_categoria.py) · integração · 34 funções · 49 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_estudantes_em_uma_operacao_com_pendencias_individuais`](../tests/test_equipes_categoria.py#L121)
- [`test_profissionais_sem_tipo_usam_o_da_categoria`](../tests/test_equipes_categoria.py#L156)
- [`test_equipe_mista_com_estudantes_e_profissionais`](../tests/test_equipes_categoria.py#L170)
- [`test_limites_incluem_o_lider`](../tests/test_equipes_categoria.py#L187) · 2 cenários
- [`test_categoria_incoerente_com_os_tipos`](../tests/test_equipes_categoria.py#L214) · 6 cenários
- [`test_total_fora_do_minimo_e_maximo_da_edicao`](../tests/test_equipes_categoria.py#L229) · 3 cenários
- [`test_limites_acompanham_a_configuracao_da_edicao`](../tests/test_equipes_categoria.py#L237)
- [`test_email_repetido_ou_do_proprio_lider_nao_vale`](../tests/test_equipes_categoria.py#L243)
- [`test_lider_nao_aceita_termos_nem_comprovante_em_nome_de_terceiros`](../tests/test_equipes_categoria.py#L273) · 4 cenários
- [`test_valores_invalidos_do_corpo`](../tests/test_equipes_categoria.py#L294) · 3 cenários
- [`test_edicao_que_nao_aceita_a_categoria_responde_422_com_as_aceitas`](../tests/test_equipes_categoria.py#L302)
- [`test_categoria_omitida_vale_estudantes_e_respeita_a_politica`](../tests/test_equipes_categoria.py#L319)
- [`test_organizador_configura_a_politica_e_nao_a_zera`](../tests/test_equipes_categoria.py#L327)
- [`test_categoria_nao_aceita_vira_pendencia_que_bloqueia_a_conclusao`](../tests/test_equipes_categoria.py#L350)
- [`test_lider_que_ja_esta_em_equipe_da_edicao_nao_cria_outra`](../tests/test_equipes_categoria.py#L364)
- [`test_convidado_que_ja_esta_em_outra_equipe_da_edicao_nao_entra`](../tests/test_equipes_categoria.py#L373)
- [`test_aceite_copia_o_tipo_indicado_e_ignora_escolha_do_convidado`](../tests/test_equipes_categoria.py#L391)
- [`test_termos_e_comprovantes_continuam_individuais`](../tests/test_equipes_categoria.py#L404)
- [`test_lider_nao_aceita_o_convite_nem_os_termos_de_outra_pessoa`](../tests/test_equipes_categoria.py#L425)
- [`test_equipe_criada_como_antes_continua_estudantes`](../tests/test_equipes_categoria.py#L451)
- [`test_equipe_legada_inserida_sem_categoria_funciona_como_estudantes`](../tests/test_equipes_categoria.py#L464)
- [`test_convite_avulso_segue_a_categoria`](../tests/test_equipes_categoria.py#L475)
- [`test_composicao_incoerente_barra_a_conclusao_e_aparece_no_painel`](../tests/test_equipes_categoria.py#L503)
- [`test_substituir_adiciona_cancela_e_mantem_quem_ja_entrou`](../tests/test_equipes_categoria.py#L532)
- [`test_substituir_remove_avisa_e_nao_deixa_reconvidar_a_mesma_equipe`](../tests/test_equipes_categoria.py#L550)
- [`test_substituir_muda_categoria_e_tipos_na_mesma_operacao`](../tests/test_equipes_categoria.py#L572)
- [`test_substituir_invalido_nao_altera_nada`](../tests/test_equipes_categoria.py#L602) · 3 cenários
- [`test_substituir_exige_lider_equipe_em_formacao_e_inscricoes_abertas`](../tests/test_equipes_categoria.py#L616)
- [`test_dev_substitui_a_composicao_e_os_convites_saem_em_nome_do_lider`](../tests/test_equipes_categoria.py#L639)
- [`test_consultar_composicao_so_para_integrantes`](../tests/test_equipes_categoria.py#L654)
- [`test_substituir_e_aceitar_ao_mesmo_tempo_nao_se_atrapalham`](../tests/test_equipes_categoria.py#L666)
- [`test_duas_criacoes_simultaneas_do_mesmo_lider_geram_uma_equipe`](../tests/test_equipes_categoria.py#L688)
- [`test_swagger_documenta_a_composicao_e_rejeita_campos_extras`](../tests/test_equipes_categoria.py#L707)
- [`test_migration_preserva_dados_legados_e_barra_politica_vazia`](../tests/test_equipes_categoria.py#L724)

</details>

### test_equipes_publicas

Arquivo [`tests/test_equipes_publicas.py`](../tests/test_equipes_publicas.py) · integração · 2 funções · 2 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_lista_so_as_homologadas_sem_dados_pessoais`](../tests/test_equipes_publicas.py#L47)
- [`test_rascunho_e_inexistente_dao_404`](../tests/test_equipes_publicas.py#L60)

</details>

### test_membros_equipe

Arquivo [`tests/test_membros_equipe.py`](../tests/test_membros_equipe.py) · integração · 28 funções · 107 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_alterar_membros_respeita_periodo_do_edital`](../tests/test_membros_equipe.py#L38) · 14 cenários
- [`test_listar_membros_restritos_a_equipe`](../tests/test_membros_equipe.py#L59) · 3 cenários
- [`test_estranho_nao_lista_membros`](../tests/test_membros_equipe.py#L81) · 3 cenários
- [`test_lider_altera_funcao_sem_mudar_identidade_ou_quantidade`](../tests/test_membros_equipe.py#L88) · 5 cenários
- [`test_patch_vazio_preserva_funcao_e_null_limpa_funcao`](../tests/test_membros_equipe.py#L108)
- [`test_dev_altera_membro_sem_vinculo`](../tests/test_membros_equipe.py#L117) · 2 cenários
- [`test_remover_abaixo_do_minimo_preserva_lider_e_revoga_acesso`](../tests/test_membros_equipe.py#L122)
- [`test_apenas_lider_da_propria_equipe_altera`](../tests/test_membros_equipe.py#L145) · 6 cenários
- [`test_exigir_token_e_conta_ativa`](../tests/test_membros_equipe.py#L165) · 12 cenários
- [`test_nao_rebaixar_lider`](../tests/test_membros_equipe.py#L185) · 10 cenários
- [`test_nao_remover_lider`](../tests/test_membros_equipe.py#L200) · 2 cenários
- [`test_nao_promover_outro_membro_a_lider`](../tests/test_membros_equipe.py#L210) · 2 cenários
- [`test_reenviar_funcao_lider_e_idempotente`](../tests/test_membros_equipe.py#L219)
- [`test_nao_alterar_usuario_de_outra_equipe`](../tests/test_membros_equipe.py#L228) · 2 cenários
- [`test_alteracao_nao_afeta_vinculo_do_mesmo_usuario_em_outra_edicao`](../tests/test_membros_equipe.py#L244) · 2 cenários
- [`test_equipe_inexistente`](../tests/test_membros_equipe.py#L259) · 3 cenários
- [`test_usuario_sem_vinculo_nao_e_adicionado`](../tests/test_membros_equipe.py#L265) · 2 cenários
- [`test_composicao_fechada_fora_das_inscricoes`](../tests/test_membros_equipe.py#L273) · 12 cenários
- [`test_composicao_fechada_fora_de_formacao`](../tests/test_membros_equipe.py#L281) · 6 cenários
- [`test_dev_tambem_respeita_periodo_e_situacao`](../tests/test_membros_equipe.py#L293) · 4 cenários
- [`test_patch_rejeita_campos_indevidos`](../tests/test_membros_equipe.py#L320) · 6 cenários
- [`test_nao_existe_inclusao_direta`](../tests/test_membros_equipe.py#L326)
- [`test_remocao_preserva_historico_e_reconvite_a_mesma_equipe_fica_bloqueado`](../tests/test_membros_equipe.py#L337)
- [`test_remocao_libera_vaga_mantendo_maximo_configurado`](../tests/test_membros_equipe.py#L363)
- [`test_remover_permite_corrigir_equipe_com_maximo_reduzido`](../tests/test_membros_equipe.py#L374)
- [`test_removido_pode_aceitar_convite_de_outra_equipe_da_mesma_edicao`](../tests/test_membros_equipe.py#L381)
- [`test_falha_depois_do_flush_reverte_alteracao`](../tests/test_membros_equipe.py#L405) · 2 cenários
- [`test_swagger_documenta_membros_e_restricoes`](../tests/test_membros_equipe.py#L430)

</details>

### test_reenvio_convite

Arquivo [`tests/test_reenvio_convite.py`](../tests/test_reenvio_convite.py) · integração · 32 funções · 42 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_reenvio_gera_token_novo_e_invalida_o_anterior`](../tests/test_reenvio_convite.py#L112)
- [`test_reenvio_renova_a_validade_de_um_link_vencido`](../tests/test_reenvio_convite.py#L136)
- [`test_o_aviso_novo_usa_a_chave_do_envio_e_retira_o_antigo_da_fila`](../tests/test_reenvio_convite.py#L154)
- [`test_aviso_que_o_worker_ja_pegou_nao_e_cancelado_e_nao_da_erro`](../tests/test_reenvio_convite.py#L180) · 3 cenários
- [`test_dois_links_diferentes_nunca_valem_ao_mesmo_tempo_e_o_400_e_identico`](../tests/test_reenvio_convite.py#L205)
- [`test_reenvio_para_quem_ja_tem_conta_usa_a_central_e_o_email_de_convites`](../tests/test_reenvio_convite.py#L236)
- [`test_convite_pos_cadastro_reenviado_vira_aviso_de_conta_e_mata_o_link`](../tests/test_reenvio_convite.py#L255)
- [`test_so_o_lider_reenvia`](../tests/test_reenvio_convite.py#L276)
- [`test_dev_tambem_reenvia`](../tests/test_reenvio_convite.py#L298)
- [`test_conta_pendente_nao_reenvia`](../tests/test_reenvio_convite.py#L306)
- [`test_convite_que_nao_pode_mais_ser_renovado_da_409`](../tests/test_reenvio_convite.py#L317) · 5 cenários
- [`test_reenvio_antes_do_intervalo_da_429_com_retry_after`](../tests/test_reenvio_convite.py#L350)
- [`test_limite_de_reenvios_da_409_e_zera_o_proximo_reenvio`](../tests/test_reenvio_convite.py#L365)
- [`test_proximo_reenvio_considera_so_o_intervalo`](../tests/test_reenvio_convite.py#L386)
- [`test_corrigir_so_o_nome_nao_envia_nada_nem_conta_nos_limites`](../tests/test_reenvio_convite.py#L410)
- [`test_trocar_o_email_invalida_o_link_antigo_e_avisa_o_endereco_novo`](../tests/test_reenvio_convite.py#L424)
- [`test_trocar_o_email_para_quem_ja_tem_conta_liga_o_convite_a_ela`](../tests/test_reenvio_convite.py#L450)
- [`test_trocar_o_email_de_quem_tem_conta_marca_o_aviso_antigo_como_lido`](../tests/test_reenvio_convite.py#L471)
- [`test_a_troca_de_email_conta_no_limite_sem_esperar_o_intervalo`](../tests/test_reenvio_convite.py#L492)
- [`test_o_reenvio_simples_conta_o_que_a_troca_de_email_ja_gastou`](../tests/test_reenvio_convite.py#L507)
- [`test_correcao_nao_aceita_email_repetido_integrante_nem_lider`](../tests/test_reenvio_convite.py#L521)
- [`test_correcao_respeita_o_maximo_de_integrantes`](../tests/test_reenvio_convite.py#L544)
- [`test_corpo_invalido_da_422`](../tests/test_reenvio_convite.py#L562) · 5 cenários
- [`test_so_o_lider_corrige`](../tests/test_reenvio_convite.py#L569)
- [`test_dois_reenvios_simultaneos_geram_um_unico_token_valido`](../tests/test_reenvio_convite.py#L584)
- [`test_troca_de_email_e_reenvio_simultaneos_deixam_um_so_token_valido`](../tests/test_reenvio_convite.py#L599)
- [`test_duas_trocas_de_email_simultaneas_deixam_um_so_token_valido`](../tests/test_reenvio_convite.py#L619)
- [`test_resposta_e_log_nao_vazam_token_nem_email_de_terceiros`](../tests/test_reenvio_convite.py#L638)
- [`test_swagger_documenta_reenvio_e_correcao`](../tests/test_reenvio_convite.py#L672)
- [`test_convite_posterior_nao_da_acesso_antecipado_a_equipe_em_formacao`](../tests/test_reenvio_convite.py#L687)
- [`test_o_convidado_define_a_propria_senha_e_ninguem_recebe_credenciais`](../tests/test_reenvio_convite.py#L724)
- [`test_migration_do_reenvio_de_convites`](../tests/test_reenvio_convite.py#L746)

</details>

### test_avaliacao_cientifica

Arquivo [`tests/test_avaliacao_cientifica.py`](../tests/test_avaliacao_cientifica.py) · misto · 21 funções · 50 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_salva_rascunho_incompleto_e_edita_substituindo_conteudo`](../tests/test_avaliacao_cientifica.py#L110) · integração
- [`test_nao_designado_recebe_404`](../tests/test_avaliacao_cientifica.py#L133) · 3 cenários · integração
- [`test_perfis_nao_cientificos_nao_avaliam`](../tests/test_avaliacao_cientifica.py#L140) · 4 cenários · integração
- [`test_dev_precisa_de_designacao_e_pode_avaliar_quando_designado`](../tests/test_avaliacao_cientifica.py#L151) · integração
- [`test_exige_rubrica_publicada_da_mesma_edicao`](../tests/test_avaliacao_cientifica.py#L161) · 3 cenários · integração
- [`test_proposta_rascunho_nao_pode_ser_avaliada`](../tests/test_avaliacao_cientifica.py#L190) · integração
- [`test_rejeita_notas_e_campos_invalidos`](../tests/test_avaliacao_cientifica.py#L212) · 10 cenários · integração
- [`test_exige_completude_no_envio_preservando_rascunho`](../tests/test_avaliacao_cientifica.py#L254) · 5 cenários · integração
- [`test_envio_calcula_nota_e_registra_data`](../tests/test_avaliacao_cientifica.py#L276) · 4 cenários · integração
- [`test_normalizacao_limites_e_arredondamento_final`](../tests/test_avaliacao_cientifica.py#L299) · 3 cenários · integração
- [`test_calculo_usa_decimal_com_escalas_diferentes`](../tests/test_avaliacao_cientifica.py#L309) · unitário
- [`test_avaliacao_enviada_e_imutavel_e_reenvio_da_409`](../tests/test_avaliacao_cientifica.py#L341) · integração
- [`test_envios_simultaneos_geram_uma_unica_avaliacao`](../tests/test_avaliacao_cientifica.py#L351) · 2 cenários · integração
- [`test_salvamento_simultaneo_ao_envio_nao_altera_avaliacao_final`](../tests/test_avaliacao_cientifica.py#L368) · integração
- [`test_falha_banco_desfaz_avaliacao_e_notas`](../tests/test_avaliacao_cientifica.py#L393) · 2 cenários · integração
- [`test_avaliadores_nao_consultam_nem_alteram_avaliacao_alheia`](../tests/test_avaliacao_cientifica.py#L415) · integração
- [`test_painel_e_proposta_da_equipe_nao_expoem_resultados`](../tests/test_avaliacao_cientifica.py#L426) · integração
- [`test_rascunho_iniciado_bloqueia_redistribuicao_e_complemento`](../tests/test_avaliacao_cientifica.py#L467) · integração
- [`test_redistribuicao_concorrente_revoga_acesso_antes_de_salvar`](../tests/test_avaliacao_cientifica.py#L479) · integração
- [`test_unicidade_no_banco`](../tests/test_avaliacao_cientifica.py#L507) · integração
- [`test_migration_em_banco_vazio_e_atualizado`](../tests/test_avaliacao_cientifica.py#L525) · 3 cenários · integração

</details>

### test_avaliacao_designacoes

Arquivo [`tests/test_avaliacao_designacoes.py`](../tests/test_avaliacao_designacoes.py) · integração · 45 funções · 72 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_quantidade_nasce_sem_valor_padrao`](../tests/test_avaliacao_designacoes.py#L190)
- [`test_organizador_configura_a_quantidade`](../tests/test_avaliacao_designacoes.py#L198) · 2 cenários
- [`test_quantidade_fora_de_2_a_3_e_recusada`](../tests/test_avaliacao_designacoes.py#L219) · 5 cenários
- [`test_configurar_hackathon_inexistente`](../tests/test_avaliacao_designacoes.py#L231)
- [`test_banco_recusa_quantidade_fora_de_2_a_3`](../tests/test_avaliacao_designacoes.py#L241)
- [`test_banco_recusa_designacao_duplicada`](../tests/test_avaliacao_designacoes.py#L249)
- [`test_alterar_quantidade_nao_mexe_nas_designacoes_existentes`](../tests/test_avaliacao_designacoes.py#L257)
- [`test_distribui_a_quantidade_configurada_de_forma_balanceada`](../tests/test_avaliacao_designacoes.py#L282) · 2 cenários
- [`test_distribuir_de_novo_nao_altera_o_que_ja_esta_completo`](../tests/test_avaliacao_designacoes.py#L308)
- [`test_nova_proposta_enviada_e_incluida_na_proxima_distribuicao`](../tests/test_avaliacao_designacoes.py#L321)
- [`test_rascunho_nao_e_distribuido`](../tests/test_avaliacao_designacoes.py#L333)
- [`test_rascunho_nao_pode_ser_redistribuido`](../tests/test_avaliacao_designacoes.py#L345)
- [`test_distribuir_sem_quantidade_configurada_responde_409`](../tests/test_avaliacao_designacoes.py#L355)
- [`test_avaliadores_insuficientes_nao_gravam_nada`](../tests/test_avaliacao_designacoes.py#L365)
- [`test_insuficiencia_so_numa_proposta_tambem_desfaz_tudo`](../tests/test_avaliacao_designacoes.py#L374)
- [`test_avaliador_inativo_ou_pendente_nao_e_elegivel`](../tests/test_avaliacao_designacoes.py#L395) · 2 cenários
- [`test_outros_papeis_e_dev_nao_sao_avaliadores`](../tests/test_avaliacao_designacoes.py#L405)
- [`test_distribuir_bloqueado_apos_inicio_da_avaliacao`](../tests/test_avaliacao_designacoes.py#L419) · 3 cenários
- [`test_distribuir_permitido_antes_da_avaliacao`](../tests/test_avaliacao_designacoes.py#L430) · 2 cenários
- [`test_distribuir_ignora_proposta_que_ja_tem_nota`](../tests/test_avaliacao_designacoes.py#L437)
- [`test_distribuir_hackathon_inexistente`](../tests/test_avaliacao_designacoes.py#L449)
- [`test_distribuicoes_simultaneas_nao_duplicam_designacoes`](../tests/test_avaliacao_designacoes.py#L458)
- [`test_redistribui_antes_de_a_avaliacao_comecar`](../tests/test_avaliacao_designacoes.py#L478)
- [`test_redistribui_proposta_ainda_sem_designacao`](../tests/test_avaliacao_designacoes.py#L498)
- [`test_redistribuir_so_afeta_a_proposta_indicada`](../tests/test_avaliacao_designacoes.py#L507)
- [`test_redistribuir_bloqueado_depois_do_inicio_da_avaliacao`](../tests/test_avaliacao_designacoes.py#L521) · 3 cenários
- [`test_redistribuir_bloqueado_se_a_proposta_ja_tem_nota`](../tests/test_avaliacao_designacoes.py#L534)
- [`test_redistribuir_sem_quantidade_configurada`](../tests/test_avaliacao_designacoes.py#L547)
- [`test_redistribuir_exige_exatamente_a_quantidade_configurada`](../tests/test_avaliacao_designacoes.py#L555) · 2 cenários
- [`test_redistribuir_recusa_avaliador_repetido`](../tests/test_avaliacao_designacoes.py#L571)
- [`test_redistribuir_recusa_quem_nao_e_avaliador_elegivel`](../tests/test_avaliacao_designacoes.py#L584) · 6 cenários
- [`test_redistribuir_proposta_inexistente`](../tests/test_avaliacao_designacoes.py#L609)
- [`test_organizador_lista_designacoes_com_propostas_ainda_sem_avaliador`](../tests/test_avaliacao_designacoes.py#L618)
- [`test_listar_designacoes_de_hackathon_inexistente`](../tests/test_avaliacao_designacoes.py#L635)
- [`test_avaliador_ve_somente_as_propostas_designadas_a_ele`](../tests/test_avaliacao_designacoes.py#L647)
- [`test_avaliador_consulta_proposta_designada_sem_ver_a_equipe`](../tests/test_avaliacao_designacoes.py#L663)
- [`test_proposta_de_outro_avaliador_ou_inexistente_responde_404`](../tests/test_avaliacao_designacoes.py#L678)
- [`test_avaliador_sem_designacao_recebe_lista_vazia`](../tests/test_avaliacao_designacoes.py#L691)
- [`test_redistribuir_tira_o_acesso_de_quem_saiu`](../tests/test_avaliacao_designacoes.py#L700)
- [`test_dev_nas_rotas_do_avaliador_ve_so_o_que_foi_designado_a_ele`](../tests/test_avaliacao_designacoes.py#L722)
- [`test_perfis_sem_permissao_nas_rotas_do_organizador`](../tests/test_avaliacao_designacoes.py#L738) · 4 cenários
- [`test_perfis_sem_permissao_nas_rotas_do_avaliador`](../tests/test_avaliacao_designacoes.py#L764) · 4 cenários
- [`test_dev_organiza_a_distribuicao`](../tests/test_avaliacao_designacoes.py#L774)
- [`test_autenticacao_e_conta_ativa`](../tests/test_avaliacao_designacoes.py#L783) · 4 cenários
- [`test_distribuicao_usa_so_o_comite_da_organizacao_do_hackathon`](../tests/test_avaliacao_designacoes.py#L811)

</details>

### test_envio_proposta

Arquivo [`tests/test_envio_proposta.py`](../tests/test_envio_proposta.py) · misto · 18 funções · 81 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_lider_envia_e_integrante_consulta_protocolo_persistido`](../tests/test_envio_proposta.py#L80) · integração
- [`test_autorizacao_por_vinculo`](../tests/test_envio_proposta.py#L112) · 6 cenários · integração
- [`test_autenticacao_e_conta_ativa`](../tests/test_envio_proposta.py#L134) · 8 cenários · integração
- [`test_apenas_homologada_envia_inclusive_dev`](../tests/test_envio_proposta.py#L159) · 8 cenários · integração
- [`test_prazo_de_propostas`](../tests/test_envio_proposta.py#L187) · 12 cenários · integração
- [`test_prazo_normaliza_fusos_e_inclui_limites`](../tests/test_envio_proposta.py#L209) · 15 cenários · unitário
- [`test_periodo_invertido_nao_abre_envio`](../tests/test_envio_proposta.py#L224) · unitário
- [`test_revalida_tema_no_envio`](../tests/test_envio_proposta.py#L235) · 6 cenários · integração
- [`test_campos_obrigatorios_incompletos_bloqueiam`](../tests/test_envio_proposta.py#L276) · 12 cenários · integração
- [`test_get_nao_expoe_rascunho_ou_proposta_ausente`](../tests/test_envio_proposta.py#L289) · 2 cenários · integração
- [`test_equipe_inexistente`](../tests/test_envio_proposta.py#L301) · 2 cenários · integração
- [`test_reenvio_retorna_409_e_envio_e_imutavel`](../tests/test_envio_proposta.py#L307) · integração
- [`test_dois_envios_simultaneos_geram_apenas_um_protocolo`](../tests/test_envio_proposta.py#L325) · integração
- [`test_envio_trava_equipe_antes_da_proposta`](../tests/test_envio_proposta.py#L343) · integração
- [`test_falha_no_protocolo_reverte_envio_e_permite_nova_tentativa`](../tests/test_envio_proposta.py#L368) · 2 cenários · integração
- [`test_banco_impede_repetir_versao_e_alterar_versao_enviada`](../tests/test_envio_proposta.py#L391) · integração
- [`test_painel_preserva_protocolo_de_inscricao_e_adiciona_o_de_proposta`](../tests/test_envio_proposta.py#L419) · integração
- [`test_swagger_documenta_envio_e_consulta`](../tests/test_envio_proposta.py#L446) · integração

</details>

### test_resultado

Arquivo [`tests/test_resultado.py`](../tests/test_resultado.py) · misto · 16 funções · 22 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_media_arredonda_so_no_fim_com_half_up`](../tests/test_resultado.py#L136) · unitário
- [`test_consolida_notas_e_classifica`](../tests/test_resultado.py#L142) · integração
- [`test_empate_na_media_desempata_por_recomendacoes_de_aprovacao`](../tests/test_resultado.py#L162) · integração
- [`test_avaliacao_faltando_ou_em_rascunho_impede_homologar`](../tests/test_resultado.py#L176) · integração
- [`test_avaliadores_insuficientes_e_quantidade_nao_configurada`](../tests/test_resultado.py#L205) · integração
- [`test_sem_propostas_nao_homologa`](../tests/test_resultado.py#L214) · integração
- [`test_homologa_grava_auditoria_e_bloqueia_resultado`](../tests/test_resultado.py#L228) · integração
- [`test_depois_de_homologado_avaliacao_e_distribuicao_ficam_bloqueadas`](../tests/test_resultado.py#L253) · integração
- [`test_banco_impede_alterar_resultado_homologado`](../tests/test_resultado.py#L282) · integração
- [`test_lista_de_aprovadas_invalida_responde_422`](../tests/test_resultado.py#L298) · 4 cenários · integração
- [`test_corpo_com_campo_extra_responde_422`](../tests/test_resultado.py#L319) · integração
- [`test_so_organizador_consulta_e_homologa`](../tests/test_resultado.py#L330) · 4 cenários · integração
- [`test_sem_token_responde_401_e_dev_pode_homologar`](../tests/test_resultado.py#L338) · integração
- [`test_hackathon_inexistente_responde_404`](../tests/test_resultado.py#L349) · integração
- [`test_lista_publica_so_aparece_depois_da_homologacao`](../tests/test_resultado.py#L364) · integração
- [`test_lista_publica_mostra_equipe_tema_e_titulo_sem_login`](../tests/test_resultado.py#L377) · integração

</details>

### test_resultado_service

Arquivo [`tests/test_resultado_service.py`](../tests/test_resultado_service.py) · unitário · 5 funções · 7 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_empate_em_media_e_recomendacoes_prioriza_envio_mais_antigo`](../tests/test_resultado_service.py#L25)
- [`test_empate_completo_desempata_por_identificador`](../tests/test_resultado_service.py#L35) · 3 cenários
- [`test_empate_sem_data_fica_depois_de_proposta_com_data`](../tests/test_resultado_service.py#L43)
- [`test_nota_zero_entra_na_classificacao_e_proposta_sem_nota_fica_sem_posicao`](../tests/test_resultado_service.py#L52)
- [`test_media_preserva_arredondamento_e_precisao_do_chamador`](../tests/test_resultado_service.py#L62)

</details>

### test_rubrica

Arquivo [`tests/test_rubrica.py`](../tests/test_rubrica.py) · misto · 24 funções · 41 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_normalizar_nome_ignora_acentos_maiusculas_e_espacos`](../tests/test_rubrica.py#L103) · unitário
- [`test_criterios_minimos_faltantes`](../tests/test_rubrica.py#L108) · unitário
- [`test_pendencias_para_publicar`](../tests/test_rubrica.py#L115) · unitário
- [`test_rubrica_lista_criterios_obrigatorios_ausentes_mesmo_com_peso_total_correto`](../tests/test_rubrica.py#L125) · unitário
- [`test_prazo_de_publicacao`](../tests/test_rubrica.py#L132) · unitário
- [`test_organizador_salva_rascunho_incompleto_com_pendencias`](../tests/test_rubrica.py#L143) · integração
- [`test_salvar_substitui_a_lista_e_mantem_a_ordem`](../tests/test_rubrica.py#L159) · integração
- [`test_criterio_invalido`](../tests/test_rubrica.py#L189) · 9 cenários · integração
- [`test_nomes_repetidos_na_rubrica`](../tests/test_rubrica.py#L193) · integração
- [`test_outros_perfis_nao_editam_rubrica`](../tests/test_rubrica.py#L199) · 3 cenários · integração
- [`test_dev_edita_e_publica`](../tests/test_rubrica.py#L206) · integração
- [`test_rubrica_de_hackathon_inexistente`](../tests/test_rubrica.py#L212) · integração
- [`test_rascunho_inexistente`](../tests/test_rubrica.py#L217) · integração
- [`test_publica_e_consulta_sem_login`](../tests/test_rubrica.py#L225) · integração
- [`test_rubrica_nao_publicada_nao_aparece_para_o_publico`](../tests/test_rubrica.py#L239) · integração
- [`test_publicar_exige_soma_100`](../tests/test_rubrica.py#L245) · 2 cenários · integração
- [`test_publicar_exige_criterios_minimos_da_rn10`](../tests/test_rubrica.py#L257) · integração
- [`test_criterios_minimos_aceitam_variacao_de_escrita`](../tests/test_rubrica.py#L267) · integração
- [`test_publicar_sem_criterios`](../tests/test_rubrica.py#L275) · integração
- [`test_publicar_antes_das_inscricoes`](../tests/test_rubrica.py#L281) · 4 cenários · integração
- [`test_rubrica_publicada_nao_muda`](../tests/test_rubrica.py#L287) · integração
- [`test_publicacoes_simultaneas_geram_um_sucesso`](../tests/test_rubrica.py#L298) · integração
- [`test_banco_impede_alterar_rubrica_publicada`](../tests/test_rubrica.py#L326) · 4 cenários · integração
- [`test_banco_permite_remover_a_rubrica_inteira`](../tests/test_rubrica.py#L333) · integração

</details>

### test_submissoes

Arquivo [`tests/test_submissoes.py`](../tests/test_submissoes.py) · integração · 26 funções · 108 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_lider_cria_rascunho_incompleto_e_persistido`](../tests/test_submissoes.py#L73) · 4 cenários
- [`test_lider_salva_todos_os_campos_com_tema_valido`](../tests/test_submissoes.py#L95)
- [`test_integrante_consulta_conteudo_e_ultimo_salvamento`](../tests/test_submissoes.py#L114)
- [`test_permissoes_por_vinculo`](../tests/test_submissoes.py#L126) · 9 cenários
- [`test_papeis_sem_vinculo_nao_acessam_rascunhos`](../tests/test_submissoes.py#L146) · 12 cenários
- [`test_dev_cria_consulta_e_edita_sem_vinculo`](../tests/test_submissoes.py#L156)
- [`test_autenticacao_e_conta_ativa`](../tests/test_submissoes.py#L170) · 12 cenários
- [`test_equipe_inexistente`](../tests/test_submissoes.py#L192) · 3 cenários
- [`test_rascunho_inexistente`](../tests/test_submissoes.py#L197) · 2 cenários
- [`test_uma_proposta_por_equipe`](../tests/test_submissoes.py#L205)
- [`test_duas_criacoes_simultaneas_nao_duplicam`](../tests/test_submissoes.py#L216)
- [`test_constraint_existente_trata_corrida_com_409`](../tests/test_submissoes.py#L231)
- [`test_falha_apos_flush_nao_deixa_rascunho_parcial`](../tests/test_submissoes.py#L245)
- [`test_patch_preserva_campos_omitidos_e_atualiza_ultimo_salvamento`](../tests/test_submissoes.py#L261)
- [`test_patch_limpa_campo_opcional_com_null`](../tests/test_submissoes.py#L289) · 6 cenários
- [`test_patch_vazio_registra_salvamento_sem_perder_conteudo`](../tests/test_submissoes.py#L309)
- [`test_tema_selecionado_precisa_existir_estar_ativo_e_ser_da_edicao`](../tests/test_submissoes.py#L325) · 6 cenários
- [`test_patch_permite_selecionar_outro_tema_valido`](../tests/test_submissoes.py#L344)
- [`test_tema_antigo_inativo_nao_impede_editar_outros_campos_ou_limpar`](../tests/test_submissoes.py#L354)
- [`test_ods_fora_do_intervalo_sao_recusados`](../tests/test_submissoes.py#L371) · 10 cenários
- [`test_corpo_rejeita_campos_controlados_pelo_servidor`](../tests/test_submissoes.py#L397) · 18 cenários
- [`test_proposta_enviada_nao_e_rascunho_nem_editavel`](../tests/test_submissoes.py#L410) · 6 cenários
- [`test_equipe_nao_homologada_fica_em_somente_leitura`](../tests/test_submissoes.py#L424) · 4 cenários
- [`test_rascunho_nao_exige_homologacao_nem_prazo_de_envio`](../tests/test_submissoes.py#L443) · 3 cenários
- [`test_swagger_documenta_contrato_e_nao_expoe_rotas_de_avaliacao`](../tests/test_submissoes.py#L463)
- [`test_salvar_rascunho_nao_cria_avaliacao_ou_protocolo`](../tests/test_submissoes.py#L492)

</details>

### test_temas

Arquivo [`tests/test_temas.py`](../tests/test_temas.py) · integração · 21 funções · 34 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_comite_organizador_e_dev_cadastram_tema`](../tests/test_temas.py#L67) · 3 cenários
- [`test_outros_perfis_nao_cadastram_tema`](../tests/test_temas.py#L83) · 3 cenários
- [`test_cadastro_exige_token`](../tests/test_temas.py#L88)
- [`test_tema_exige_titulo_descricao_e_ods`](../tests/test_temas.py#L105) · 6 cenários
- [`test_titulo_repetido_na_mesma_edicao`](../tests/test_temas.py#L109)
- [`test_cadastro_em_hackathon_inexistente`](../tests/test_temas.py#L118)
- [`test_edicao_altera_apenas_os_campos_enviados`](../tests/test_temas.py#L122)
- [`test_edicao_nao_aceita_null_em_campo_obrigatorio`](../tests/test_temas.py#L137) · 4 cenários
- [`test_edicao_com_titulo_de_outro_tema`](../tests/test_temas.py#L142)
- [`test_participante_nao_edita_tema`](../tests/test_temas.py#L148)
- [`test_editar_tema_inexistente`](../tests/test_temas.py#L154)
- [`test_tema_desativado_some_da_listagem_de_participantes`](../tests/test_temas.py#L158)
- [`test_organizador_lista_inativos_quando_pede`](../tests/test_temas.py#L173)
- [`test_participante_nao_pede_inativos`](../tests/test_temas.py#L186)
- [`test_listagem_de_outra_edicao_nao_mistura`](../tests/test_temas.py#L190)
- [`test_reativar_tema`](../tests/test_temas.py#L196)
- [`test_tema_desativado_nao_pode_ser_escolhido_na_proposta`](../tests/test_temas.py#L202)
- [`test_excluir_tema_sem_propostas`](../tests/test_temas.py#L208)
- [`test_nao_exclui_tema_com_propostas`](../tests/test_temas.py#L217) · 2 cenários
- [`test_participante_nao_exclui_tema`](../tests/test_temas.py#L234)
- [`test_temas_ativos_sao_publicos`](../tests/test_temas.py#L239)

</details>

### test_temas_rubricas_comite

Arquivo [`tests/test_temas_rubricas_comite.py`](../tests/test_temas_rubricas_comite.py) · integração · 22 funções · 27 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_catalogo_de_temas_ativos_e_publico`](../tests/test_temas_rubricas_comite.py#L46)
- [`test_tema_desativado_nao_aparece_para_visitante`](../tests/test_temas_rubricas_comite.py#L59)
- [`test_catalogo_de_edicao_inexistente`](../tests/test_temas_rubricas_comite.py#L64)
- [`test_inativos_exigem_token`](../tests/test_temas_rubricas_comite.py#L68)
- [`test_token_invalido_no_catalogo_retorna_401`](../tests/test_temas_rubricas_comite.py#L76) · 2 cenários
- [`test_outros_perfis_nao_pedem_inativos`](../tests/test_temas_rubricas_comite.py#L84) · 2 cenários
- [`test_comite_pendente_nao_pede_inativos`](../tests/test_temas_rubricas_comite.py#L89)
- [`test_comite_gerencia_temas`](../tests/test_temas_rubricas_comite.py#L97)
- [`test_escrita_de_tema_exige_token`](../tests/test_temas_rubricas_comite.py#L114) · 2 cenários
- [`test_comite_monta_e_publica_rubrica`](../tests/test_temas_rubricas_comite.py#L126)
- [`test_rubrica_exige_token`](../tests/test_temas_rubricas_comite.py#L138) · 2 cenários
- [`test_outros_perfis_nao_editam_rubrica_do_projeto_final`](../tests/test_temas_rubricas_comite.py#L146) · 2 cenários
- [`test_fases_tem_criterios_e_pesos_independentes`](../tests/test_temas_rubricas_comite.py#L192)
- [`test_rubrica_sem_fase_e_a_da_proposta`](../tests/test_temas_rubricas_comite.py#L209)
- [`test_publicar_uma_fase_nao_publica_nem_trava_a_outra`](../tests/test_temas_rubricas_comite.py#L220)
- [`test_fase_invalida`](../tests/test_temas_rubricas_comite.py#L235)
- [`test_projeto_final_exige_minimos_da_rn10`](../tests/test_temas_rubricas_comite.py#L240)
- [`test_projeto_final_pode_ser_publicado_depois_das_inscricoes`](../tests/test_temas_rubricas_comite.py#L252)
- [`test_projeto_final_nao_publica_depois_do_resultado_homologado`](../tests/test_temas_rubricas_comite.py#L261)
- [`test_rubrica_criada_sem_fase_fica_na_proposta`](../tests/test_temas_rubricas_comite.py#L284)
- [`test_banco_permite_uma_rubrica_por_fase`](../tests/test_temas_rubricas_comite.py#L292)
- [`test_avaliacao_cientifica_nao_usa_rubrica_do_projeto_final`](../tests/test_temas_rubricas_comite.py#L304)

</details>

### test_validacao_links

Arquivo [`tests/test_validacao_links.py`](../tests/test_validacao_links.py) · unitário · 8 funções · 17 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_link_exige_https_e_host`](../tests/test_validacao_links.py#L9) · 2 cenários
- [`test_link_rejeita_credenciais_embutidas`](../tests/test_validacao_links.py#L15) · 3 cenários
- [`test_limite_de_tamanho_conta_o_link_apos_aparar_as_pontas`](../tests/test_validacao_links.py#L24) · 2 cenários
- [`test_primeiro_tamanho_acima_do_limite_e_recusado`](../tests/test_validacao_links.py#L30)
- [`test_caracteres_de_controle_e_espacos_unicode_sao_recusados_no_meio_do_link`](../tests/test_validacao_links.py#L46) · 4 cenários
- [`test_porta_invalida_da_erro_de_validacao`](../tests/test_validacao_links.py#L52) · 2 cenários
- [`test_extensao_fora_do_caminho_nao_qualifica_link_como_imagem`](../tests/test_validacao_links.py#L58) · 2 cenários
- [`test_link_de_imagem_preserva_espaco_codificado_e_parametros`](../tests/test_validacao_links.py#L63)

</details>

### test_validacao_submissao

Arquivo [`tests/test_validacao_submissao.py`](../tests/test_validacao_submissao.py) · unitário · 6 funções · 13 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_envio_exige_os_dois_limites_do_prazo`](../tests/test_validacao_submissao.py#L13) · 2 cenários
- [`test_espacos_unicode_nao_preenchem_texto_obrigatorio`](../tests/test_validacao_submissao.py#L35) · 3 cenários
- [`test_ods_validos_na_mesma_lista_nao_compensam_item_invalido`](../tests/test_validacao_submissao.py#L49) · 3 cenários
- [`test_todas_as_pendencias_sao_informadas_juntas_na_ordem_do_formulario`](../tests/test_validacao_submissao.py#L55)
- [`test_documento_opcional_e_limites_de_ods_nao_bloqueiam_proposta_completa`](../tests/test_validacao_submissao.py#L67)
- [`test_prazo_de_propostas_independe_das_datas_de_inscricao`](../tests/test_validacao_submissao.py#L83) · 3 cenários

</details>

### test_versionamento_proposta

Arquivo [`tests/test_versionamento_proposta.py`](../tests/test_versionamento_proposta.py) · integração · 24 funções · 33 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_reenvio_cria_nova_versao_com_protocolo_proprio_e_preserva_a_anterior`](../tests/test_versionamento_proposta.py#L121)
- [`test_cada_versao_avisa_o_protocolo_por_email`](../tests/test_versionamento_proposta.py#L156)
- [`test_varios_reenvios_numeram_em_sequencia`](../tests/test_versionamento_proposta.py#L166)
- [`test_reenvios_simultaneos_nao_repetem_numero_de_versao`](../tests/test_versionamento_proposta.py#L181)
- [`test_dev_reenvia`](../tests/test_versionamento_proposta.py#L197)
- [`test_reenvio_exige_token`](../tests/test_versionamento_proposta.py#L206)
- [`test_so_o_lider_reenvia`](../tests/test_versionamento_proposta.py#L215) · 2 cenários
- [`test_historico_so_para_integrantes`](../tests/test_versionamento_proposta.py#L223)
- [`test_rascunho_nao_pode_ser_reenviado`](../tests/test_versionamento_proposta.py#L233)
- [`test_reenvio_depois_do_prazo`](../tests/test_versionamento_proposta.py#L239)
- [`test_reenvio_depois_da_distribuicao`](../tests/test_versionamento_proposta.py#L245)
- [`test_reenvio_com_avaliacao_registrada`](../tests/test_versionamento_proposta.py#L256)
- [`test_reenvio_e_envio_depois_do_resultado_homologado`](../tests/test_versionamento_proposta.py#L272)
- [`test_envio_original_depois_do_resultado_homologado`](../tests/test_versionamento_proposta.py#L279)
- [`test_reenvio_de_equipe_nao_homologada`](../tests/test_versionamento_proposta.py#L287)
- [`test_tema_inativo_ou_de_outra_edicao`](../tests/test_versionamento_proposta.py#L296)
- [`test_nova_versao_precisa_estar_completa`](../tests/test_versionamento_proposta.py#L314) · 6 cenários
- [`test_proposta_legada_sem_historico_continua_consultavel`](../tests/test_versionamento_proposta.py#L327)
- [`test_envio_espera_a_homologacao_em_andamento_e_respeita_o_resultado`](../tests/test_versionamento_proposta.py#L351)
- [`test_nao_homologa_antes_do_fim_do_prazo_de_propostas`](../tests/test_versionamento_proposta.py#L427) · 2 cenários
- [`test_avaliacao_legada_incompleta_impede_homologar`](../tests/test_versionamento_proposta.py#L445)
- [`test_avaliacao_enviada_sem_tudo_da_rf30_e_incompleta`](../tests/test_versionamento_proposta.py#L471) · 3 cenários
- [`test_homologa_todas_as_propostas_enviadas`](../tests/test_versionamento_proposta.py#L510)
- [`test_migration_transforma_envios_existentes_na_versao_1`](../tests/test_versionamento_proposta.py#L524)

</details>

### test_atribuicoes_mentor

Arquivo [`tests/test_atribuicoes_mentor.py`](../tests/test_atribuicoes_mentor.py) · integração · 37 funções · 53 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_atribuir_autorizados_e_marcos`](../tests/test_atribuicoes_mentor.py#L191) · 3 cenários
- [`test_regras_da_equipe`](../tests/test_atribuicoes_mentor.py#L207) · 5 cenários
- [`test_mentor_inelegivel`](../tests/test_atribuicoes_mentor.py#L237) · 5 cenários
- [`test_mentor_de_outra_edicao_e_termos_desatualizados`](../tests/test_atribuicoes_mentor.py#L241)
- [`test_capacidade_global_e_reducao`](../tests/test_atribuicoes_mentor.py#L250)
- [`test_capacidade_entre_edicoes`](../tests/test_atribuicoes_mentor.py#L265)
- [`test_reducao_abaixo_do_uso_recusada`](../tests/test_atribuicoes_mentor.py#L276)
- [`test_substituicao_preserva_historico_e_libera_vaga`](../tests/test_atribuicoes_mentor.py#L290)
- [`test_substituicao_falha_preserva_vinculo`](../tests/test_atribuicoes_mentor.py#L307)
- [`test_encerramento_e_reinicio_da_cadeia`](../tests/test_atribuicoes_mentor.py#L318)
- [`test_isolamento_das_equipes_e_dos_mentores`](../tests/test_atribuicoes_mentor.py#L331)
- [`test_listagem_filtros_e_mentor_desativado`](../tests/test_atribuicoes_mentor.py#L356)
- [`test_permissoes_administrativas`](../tests/test_atribuicoes_mentor.py#L379) · 3 cenários
- [`test_sem_token_e_gestor_pendente`](../tests/test_atribuicoes_mentor.py#L401)
- [`test_validacao_e_mass_assignment`](../tests/test_atribuicoes_mentor.py#L408) · 4 cenários
- [`test_treinamento_auditado_idempotente_e_permissoes`](../tests/test_atribuicoes_mentor.py#L419)
- [`test_treinamento_exige_homologacao`](../tests/test_atribuicoes_mentor.py#L436)
- [`test_notifica_todos_atomicamente_e_entrega`](../tests/test_atribuicoes_mentor.py#L447)
- [`test_substituicao_notifica_anterior_novo_e_equipe`](../tests/test_atribuicoes_mentor.py#L480)
- [`test_falha_de_notificacao_desfaz_atribuicao`](../tests/test_atribuicoes_mentor.py#L492)
- [`test_falha_enfileiramento_preserva_evento_e_atribuicao`](../tests/test_atribuicoes_mentor.py#L505)
- [`test_concorrencia_mesma_equipe`](../tests/test_atribuicoes_mentor.py#L519)
- [`test_concorrencia_ultima_vaga`](../tests/test_atribuicoes_mentor.py#L531)
- [`test_substituicoes_simultaneas`](../tests/test_atribuicoes_mentor.py#L552)
- [`test_indice_postgres_barra_dois_vigentes`](../tests/test_atribuicoes_mentor.py#L565)
- [`test_fk_postgres_barra_edicao_incorreta`](../tests/test_atribuicoes_mentor.py#L585)
- [`test_swagger`](../tests/test_atribuicoes_mentor.py#L605)
- [`test_be_s5_10_ativacao_real_antes_da_atribuicao`](../tests/test_atribuicoes_mentor.py#L622)
- [`test_trocas_cruzadas_nao_causam_deadlock`](../tests/test_atribuicoes_mentor.py#L656)
- [`test_rollback_de_substituicao_preserva_anterior_e_avisos`](../tests/test_atribuicoes_mentor.py#L673)
- [`test_eventos_pendentes_para_a_central_so_quando_a_publicacao_falha`](../tests/test_atribuicoes_mentor.py#L692)
- [`test_equipes_aprovadas_para_comite_e_organizador`](../tests/test_atribuicoes_mentor.py#L736) · 2 cenários
- [`test_equipes_aprovadas_antes_da_homologacao_vem_vazia`](../tests/test_atribuicoes_mentor.py#L749)
- [`test_equipes_aprovadas_negadas_a_participante_e_mentor`](../tests/test_atribuicoes_mentor.py#L758)
- [`test_equipes_aprovadas_de_hackathon_inexistente`](../tests/test_atribuicoes_mentor.py#L763)
- [`test_comite_de_outra_organizacao_nao_ve_as_aprovadas`](../tests/test_atribuicoes_mentor.py#L767)
- [`test_comite_atribui_mentor_a_equipe_da_lista`](../tests/test_atribuicoes_mentor.py#L778)

</details>

### test_designacao_projetos_finais

Arquivo [`tests/test_designacao_projetos_finais.py`](../tests/test_designacao_projetos_finais.py) · integração · 32 funções · 47 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_organizador_configura_a_quantidade`](../tests/test_designacao_projetos_finais.py#L234) · 2 cenários
- [`test_quantidade_fora_de_2_a_3_e_recusada`](../tests/test_designacao_projetos_finais.py#L259) · 5 cenários
- [`test_banco_recusa_quantidade_fora_de_2_a_3`](../tests/test_designacao_projetos_finais.py#L269)
- [`test_banco_recusa_duas_designacoes_vigentes_iguais`](../tests/test_designacao_projetos_finais.py#L277)
- [`test_distribui_projetos_aprovados_de_forma_balanceada`](../tests/test_designacao_projetos_finais.py#L298) · 2 cenários
- [`test_proposta_reprovada_nao_e_projeto_final`](../tests/test_designacao_projetos_finais.py#L323)
- [`test_distribuir_de_novo_so_completa`](../tests/test_designacao_projetos_finais.py#L337)
- [`test_somente_comite_tecnico_ativo_e_elegivel`](../tests/test_designacao_projetos_finais.py#L349)
- [`test_sem_homologacao_cientifica_responde_409`](../tests/test_designacao_projetos_finais.py#L362)
- [`test_sem_quantidade_configurada_responde_409`](../tests/test_designacao_projetos_finais.py#L373)
- [`test_hackathon_encerrado_bloqueia`](../tests/test_designacao_projetos_finais.py#L385) · 2 cenários
- [`test_falta_de_avaliadores_nao_grava_nada`](../tests/test_designacao_projetos_finais.py#L395)
- [`test_mentor_da_equipe_nao_e_designado`](../tests/test_designacao_projetos_finais.py#L407)
- [`test_mentoria_encerrada_tambem_impede`](../tests/test_designacao_projetos_finais.py#L416)
- [`test_integrante_da_equipe_nao_e_designado`](../tests/test_designacao_projetos_finais.py#L426)
- [`test_conflito_declarado_impede_e_fica_registrado`](../tests/test_designacao_projetos_finais.py#L436)
- [`test_conflito_impede_quando_so_sobram_impedidos`](../tests/test_designacao_projetos_finais.py#L457)
- [`test_conflito_repetido_ou_com_designacao_vigente_responde_409`](../tests/test_designacao_projetos_finais.py#L467)
- [`test_conflito_sem_motivo_responde_422`](../tests/test_designacao_projetos_finais.py#L478) · 2 cenários
- [`test_conflito_com_quem_nao_e_tecnico_ou_equipe_de_outro_hackathon`](../tests/test_designacao_projetos_finais.py#L484)
- [`test_redistribui_e_mantem_historico`](../tests/test_designacao_projetos_finais.py#L504)
- [`test_redistribuir_para_impedido_responde_409`](../tests/test_designacao_projetos_finais.py#L524)
- [`test_redistribuir_com_lista_invalida_responde_422`](../tests/test_designacao_projetos_finais.py#L537) · 2 cenários
- [`test_redistribuir_com_nao_tecnico_responde_409`](../tests/test_designacao_projetos_finais.py#L545)
- [`test_redistribuir_proposta_reprovada_responde_404`](../tests/test_designacao_projetos_finais.py#L554)
- [`test_distribuicoes_simultaneas_nao_duplicam`](../tests/test_designacao_projetos_finais.py#L563)
- [`test_listagem_admin_traz_avaliadores_vigentes`](../tests/test_designacao_projetos_finais.py#L583)
- [`test_avaliador_ve_so_os_proprios_projetos`](../tests/test_designacao_projetos_finais.py#L600)
- [`test_designacao_removida_some_da_lista_do_avaliador`](../tests/test_designacao_projetos_finais.py#L623)
- [`test_somente_organizador_distribui`](../tests/test_designacao_projetos_finais.py#L636) · 4 cenários
- [`test_somente_comite_tecnico_lista_os_proprios_projetos`](../tests/test_designacao_projetos_finais.py#L645) · 4 cenários
- [`test_sem_token_responde_401`](../tests/test_designacao_projetos_finais.py#L653)

</details>

### test_entregas_mentoria

Arquivo [`tests/test_entregas_mentoria.py`](../tests/test_entregas_mentoria.py) · integração · 8 funções · 8 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_gestor_cadastra_pagina_edita_e_exclui_marcos`](../tests/test_entregas_mentoria.py#L103)
- [`test_calendario_aceita_um_final_depois_dos_parciais`](../tests/test_entregas_mentoria.py#L128)
- [`test_calendario_requer_equipe_aprovada_ou_mentor_vigente`](../tests/test_entregas_mentoria.py#L145)
- [`test_entrega_no_prazo_preserva_historico_apos_prorrogacao`](../tests/test_entregas_mentoria.py#L164)
- [`test_entrega_parcial_recusa_marco_final_prazo_encerrado_e_proposta_reprovada`](../tests/test_entregas_mentoria.py#L211)
- [`test_submissao_final_grava_artefatos_e_permite_download_autorizado`](../tests/test_entregas_mentoria.py#L230)
- [`test_falha_na_validacao_do_repositorio_permite_repetir_submissao_final`](../tests/test_entregas_mentoria.py#L276)
- [`test_avaliador_acessa_relatorio_validado_enquanto_designacao_esta_vigente`](../tests/test_entregas_mentoria.py#L294)

</details>

### test_feedbacks_mentoria

Arquivo [`tests/test_feedbacks_mentoria.py`](../tests/test_feedbacks_mentoria.py) · integração · 54 funções · 70 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_mentor_registra_feedback`](../tests/test_feedbacks_mentoria.py#L81)
- [`test_autor_vem_do_jwt_e_campos_extras_sao_recusados`](../tests/test_feedbacks_mentoria.py#L92)
- [`test_outros_perfis_nao_escrevem`](../tests/test_feedbacks_mentoria.py#L104) · 3 cenários
- [`test_integrante_e_gestor_nao_escrevem`](../tests/test_feedbacks_mentoria.py#L109)
- [`test_dev_escreve_com_atribuicao_vigente`](../tests/test_feedbacks_mentoria.py#L115)
- [`test_escrita_sem_autenticacao`](../tests/test_feedbacks_mentoria.py#L122)
- [`test_404_igual_para_equipe_inexistente_e_de_outro_mentor`](../tests/test_feedbacks_mentoria.py#L129)
- [`test_payload_invalido`](../tests/test_feedbacks_mentoria.py#L152) · 7 cenários
- [`test_texto_no_limite_e_aparado`](../tests/test_feedbacks_mentoria.py#L157)
- [`test_todos_os_status`](../tests/test_feedbacks_mentoria.py#L163) · 4 cenários
- [`test_edicao_encerrada_bloqueia_escrita_e_mantem_leitura`](../tests/test_feedbacks_mentoria.py#L167)
- [`test_equipe_inelegivel`](../tests/test_feedbacks_mentoria.py#L181)
- [`test_equipe_sem_proposta_aprovada`](../tests/test_feedbacks_mentoria.py#L186)
- [`test_feedback_com_marco_e_com_entrega`](../tests/test_feedbacks_mentoria.py#L204)
- [`test_vinculos_inconsistentes`](../tests/test_feedbacks_mentoria.py#L223)
- [`test_banco_recusa_vinculos_inconsistentes`](../tests/test_feedbacks_mentoria.py#L241)
- [`test_trigger_bloqueia_update_e_delete`](../tests/test_feedbacks_mentoria.py#L263)
- [`test_apagar_equipe_ou_usuario_com_feedback_e_recusado`](../tests/test_feedbacks_mentoria.py#L275)
- [`test_correcao_cria_nova_linha_e_marca_o_original`](../tests/test_feedbacks_mentoria.py#L283)
- [`test_segunda_correcao_do_mesmo_feedback_da_409`](../tests/test_feedbacks_mentoria.py#L300)
- [`test_correcoes_simultaneas_so_uma_vence`](../tests/test_feedbacks_mentoria.py#L307)
- [`test_correcao_de_outro_autor_ou_de_outra_equipe`](../tests/test_feedbacks_mentoria.py#L327)
- [`test_banco_recusa_correcao_de_outra_equipe`](../tests/test_feedbacks_mentoria.py#L343)
- [`test_leitura_por_perfil`](../tests/test_feedbacks_mentoria.py#L361)
- [`test_leitura_sem_autenticacao`](../tests/test_feedbacks_mentoria.py#L389)
- [`test_mentor_substituido_perde_acesso_e_o_novo_ve_o_historico`](../tests/test_feedbacks_mentoria.py#L393)
- [`test_vinculo_encerrado_perde_acesso`](../tests/test_feedbacks_mentoria.py#L412)
- [`test_duas_organizacoes`](../tests/test_feedbacks_mentoria.py#L423)
- [`test_paginacao_e_ordem_estavel_com_empate`](../tests/test_feedbacks_mentoria.py#L449)
- [`test_ordem_decrescente_por_data`](../tests/test_feedbacks_mentoria.py#L473)
- [`test_paginacao_invalida`](../tests/test_feedbacks_mentoria.py#L482) · 6 cenários
- [`test_limites_validos`](../tests/test_feedbacks_mentoria.py#L486)
- [`test_sem_chave_cada_pedido_cria_um_feedback`](../tests/test_feedbacks_mentoria.py#L495)
- [`test_mesma_chave_e_mesmo_conteudo_devolve_o_mesmo`](../tests/test_feedbacks_mentoria.py#L500)
- [`test_mesma_chave_com_conteudo_diferente_da_409`](../tests/test_feedbacks_mentoria.py#L513)
- [`test_chaves_diferentes_criam_dois`](../tests/test_feedbacks_mentoria.py#L522)
- [`test_chave_com_entrega_derivada_repete_com_200`](../tests/test_feedbacks_mentoria.py#L529)
- [`test_chave_invalida`](../tests/test_feedbacks_mentoria.py#L538)
- [`test_chaves_iguais_de_autores_diferentes_nao_colidem`](../tests/test_feedbacks_mentoria.py#L542)
- [`test_pedidos_simultaneos_com_a_mesma_chave`](../tests/test_feedbacks_mentoria.py#L550)
- [`test_integrantes_confirmados_recebem_uma_notificacao_sem_o_texto`](../tests/test_feedbacks_mentoria.py#L578)
- [`test_repeticao_da_chave_nao_duplica_a_notificacao`](../tests/test_feedbacks_mentoria.py#L614)
- [`test_falha_ao_notificar_nao_derruba_o_feedback`](../tests/test_feedbacks_mentoria.py#L620)
- [`test_nenhum_email_e_enfileirado`](../tests/test_feedbacks_mentoria.py#L631)
- [`test_equipe_sem_outros_integrantes_nao_notifica`](../tests/test_feedbacks_mentoria.py#L637)
- [`test_painel_traz_campos_novos_e_mantem_os_antigos`](../tests/test_feedbacks_mentoria.py#L648)
- [`test_painel_detalhe_com_feedbacks_recentes_sem_texto_completo`](../tests/test_feedbacks_mentoria.py#L675)
- [`test_dias_sem_feedback_conta_dias_inteiros`](../tests/test_feedbacks_mentoria.py#L687)
- [`test_painel_conta_feedback_de_mentor_anterior`](../tests/test_feedbacks_mentoria.py#L701)
- [`test_historico_junta_entregas_e_feedbacks_na_ordem`](../tests/test_feedbacks_mentoria.py#L712)
- [`test_historico_paginado_sem_repetir_nem_perder`](../tests/test_feedbacks_mentoria.py#L751)
- [`test_historico_so_com_feedbacks_com_entregas_e_vazio`](../tests/test_feedbacks_mentoria.py#L767)
- [`test_historico_ignora_a_submissao_final`](../tests/test_feedbacks_mentoria.py#L778)
- [`test_marco_com_feedback_nao_pode_ser_excluido`](../tests/test_feedbacks_mentoria.py#L803)

</details>

### test_mentores

Arquivo [`tests/test_mentores.py`](../tests/test_mentores.py) · integração · 44 funções · 112 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_cadastro_por_perfis_autorizados`](../tests/test_mentores.py#L100) · 3 cenários
- [`test_campos_obrigatorios`](../tests/test_mentores.py#L131) · 6 cenários
- [`test_campos_invalidos`](../tests/test_mentores.py#L159) · 12 cenários
- [`test_email_duplicado_entre_perfis`](../tests/test_mentores.py#L170)
- [`test_perfis_proibidos`](../tests/test_mentores.py#L201) · 24 cenários
- [`test_admin_sem_token`](../tests/test_mentores.py#L213) · 8 cenários
- [`test_gestor_pendente_nao_cadastra`](../tests/test_mentores.py#L217)
- [`test_listar_consultar_editar`](../tests/test_mentores.py#L234)
- [`test_edicao_nao_contorna_validacoes`](../tests/test_mentores.py#L262) · 6 cenários
- [`test_edicao_email_duplicado`](../tests/test_mentores.py#L274)
- [`test_consulta_nao_confunde_outro_perfil`](../tests/test_mentores.py#L288) · 2 cenários
- [`test_convite_seguro_e_entrega_pela_fila`](../tests/test_mentores.py#L306)
- [`test_consulta_convite_exibe_perfil_e_termos`](../tests/test_mentores.py#L325)
- [`test_ativacao_completa_aceites_login_e_uso_unico`](../tests/test_mentores.py#L341)
- [`test_token_recusado`](../tests/test_mentores.py#L366) · 3 cenários
- [`test_ativacao_incompleta_nao_consume_token`](../tests/test_mentores.py#L397) · 6 cenários
- [`test_rejeita_aceite_repetido_ou_desatualizado`](../tests/test_mentores.py#L405)
- [`test_reenvio_revoga_token_antigo`](../tests/test_mentores.py#L415)
- [`test_desativacao_revoga_acesso_preserva_dados_e_reativacao`](../tests/test_mentores.py#L431)
- [`test_admin_nao_ativa_mentor_pendente_e_desativacao_revoga_convite`](../tests/test_mentores.py#L465)
- [`test_alterar_email_exige_nova_ativacao`](../tests/test_mentores.py#L485)
- [`test_ativacoes_simultaneas_consumem_token_uma_vez`](../tests/test_mentores.py#L504)
- [`test_elegibilidade_be_s5_11`](../tests/test_mentores.py#L526)
- [`test_falha_de_fila_mantem_cadastro_pendente`](../tests/test_mentores.py#L547)
- [`test_rollback_nao_deixa_cadastro_convite_ou_email`](../tests/test_mentores.py#L557)
- [`test_operacoes_administrativas_autorizadas`](../tests/test_mentores.py#L586) · 3 cenários
- [`test_cadastro_generico_nao_contorna_rn33`](../tests/test_mentores.py#L628) · 6 cenários
- [`test_cadastro_generico_envia_convite_sem_senha`](../tests/test_mentores.py#L646)
- [`test_cadastro_dos_demais_perfis_preserva_contrato`](../tests/test_mentores.py#L667)
- [`test_convite_nao_autentica_nem_acessa_rota_de_negocio`](../tests/test_mentores.py#L679)
- [`test_aceites_de_outra_edicao_nao_ativam`](../tests/test_mentores.py#L688)
- [`test_falha_apos_aceites_desfaz_ativacao`](../tests/test_mentores.py#L694)
- [`test_reativacao_exige_termos_e_convite_renovado_preserva_senha`](../tests/test_mentores.py#L711)
- [`test_desativacao_simultanea_a_ativacao_impede_acesso`](../tests/test_mentores.py#L762)
- [`test_edicao_do_convite_e_aceites_em_duas_edicoes_validas`](../tests/test_mentores.py#L832)
- [`test_reenvio_e_clientes_independentes_por_edicao`](../tests/test_mentores.py#L862)
- [`test_dois_convites_antes_do_worker_entregam_apenas_o_atual`](../tests/test_mentores.py#L882)
- [`test_worker_descarta_convite_revogado_depois_de_reservar`](../tests/test_mentores.py#L906)
- [`test_mensagem_ja_enviada_permanece_no_historico`](../tests/test_mentores.py#L937)
- [`test_envio_em_andamento_termina_antes_da_revogacao`](../tests/test_mentores.py#L947)
- [`test_falha_enfileiramento_visivel_e_recuperacao_sem_segredos`](../tests/test_mentores.py#L984)
- [`test_falha_entrega_visivel_e_novo_convite`](../tests/test_mentores.py#L1010)
- [`test_rollback_do_reenvio_preserva_convite_e_outbox_anteriores`](../tests/test_mentores.py#L1025)
- [`test_openapi_contrato_de_edicao_e_pendencia`](../tests/test_mentores.py#L1046)

</details>

### test_painel_mentor

Arquivo [`tests/test_painel_mentor.py`](../tests/test_painel_mentor.py) · integração · 21 funções · 35 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_painel_agrega_progresso_e_pendencias`](../tests/test_painel_mentor.py#L125)
- [`test_edicao_sem_calendario`](../tests/test_painel_mentor.py#L162)
- [`test_mentor_sem_equipes`](../tests/test_painel_mentor.py#L171)
- [`test_paginacao_mantem_resumo_de_todas_as_equipes`](../tests/test_painel_mentor.py#L177)
- [`test_parametros_invalidos`](../tests/test_painel_mentor.py#L199) · 4 cenários
- [`test_filtros_por_edicao_e_equipe`](../tests/test_painel_mentor.py#L203)
- [`test_detalhe_traz_integrantes_calendario_e_entregas`](../tests/test_painel_mentor.py#L223)
- [`test_edicao_encerrada_nao_tem_pendencias_em_aberto`](../tests/test_painel_mentor.py#L250) · 2 cenários
- [`test_nao_vaza_dados_sensiveis`](../tests/test_painel_mentor.py#L263)
- [`test_equipe_nao_designada_e_de_outro_mentor`](../tests/test_painel_mentor.py#L309)
- [`test_mentor_substituido_perde_o_acesso_e_o_novo_ve_o_historico`](../tests/test_painel_mentor.py#L319)
- [`test_atribuicao_encerrada`](../tests/test_painel_mentor.py#L332)
- [`test_equipe_que_deixou_de_ser_elegivel`](../tests/test_painel_mentor.py#L353) · 3 cenários
- [`test_equipe_reprovada_nao_aparece_mesmo_com_vinculo_no_banco`](../tests/test_painel_mentor.py#L360)
- [`test_isolamento_entre_organizacoes`](../tests/test_painel_mentor.py#L376)
- [`test_exige_autenticacao`](../tests/test_painel_mentor.py#L390)
- [`test_perfis_sem_acesso`](../tests/test_painel_mentor.py#L398) · 4 cenários
- [`test_mentor_pendente_ou_desativado`](../tests/test_painel_mentor.py#L404)
- [`test_dev_ve_apenas_os_proprios_vinculos`](../tests/test_painel_mentor.py#L413)
- [`test_situacao_do_marco_sem_entrega`](../tests/test_painel_mentor.py#L430) · 5 cenários
- [`test_situacao_do_marco_com_entrega`](../tests/test_painel_mentor.py#L438) · 2 cenários

</details>

### test_validacao_submissao_final

Arquivo [`tests/test_validacao_submissao_final.py`](../tests/test_validacao_submissao_final.py) · unitário · 11 funções · 31 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_normalizar_repositorio`](../tests/test_validacao_submissao_final.py#L37) · 3 cenários
- [`test_rejeitar_url_fora_do_formato_de_repositorio`](../tests/test_validacao_submissao_final.py#L52) · 6 cenários
- [`test_confirmar_repositorio_publico_pela_api`](../tests/test_validacao_submissao_final.py#L57)
- [`test_rejeitar_repositorio_inacessivel_sem_seguir_redirecionamento`](../tests/test_validacao_submissao_final.py#L72) · 4 cenários
- [`test_rejeitar_metadados_sem_confirmacao_de_repositorio_publico`](../tests/test_validacao_submissao_final.py#L94) · 4 cenários
- [`test_falha_temporaria_na_resposta_do_github`](../tests/test_validacao_submissao_final.py#L115) · 6 cenários
- [`test_timeout_na_consulta_ao_github`](../tests/test_validacao_submissao_final.py#L124)
- [`test_ler_pdf_em_blocos_no_limite`](../tests/test_validacao_submissao_final.py#L151)
- [`test_limite_do_pdf_considera_a_soma_dos_blocos`](../tests/test_validacao_submissao_final.py#L162)
- [`test_tipo_de_midia_incorreto_rejeita_pdf_valido`](../tests/test_validacao_submissao_final.py#L171)
- [`test_rejeitar_pdfs_ilegiveis`](../tests/test_validacao_submissao_final.py#L186) · 3 cenários

</details>

### test_email_api

Arquivo [`tests/test_email_api.py`](../tests/test_email_api.py) · integração · 24 funções · 48 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_sem_token_responde_401`](../tests/test_email_api.py#L45) · 3 cenários
- [`test_perfis_sem_permissao_respondem_403`](../tests/test_email_api.py#L51) · 12 cenários
- [`test_organizador_com_conta_pendente_responde_403`](../tests/test_email_api.py#L60) · 3 cenários
- [`test_organizador_e_dev_acessam`](../tests/test_email_api.py#L67) · 2 cenários
- [`test_lista_os_mais_recentes_primeiro`](../tests/test_email_api.py#L79)
- [`test_lista_vazia_devolve_lista_vazia`](../tests/test_email_api.py#L90)
- [`test_resposta_nunca_traz_o_conteudo_da_mensagem_nem_a_chave`](../tests/test_email_api.py#L96)
- [`test_filtra_por_status`](../tests/test_email_api.py#L109)
- [`test_filtra_por_tipo`](../tests/test_email_api.py#L120)
- [`test_filtra_por_destinatario_sem_diferenciar_maiusculas`](../tests/test_email_api.py#L129)
- [`test_filtros_combinados`](../tests/test_email_api.py#L140)
- [`test_paginacao_por_limite_e_deslocamento`](../tests/test_email_api.py#L153)
- [`test_parametros_invalidos_respondem_422`](../tests/test_email_api.py#L174) · 6 cenários
- [`test_aceita_o_limite_maximo_de_100`](../tests/test_email_api.py#L181)
- [`test_consulta_mostra_a_situacao_do_envio`](../tests/test_email_api.py#L190)
- [`test_consulta_de_id_inexistente_responde_404`](../tests/test_email_api.py#L206)
- [`test_id_que_nao_e_uuid_responde_422`](../tests/test_email_api.py#L214) · 2 cenários
- [`test_reenviar_devolve_o_email_que_falhou_para_a_fila`](../tests/test_email_api.py#L225)
- [`test_o_worker_envia_o_email_reenviado`](../tests/test_email_api.py#L241)
- [`test_so_reenvia_o_que_falhou`](../tests/test_email_api.py#L262) · 3 cenários
- [`test_reenviar_duas_vezes_seguidas_na_segunda_responde_409`](../tests/test_email_api.py#L282)
- [`test_dois_reenvios_simultaneos_resultam_em_um_sucesso_e_um_conflito`](../tests/test_email_api.py#L290)
- [`test_swagger_documenta_as_rotas_de_email`](../tests/test_email_api.py#L310)
- [`test_swagger_nao_expoe_o_conteudo_da_mensagem_no_schema`](../tests/test_email_api.py#L340)

</details>

### test_email_envio

Arquivo [`tests/test_email_envio.py`](../tests/test_email_envio.py) · misto · 20 funções · 20 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_espera_dobra_a_cada_tentativa_e_para_no_teto`](../tests/test_email_envio.py#L25) · unitário
- [`test_envio_com_sucesso_marca_enviado_e_apaga_o_corpo`](../tests/test_email_envio.py#L35) · integração
- [`test_email_enviado_nao_e_enviado_de_novo`](../tests/test_email_envio.py#L55) · integração
- [`test_fila_vazia_nao_chama_o_provedor`](../tests/test_email_envio.py#L66) · integração
- [`test_falha_temporaria_reagenda_com_espera_e_guarda_o_motivo`](../tests/test_email_envio.py#L76) · integração
- [`test_nao_tenta_de_novo_antes_da_hora`](../tests/test_email_envio.py#L93) · integração
- [`test_a_espera_dobra_na_segunda_falha`](../tests/test_email_envio.py#L104) · integração
- [`test_depois_da_espera_envia_e_nao_perde_o_aviso`](../tests/test_email_envio.py#L116) · integração
- [`test_esgotadas_as_tentativas_o_email_vai_para_falha`](../tests/test_email_envio.py#L134) · integração
- [`test_erro_permanente_vai_direto_para_falha_sem_gastar_as_tentativas`](../tests/test_email_envio.py#L148) · integração
- [`test_erro_inesperado_do_provedor_e_tratado_como_temporario`](../tests/test_email_envio.py#L160) · integração
- [`test_falha_de_um_email_nao_impede_os_demais_do_lote`](../tests/test_email_envio.py#L172) · integração
- [`test_so_pega_pendentes_com_a_hora_vencida`](../tests/test_email_envio.py#L188) · integração
- [`test_lote_respeita_o_limite_e_comeca_pelos_mais_antigos`](../tests/test_email_envio.py#L205) · integração
- [`test_reserva_respeita_limite_com_plano_nested_loop`](../tests/test_email_envio.py#L217) · integração
- [`test_reserva_vencida_volta_para_a_fila_e_conta_outra_tentativa`](../tests/test_email_envio.py#L244) · integração
- [`test_reserva_ainda_valida_nao_e_tocada`](../tests/test_email_envio.py#L257) · integração
- [`test_reserva_vencida_sem_tentativas_restantes_vai_para_falha`](../tests/test_email_envio.py#L268) · integração
- [`test_o_envio_reserva_o_email_enquanto_o_provedor_trabalha`](../tests/test_email_envio.py#L287) · integração
- [`test_workers_simultaneos_nunca_enviam_o_mesmo_email_duas_vezes`](../tests/test_email_envio.py#L312) · integração

</details>

### test_email_eventos

Arquivo [`tests/test_email_eventos.py`](../tests/test_email_eventos.py) · integração · 16 funções · 16 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_convite_enfileira_o_aviso_para_quem_tem_conta`](../tests/test_email_eventos.py#L79)
- [`test_convite_para_quem_ainda_nao_tem_conta_tambem_gera_o_aviso`](../tests/test_email_eventos.py#L97)
- [`test_convite_recusado_pelas_regras_nao_gera_aviso`](../tests/test_email_eventos.py#L106)
- [`test_convidar_de_novo_depois_de_cancelar_gera_um_aviso_novo`](../tests/test_email_eventos.py#L123)
- [`test_concluir_a_inscricao_avisa_cada_integrante_com_o_protocolo`](../tests/test_email_eventos.py#L140)
- [`test_concluir_ja_homologada_avisa_a_inscricao_e_a_homologacao`](../tests/test_email_eventos.py#L158)
- [`test_conclusao_recusada_nao_gera_aviso`](../tests/test_email_eventos.py#L168)
- [`test_homologa_so_quando_o_ultimo_comprovante_e_aprovado_e_avisa_uma_unica_vez`](../tests/test_email_eventos.py#L179)
- [`test_envio_da_proposta_avisa_so_o_lider_com_o_protocolo`](../tests/test_email_eventos.py#L213)
- [`test_envio_recusado_ou_repetido_nao_gera_aviso_a_mais`](../tests/test_email_eventos.py#L236)
- [`test_aviso_so_vale_se_a_acao_for_confirmada`](../tests/test_email_eventos.py#L248)
- [`test_resultado_avisa_todos_os_integrantes_aprovados_ou_nao`](../tests/test_email_eventos.py#L298)
- [`test_email_do_resultado_nao_traz_parecer_nem_nota`](../tests/test_email_eventos.py#L321)
- [`test_homologar_de_novo_ou_sem_permissao_nao_gera_aviso_a_mais`](../tests/test_email_eventos.py#L336)
- [`test_o_worker_entrega_os_avisos_do_convite`](../tests/test_email_eventos.py#L352)
- [`test_falha_do_provedor_nao_desfaz_a_acao_principal`](../tests/test_email_eventos.py#L367)

</details>

### test_email_fila

Arquivo [`tests/test_email_fila.py`](../tests/test_email_fila.py) · misto · 16 funções · 27 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_enfileirar_grava_o_email_pendente_com_o_conteudo_pronto`](../tests/test_email_fila.py#L59) · integração
- [`test_destinatario_com_espacos_nas_pontas_e_aparado`](../tests/test_email_fila.py#L79) · integração
- [`test_mesma_chave_nao_enfileira_o_aviso_duas_vezes`](../tests/test_email_fila.py#L87) · integração
- [`test_sem_chave_cada_chamada_gera_um_email`](../tests/test_email_fila.py#L96) · integração
- [`test_chaves_diferentes_para_o_mesmo_destinatario_geram_dois_emails`](../tests/test_email_fila.py#L105) · integração
- [`test_so_existe_se_a_transacao_da_acao_for_confirmada`](../tests/test_email_fila.py#L114) · integração
- [`test_email_da_transacao_e_confirmado_junto_com_o_resto`](../tests/test_email_fila.py#L128) · integração
- [`test_destinatario_invalido_nao_entra_na_fila_e_a_acao_segue`](../tests/test_email_fila.py#L154) · 5 cenários · integração
- [`test_template_com_contexto_incompleto_nao_entra_na_fila`](../tests/test_email_fila.py#L176) · integração
- [`test_erro_do_banco_ao_gravar_o_email_nao_perde_o_resto_da_transacao`](../tests/test_email_fila.py#L187) · integração
- [`test_link_do_front_nao_duplica_barras`](../tests/test_email_fila.py#L214) · unitário
- [`test_banco_recusa_email_invalido`](../tests/test_email_fila.py#L247) · 8 cenários · integração
- [`test_banco_recusa_enviado_sem_data_de_envio`](../tests/test_email_fila.py#L254) · integração
- [`test_banco_recusa_chave_repetida`](../tests/test_email_fila.py#L262) · integração
- [`test_enviado_pode_ficar_sem_corpo`](../tests/test_email_fila.py#L270) · integração
- [`test_apagar_o_usuario_preserva_o_historico_do_email`](../tests/test_email_fila.py#L280) · integração

</details>

### test_email_provedores

Arquivo [`tests/test_email_provedores.py`](../tests/test_email_provedores.py) · unitário · 18 funções · 28 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_mensagem_tem_remetente_unico_texto_e_alternativa_html`](../tests/test_email_provedores.py#L98)
- [`test_nome_e_assunto_com_acento_sao_aceitos`](../tests/test_email_provedores.py#L114)
- [`test_quebra_de_linha_em_cabecalho_e_recusada_sem_chegar_ao_servidor`](../tests/test_email_provedores.py#L138) · 3 cenários
- [`test_starttls_autentica_e_envia_uma_vez`](../tests/test_email_provedores.py#L150)
- [`test_ssl_usa_conexao_segura_desde_o_inicio_sem_starttls`](../tests/test_email_provedores.py#L159)
- [`test_sem_seguranca_e_sem_usuario_so_conecta_e_envia`](../tests/test_email_provedores.py#L166)
- [`test_classifica_o_erro_como_temporario_ou_permanente`](../tests/test_email_provedores.py#L200) · 9 cenários
- [`test_mensagem_de_erro_traz_o_codigo_do_servidor_e_nunca_a_senha`](../tests/test_email_provedores.py#L207)
- [`test_erro_longo_do_servidor_e_cortado_em_500_caracteres`](../tests/test_email_provedores.py#L219)
- [`test_console_registra_so_destinatario_e_assunto_e_nao_o_corpo`](../tests/test_email_provedores.py#L231)
- [`test_provedor_falso_guarda_as_mensagens_e_falha_na_ordem_programada`](../tests/test_email_provedores.py#L240)
- [`test_provedor_padrao_e_o_console`](../tests/test_email_provedores.py#L261)
- [`test_provedor_smtp_sai_das_variaveis_de_ambiente`](../tests/test_email_provedores.py#L267)
- [`test_provedor_definido_a_mao_tem_prioridade`](../tests/test_email_provedores.py#L288)
- [`test_smtp_sem_servidor_impede_a_api_de_subir`](../tests/test_email_provedores.py#L299)
- [`test_smtp_com_servidor_e_remetente_e_aceito`](../tests/test_email_provedores.py#L304)
- [`test_provedor_desconhecido_e_recusado`](../tests/test_email_provedores.py#L308)
- [`test_senha_do_smtp_nao_aparece_na_representacao_da_configuracao`](../tests/test_email_provedores.py#L313)

</details>

### test_email_templates

Arquivo [`tests/test_email_templates.py`](../tests/test_email_templates.py) · unitário · 13 funções · 32 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_todo_tipo_tem_template_de_texto_e_html`](../tests/test_email_templates.py#L37)
- [`test_renderiza_assunto_texto_e_html_com_o_link`](../tests/test_email_templates.py#L44) · 9 cenários
- [`test_falta_de_valor_no_contexto_e_erro_e_nao_e_mail_incompleto`](../tests/test_email_templates.py#L57) · 9 cenários
- [`test_assuntos_com_protocolo_trazem_o_numero`](../tests/test_email_templates.py#L65)
- [`test_html_escapa_valores_e_o_texto_simples_nao`](../tests/test_email_templates.py#L70)
- [`test_assunto_continua_em_uma_linha_mesmo_com_quebra_no_valor`](../tests/test_email_templates.py#L79)
- [`test_sem_link_o_email_sai_sem_botao`](../tests/test_email_templates.py#L88)
- [`test_convite_sem_nome_de_equipe_ou_de_lider_usa_texto_generico`](../tests/test_email_templates.py#L97)
- [`test_resultado_diz_so_se_a_proposta_foi_aprovada`](../tests/test_email_templates.py#L113) · 2 cenários
- [`test_resultado_nunca_expoe_parecer_nem_nota_mesmo_que_venham_no_contexto`](../tests/test_email_templates.py#L122)
- [`test_data_e_hora_saem_no_horario_de_brasilia`](../tests/test_email_templates.py#L144) · 3 cenários
- [`test_protocolo_da_proposta_mostra_o_horario_de_brasilia`](../tests/test_email_templates.py#L148)
- [`test_confirmacao_e_recuperacao_orientam_quem_nao_fez_o_pedido`](../tests/test_email_templates.py#L155)

</details>

### test_notificacao_service

Arquivo [`tests/test_notificacao_service.py`](../tests/test_notificacao_service.py) · unitário · 5 funções · 5 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_pagina_vazia_preserva_total_do_filtro_sem_buscar_pareceres`](../tests/test_notificacao_service.py#L58)
- [`test_pareceres_sao_reutilizados_por_proposta_sem_misturar_resultados`](../tests/test_notificacao_service.py#L81)
- [`test_nova_listagem_busca_parecer_atualizado`](../tests/test_notificacao_service.py#L108)
- [`test_falha_ao_ler_segunda_equipe_nao_persiste_lote_parcial`](../tests/test_notificacao_service.py#L132)
- [`test_avisos_da_central_sao_adicionados_depois_do_flush_dos_avisos_de_resultado`](../tests/test_notificacao_service.py#L153)

</details>

### test_notificacoes

Arquivo [`tests/test_notificacoes.py`](../tests/test_notificacoes.py) · integração · 49 funções · 53 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_notificar_grava_um_aviso_por_destinatario`](../tests/test_notificacoes.py#L82)
- [`test_repetir_o_mesmo_fato_nao_duplica`](../tests/test_notificacoes.py#L107)
- [`test_destinatario_repetido_na_lista_recebe_uma_vez`](../tests/test_notificacoes.py#L118)
- [`test_sem_destinatarios_nao_faz_nada`](../tests/test_notificacoes.py#L123)
- [`test_a_mesma_chave_vale_por_usuario`](../tests/test_notificacoes.py#L127)
- [`test_gravacoes_simultaneas_do_mesmo_fato_criam_um_so_aviso`](../tests/test_notificacoes.py#L133)
- [`test_resultado_nao_passa_pela_funcao_unica`](../tests/test_notificacoes.py#L160)
- [`test_referencia_exige_tipo_e_id_juntos`](../tests/test_notificacoes.py#L165)
- [`test_falha_ao_gravar_nao_derruba_a_acao_principal`](../tests/test_notificacoes.py#L170)
- [`test_erro_da_escrita_anterior_nao_e_engolido_como_falha_do_aviso`](../tests/test_notificacoes.py#L194)
- [`test_chat_nao_enfileira_email`](../tests/test_notificacoes.py#L219)
- [`test_o_servico_de_notificacao_nao_depende_do_modulo_de_email`](../tests/test_notificacoes.py#L233)
- [`test_todos_os_tipos_sao_aceitos`](../tests/test_notificacoes.py#L240)
- [`test_listagem_exige_login`](../tests/test_notificacoes.py#L249)
- [`test_conta_pendente_nao_acessa`](../tests/test_notificacoes.py#L256)
- [`test_item_generico_tem_os_campos_da_central`](../tests/test_notificacoes.py#L261)
- [`test_marcar_como_lida_e_idempotente`](../tests/test_notificacoes.py#L280)
- [`test_marcar_todas_como_lidas`](../tests/test_notificacoes.py#L303)
- [`test_filtro_por_tipo`](../tests/test_notificacoes.py#L318)
- [`test_paginacao_com_total_no_cabecalho`](../tests/test_notificacoes.py#L328)
- [`test_total_acompanha_o_filtro`](../tests/test_notificacoes.py#L349)
- [`test_parametros_invalidos`](../tests/test_notificacoes.py#L362) · 4 cenários
- [`test_o_limite_padrao_e_100`](../tests/test_notificacoes.py#L366)
- [`test_cors_expoe_o_total_ao_navegador`](../tests/test_notificacoes.py#L379)
- [`test_ninguem_ve_notificacao_de_outro`](../tests/test_notificacoes.py#L391)
- [`test_dev_so_ve_as_proprias`](../tests/test_notificacoes.py#L403)
- [`test_marcar_a_de_outro_da_404_igual_a_inexistente_e_nao_altera`](../tests/test_notificacoes.py#L412)
- [`test_marcar_todas_nao_toca_nas_dos_outros`](../tests/test_notificacoes.py#L426)
- [`test_id_invalido_da_422`](../tests/test_notificacoes.py#L435)
- [`test_leituras_simultaneas_sao_consistentes`](../tests/test_notificacoes.py#L442)
- [`test_swagger_documenta_as_rotas_e_os_erros`](../tests/test_notificacoes.py#L462)
- [`test_resposta_do_rf33_continua_valida_e_ganha_so_campos_novos`](../tests/test_notificacoes.py#L491)
- [`test_marcar_resultado_como_lido_pelo_notificacao_id_mantem_o_formato`](../tests/test_notificacoes.py#L526)
- [`test_resultado_convive_com_os_demais_tipos_na_mesma_lista`](../tests/test_notificacoes.py#L550)
- [`test_convite_avisa_quem_ja_tem_conta_e_o_email_continua`](../tests/test_notificacoes.py#L572)
- [`test_convite_a_quem_nao_tem_conta_so_gera_email`](../tests/test_notificacoes.py#L587)
- [`test_resposta_ao_convite_avisa_o_lider`](../tests/test_notificacoes.py#L593) · 2 cenários
- [`test_resposta_recusada_pelas_regras_nao_avisa`](../tests/test_notificacoes.py#L607)
- [`test_falha_ao_notificar_nao_derruba_o_convite_nem_o_email`](../tests/test_notificacoes.py#L615)
- [`test_falha_ao_notificar_a_resposta_nao_desfaz_o_aceite`](../tests/test_notificacoes.py#L631)
- [`test_inscricao_concluida_avisa_cada_integrante`](../tests/test_notificacoes.py#L647)
- [`test_equipe_homologada_avisa_uma_vez_cada_integrante`](../tests/test_notificacoes.py#L660)
- [`test_conclusao_recusada_nao_avisa`](../tests/test_notificacoes.py#L677)
- [`test_envio_da_proposta_avisa_so_o_lider`](../tests/test_notificacoes.py#L684)
- [`test_resultado_cria_a_central_junto_do_rf33_para_todos`](../tests/test_notificacoes.py#L700)
- [`test_atribuicao_de_mentor_notifica_equipe_e_mentor_na_central`](../tests/test_notificacoes.py#L723)
- [`test_substituicao_notifica_o_mentor_anterior`](../tests/test_notificacoes.py#L744)
- [`test_falha_ao_publicar_deixa_o_evento_pendente_e_mantem_a_atribuicao`](../tests/test_notificacoes.py#L756)
- [`test_backfill_traz_o_historico_como_lido`](../tests/test_notificacoes.py#L786)

</details>

### test_banco_de_teste

Arquivo [`tests/test_banco_de_teste.py`](../tests/test_banco_de_teste.py) · integração · 2 funções · 2 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_testes_usam_um_banco_proprio`](../tests/test_banco_de_teste.py#L5)
- [`test_a_api_e_os_testes_falam_com_o_mesmo_banco`](../tests/test_banco_de_teste.py#L11)

</details>

### test_health

Arquivo [`tests/test_health.py`](../tests/test_health.py) · integração · 1 função · 1 cenário.

<details>
<summary>Ver funções de teste</summary>

- [`test_health`](../tests/test_health.py#L1)

</details>

### test_migrations

Arquivo [`tests/test_migrations.py`](../tests/test_migrations.py) · integração · 38 funções · 41 cenários.

<details>
<summary>Ver funções de teste</summary>

- [`test_migration_aplicada`](../tests/test_migrations.py#L116)
- [`test_enums_batem_com_banco`](../tests/test_migrations.py#L125)
- [`test_models_batem_com_banco`](../tests/test_migrations.py#L149)
- [`test_orm_usa_padroes_do_banco`](../tests/test_migrations.py#L168)
- [`test_pessoa_em_duas_equipes_do_mesmo_hackathon`](../tests/test_migrations.py#L202)
- [`test_pessoa_em_equipes_de_hackathons_diferentes`](../tests/test_migrations.py#L213)
- [`test_membro_com_hackathon_diferente_do_da_equipe`](../tests/test_migrations.py#L223)
- [`test_um_lider_por_equipe`](../tests/test_migrations.py#L232)
- [`test_min_integrantes_maior_que_max`](../tests/test_migrations.py#L243)
- [`test_convite_pendente_repetido`](../tests/test_migrations.py#L267)
- [`test_novo_convite_depois_de_recusa`](../tests/test_migrations.py#L278)
- [`test_convite_aceito_sem_data_de_resposta`](../tests/test_migrations.py#L288)
- [`test_aceite_duplicado`](../tests/test_migrations.py#L306)
- [`test_duas_versoes_vigentes_do_mesmo_termo`](../tests/test_migrations.py#L322)
- [`test_termo_sem_conteudo_nem_url`](../tests/test_migrations.py#L332)
- [`test_comprovante_recusado_sem_motivo`](../tests/test_migrations.py#L348)
- [`test_reenvio_de_comprovante_depois_de_recusa`](../tests/test_migrations.py#L358)
- [`test_dois_comprovantes_pendentes`](../tests/test_migrations.py#L367)
- [`test_tema_com_ods_invalido`](../tests/test_migrations.py#L392)
- [`test_rascunho_incompleto_e_aceito`](../tests/test_migrations.py#L404)
- [`test_proposta_enviada_sem_tema`](../tests/test_migrations.py#L413)
- [`test_proposta_enviada_completa`](../tests/test_migrations.py#L429)
- [`test_duas_propostas_da_mesma_equipe`](../tests/test_migrations.py#L445)
- [`test_proposta_com_tema_de_outro_hackathon`](../tests/test_migrations.py#L456)
- [`test_protocolo_de_proposta_sem_submissao`](../tests/test_migrations.py#L469)
- [`test_usuario_novo_fica_ativo`](../tests/test_migrations.py#L481)
- [`test_papel_antigo_nao_existe_mais`](../tests/test_migrations.py#L490)
- [`test_mentor_com_max_equipes_zero`](../tests/test_migrations.py#L498)
- [`test_migration_de_autenticacao_aplicada`](../tests/test_migrations.py#L512)
- [`test_usuario_novo_nasce_ativo_sem_senha_nem_bloqueio`](../tests/test_migrations.py#L521)
- [`test_email_repetido_em_outras_maiusculas`](../tests/test_migrations.py#L536)
- [`test_tentativas_de_login_negativas`](../tests/test_migrations.py#L545)
- [`test_migration_de_rubricas_aplicada`](../tests/test_migrations.py#L581)
- [`test_duas_rubricas_na_mesma_edicao`](../tests/test_migrations.py#L590)
- [`test_criterio_de_rubrica_invalido`](../tests/test_migrations.py#L609) · 4 cenários
- [`test_criterio_repetido_na_rubrica`](../tests/test_migrations.py#L617)
- [`test_rascunho_de_rubrica_pode_ser_alterado`](../tests/test_migrations.py#L627)
- [`test_criterio_de_rubrica_publicada_nao_muda`](../tests/test_migrations.py#L642)

</details>
