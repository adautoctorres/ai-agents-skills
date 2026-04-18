## Estrutura

```
.
├── .claude/
│   ├── agents/          # Sub-agentes invocáveis pelo Claude Code
│   ├── commands/        # Slash commands simples (atalhos de prompt)
│   ├── skills/          # Skills avançadas com templates e lógica própria
│   └── settings.json    # Configuração local (idioma, permissões)
├── docs/                # Guias detalhados
├── input/               # Arquivos de entrada para processamento
├── mcps/
│   └── oracle/          # Servidor MCP para banco Oracle
├── relatos/             # Relatos gerados pelo gitlab-report-formatter
└── pyproject.toml       # Dependências Python (mcp, oracledb, anthropic)
```

## Pré-requisitos

```bash
uv venv        # cria o ambiente virtual em .venv
uv sync        # instala as dependências do pyproject.toml
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

### Registrar

```bash
claude mcp add --scope local mcp-oracle python mcps/oracle/mcp-oracle.py
```

### Remover

```bash
claude mcp remove mcp-oracle --scope local

```

### Ferramentas disponíveis

| Servidor | Ferramenta MCP | Parâmetros |
|----------|----------------|------------|
| `mcp-oracle` | `mcp__mcp-oracle__executar_query` | `sql: str`, `parametros?: dict` |
| `mcp-oracle` | `mcp__mcp-oracle__executar_dml` | `sql: str`, `parametros?: dict` |
| `mcp-oracle` | `mcp__mcp-oracle__listar_tabelas` | `schema?: str` |
| `mcp-oracle` | `mcp__mcp-oracle__descrever_tabela` | `tabela: str`, `schema?: str` |
| `mcp-oracle` | `mcp__mcp-oracle__executar_procedure` | `nome: str`, `parametros?: dict` |

### Variáveis de ambiente (mcp-oracle)

```bash
ORACLE_USER=usuario
ORACLE_PASSWORD=senha
ORACLE_DSN=host:porta/service_name   # ex: localhost:1521/XEPDB1
```

## Documentação

- [Skills e Slash Commands](docs/guia-skills.md)
- [Servidor MCP Oracle](docs/guia-mcp.md)
