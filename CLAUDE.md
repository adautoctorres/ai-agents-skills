# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Visão geral

Repositório pessoal de agentes, skills e servidores MCP para o Claude Code. Composto por arquivos Markdown de configuração e scripts Python para servidores MCP.

## Privacidade e dados sensíveis

Nunca incluir em documentação, relatos, commits ou respostas: tokens, senhas, URLs internas de cluster, dados de conexão (DSN, hosts, portas), usuários de serviço ou qualquer credencial e dados de contextos do Kubernetes. Use variáveis de ambiente como referência. Esta regra se aplica a todos os artefatos gerados neste repositório.

## Configuração

- Linguagem padrão: **pt-BR** (definida em `.claude/settings.json`)
- Dependências Python: `anthropic`, `mcp`, `oracledb`, `dotenv`, `pyyaml` — gerenciadas via `uv` com `pyproject.toml` como única fonte de verdade. Para instalar: `uv sync`. Nunca criar `requirements.txt` avulsos.

## Slash Command (`.claude/commands/`)

### `/gitlab-report-formatter`

Atalho que invoca a skill `gitlab-report-formatter`. Aceita texto livre como argumento; se omitido, pergunta ao usuário o tipo de relato desejado.

## Skill (`.claude/skills/gitlab-report-formatter/`)

Transforma texto bruto (anotações, transcrições, bullets) em relatos estruturados prontos para issues do GitLab.

**Tipos suportados:** Registro de Atividades, Reunião/Ata, Apoio Técnico, Consultoria, Incidente, Status Report.

**Templates em `templates/`:** `registro-atividades.md`, `apoio-tecnico.md`, `ata-reuniao.md`, `incidente.md`.

**Regras de formatação:** `**seções**` em negrito (sem `#`/`##`), `- [ ]` para ações pendentes, sem labels.

**Persistência:** relatos salvos automaticamente em `relatos/{slug}-{yyyymmdd}.md`.

## Servidor MCP (`mcps/`)

### `mcps/oracle/mcp-oracle.py`

Servidor MCP para acesso a banco de dados Oracle via `oracledb`. Ferramentas expostas: `executar_query`, `executar_dml`, `listar_tabelas`, `descrever_tabela`, `executar_procedure`.

Requer variáveis de ambiente: `ORACLE_USER`, `ORACLE_PASSWORD`, `ORACLE_DSN`.

Registro: `make mcp-add` — remoção: `make mcp-remove`.

### `mcps/k8s/mcp-k8s.py`

Servidor MCP para interação segura com clusters Kubernetes via `kubectl`. 
Apenas operações de leitura permitidas (whitelist: `get`, `describe`, `logs`, `config`). Comandos destrutivos bloqueados. Saída sempre em JSON com campos `status`, `context`, `command`, `data`, `timestamp`.

Ferramentas expostas: `k8s_list_contexts`, `k8s_get_current_context`, `k8s_switch_context`, `k8s_get_pods`, `k8s_get_services`, `k8s_get_nodes`, `k8s_get_namespaces`, `k8s_describe_resource`, `k8s_get_logs`.

Variáveis de ambiente opcionais: `KUBECONFIG` (padrão: `~/.kube/config`), `KUBECTL_TIMEOUT` (padrão: `30`).

Registro: `make mcp-k8s-add` — remoção: `make mcp-k8s-remove`.

## Relatos (`relatos/`)

Pasta com os relatos gerados pelo `gitlab-report-formatter`, prontos para colar em issues do GitLab.

Convenção de nome: `{slug}-{yyyymmdd}.md` com sufixo sequencial (`-2`, `-3`) em caso de múltiplos relatos no mesmo dia.

## Entradas (`input/`)

Pasta para arquivos de entrada usados como insumo para geração de relatos ou processamento.
