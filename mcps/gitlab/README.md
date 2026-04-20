# MCP GitLab

Servidor MCP para acesso ao GitLab corporativo com leitura irrestrita e escrita controlada por flag.

## Funcionalidades

- Leitura irrestrita de projetos, MRs, issues, arquivos e atividade de usuários
- Escrita controlada por variável de ambiente (`GITLAB_WRITE_ENABLED`)
- Token nunca exposto ao agente
- Validação de escopo: toda operação verifica se o recurso pertence ao `GITLAB_GROUP_PATH`
- Rate limiting separado para leitura e escrita
- Cache com TTL de 120 s para requisições GET
- Deduplicação de issues por hash (title + description) por sessão
- Logs de auditoria em todas as operações
- Suporte a `dry_run` nas operações de escrita

## Requisitos

- Python 3.11+
- Dependências: `mcp`, `httpx`, `pydantic`, `python-dotenv`
- Instalação via `uv sync` na raiz do repositório

## Variáveis de ambiente

### Obrigatórias

| Variável | Descrição |
|---|---|
| `GITLAB_URL` | URL base da instância GitLab (ex: `https://gitlab.example.com`) |
| `GITLAB_TOKEN` | Personal Access Token com escopo `read_api` (e `api` para escrita) |
| `GITLAB_GROUP_PATH` | Caminho do grupo raiz permitido (ex: `minha-empresa/time`) |

### Opcionais

| Variável | Padrão | Descrição |
|---|---|---|
| `GITLAB_TIMEOUT` | `30` | Timeout HTTP em segundos |
| `GITLAB_RATE_LIMIT` | `60` | Requisições de leitura por minuto |
| `GITLAB_WRITE_ENABLED` | `false` | Habilita operações de escrita (`true`/`false`) |
| `GITLAB_WRITE_RATE_LIMIT` | `10` | Operações de escrita por minuto |
| `GITLAB_DRY_RUN` | `false` | Simula escritas sem executar (`true`/`false`) |
| `GITLAB_AGENT_LABEL` | `created-by-agent` | Label adicionada automaticamente às issues criadas |
| `GITLAB_SSL_VERIFY` | `true` | Valida certificado SSL (`true`/`false`) |

Defina as variáveis em um arquivo `.env` na raiz do repositório ou diretamente no ambiente.

## Registro e remoção

```bash
# Registrar
make mcp-gitlab-add

# Remover
make mcp-gitlab-remove
```

## Ferramentas disponíveis

### Leitura

| Ferramenta | Descrição |
|---|---|
| `gitlab_list_projects` | Lista projetos dentro do grupo permitido |
| `gitlab_get_project` | Retorna metadados de um projeto |
| `gitlab_list_merge_requests` | Lista MRs de um projeto (opened/closed/merged/all) |
| `gitlab_list_issues` | Lista issues com filtro por assignee e estado |
| `gitlab_get_file_content` | Retorna conteúdo de um arquivo de um repositório |
| `gitlab_search_code` | Busca código dentro do escopo do grupo |
| `gitlab_get_issue_notes` | Lista comentários de uma issue (filtrável por autor e data) |
| `gitlab_get_user_activity` | Lista eventos/atividades de um usuário no grupo |

### Escrita (requerem `GITLAB_WRITE_ENABLED=true`)

| Ferramenta | Descrição |
|---|---|
| `gitlab_create_issue` | Cria issue em projeto do grupo, com deduplicação automática |
| `gitlab_add_issue_comment` | Adiciona comentário em issue existente |

## Segurança

- **Escopo restrito:** todas as operações validam se o recurso pertence ao `GITLAB_GROUP_PATH`. Tentativas de acesso fora do escopo são bloqueadas e auditadas.
- **Token protegido:** o `GITLAB_TOKEN` é lido apenas pelo servidor e nunca repassado ao agente.
- **Path traversal:** caminhos de arquivo são normalizados e validados contra `..` e caracteres perigosos.
- **Escrita desabilitada por padrão:** operações de escrita exigem `GITLAB_WRITE_ENABLED=true` explícito.
- **Auditoria:** todas as operações geram log com `status`, `tool`, `resource` e detalhe. Escritas incluem o payload (sem campos sensíveis).

## Exemplos de uso

```
"Liste os projetos do time de backend"
→ gitlab_list_projects { group_path: "empresa/backend" }

"Quais MRs estão abertos no repo api-gateway?"
→ gitlab_list_merge_requests { project_path: "empresa/backend/api-gateway", state: "opened" }

"O que user fez na sexta-feira (18/04)?"
→ gitlab_get_user_activity { username: "user", after: "2026-04-18", before: "2026-04-19" }

"Mostre o Dockerfile do projeto api-gateway na branch develop"
→ gitlab_get_file_content { project_path: "empresa/backend/api-gateway", file_path: "Dockerfile", branch: "develop" }

"Cria issue 'Bug no login' no projeto auth-service" (requer GITLAB_WRITE_ENABLED=true)
→ gitlab_create_issue { project_path: "empresa/backend/auth-service", title: "Bug no login" }
```
