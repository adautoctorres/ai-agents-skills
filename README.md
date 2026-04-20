Repositório pessoal de agentes, skills e servidores MCP para o Claude Code. Centraliza automações de produtividade — formatação de relatos para GitLab, acesso a bancos Oracle, interação com Kubernetes e integração com GitLab corporativo via MCP.

## Estrutura

```
.
├── .claude/
│   ├── agents/          # Sub-agentes invocáveis pelo Claude Code
│   ├── commands/        # Slash commands simples (atalhos de prompt)
│   ├── skills/          # Skills avançadas com templates e lógica própria
│   └── settings.json    # Configuração local (idioma, permissões)
├── input/               # Arquivos de entrada para processamento
├── mcps/
│   ├── oracle/          # Servidor MCP para banco Oracle
│   ├── k8s/             # Servidor MCP para Kubernetes (somente leitura)
│   └── gitlab/          # Servidor MCP para GitLab corporativo
├── relatos/             # Relatos gerados pelo gitlab-report-formatter
└── pyproject.toml       # Dependências Python (mcp, oracledb, anthropic)
```

## Pré-requisitos

```bash
uv venv   # cria o ambiente virtual em .venv
uv sync   # instala as dependências do pyproject.toml
```

## Slash Commands

Arquivos únicos em `.claude/commands/`:

| Comando | O que faz |
|---------|-----------|
| `/gitlab-report-formatter <texto>` | Formata texto bruto em relato estruturado para issue do GitLab |

## Skills

Pastas em `.claude/skills/` com templates e lógica própria:

| Skill | O que faz |
|-------|-----------|
| `gitlab-report-formatter` | Transforma anotações brutas em relatos GitLab usando templates em `templates/` |

### Templates disponíveis

| Template | Tipo de relato |
|----------|---------------|
| `registro-atividades.md` | Registro de trabalho executado |
| `apoio-tecnico.md` | Chamado ou atendimento de suporte / consultoria |
| `ata-reuniao.md` | Reunião ou call com pauta e decisões |
| `incidente.md` | Problema ou falha em produção |

## Servidores MCP

### mcp-oracle

Acesso a banco de dados Oracle via `oracledb`.

```bash
make mcp-oracle-add      # registrar
make mcp-oracle-remove   # remover
```

| Ferramenta | Descrição |
|---|---|
| `executar_query` | Executa SELECT e retorna resultados |
| `executar_dml` | Executa INSERT/UPDATE/DELETE |
| `listar_tabelas` | Lista tabelas do schema |
| `descrever_tabela` | Descreve colunas de uma tabela |
| `executar_procedure` | Chama stored procedure |

Variáveis de ambiente: `ORACLE_USER`, `ORACLE_PASSWORD`, `ORACLE_DSN`

---

### mcp-k8s

Interação segura com clusters Kubernetes via `kubectl` (somente leitura).

```bash
make mcp-k8s-add      # registrar
make mcp-k8s-remove   # remover
```

| Ferramenta | Descrição |
|---|---|
| `k8s_list_contexts` | Lista contextos disponíveis no kubeconfig |
| `k8s_get_current_context` | Retorna o contexto ativo |
| `k8s_switch_context` | Troca o contexto ativo |
| `k8s_get_pods` | Lista pods de um namespace |
| `k8s_get_services` | Lista services de um namespace |
| `k8s_get_nodes` | Lista nós do cluster |
| `k8s_get_namespaces` | Lista namespaces disponíveis |
| `k8s_describe_resource` | Descreve um recurso Kubernetes |
| `k8s_get_logs` | Retorna logs de um pod |

Variáveis de ambiente opcionais: `KUBECONFIG` (padrão: `~/.kube/config`), `KUBECTL_TIMEOUT` (padrão: `30`)

---

### mcp-gitlab

Acesso ao GitLab corporativo com leitura irrestrita e escrita controlada por flag. Veja o [README completo](mcps/gitlab/README.md).

```bash
make mcp-gitlab-add      # registrar
make mcp-gitlab-remove   # remover
```

**Ferramentas de leitura:**

| Ferramenta | Descrição |
|---|---|
| `gitlab_list_projects` | Lista projetos do grupo |
| `gitlab_get_project` | Metadados de um projeto |
| `gitlab_list_merge_requests` | Lista MRs de um projeto |
| `gitlab_list_issues` | Lista issues com filtros |
| `gitlab_get_file_content` | Conteúdo de arquivo de um repositório |
| `gitlab_search_code` | Busca código no grupo |
| `gitlab_get_issue_notes` | Comentários de uma issue |
| `gitlab_get_user_activity` | Atividade de um usuário no grupo |

**Ferramentas de escrita** (requerem `GITLAB_WRITE_ENABLED=true`):

| Ferramenta | Descrição |
|---|---|
| `gitlab_create_issue` | Cria issue com deduplicação automática |
| `gitlab_add_issue_comment` | Adiciona comentário em issue existente |

Variáveis de ambiente obrigatórias: `GITLAB_URL`, `GITLAB_TOKEN`, `GITLAB_GROUP_PATH`

## Documentação

- [Servidor MCP GitLab](mcps/gitlab/README.md)
