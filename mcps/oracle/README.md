# MCP Oracle (`mcp-oracle`)

Servidor MCP em Python para acesso a banco de dados Oracle via `oracledb` (modo thin — sem Oracle Client instalado).

## Ferramentas expostas

| Tool | Descrição |
|---|---|
| `executar_query` | Executa SELECT e retorna linhas como lista de dicionários |
| `executar_dml` | Executa INSERT, UPDATE ou DELETE com commit automático |
| `listar_tabelas` | Lista tabelas de um schema |
| `descrever_tabela` | Retorna colunas com tipo, tamanho e obrigatoriedade |
| `executar_procedure` | Chama stored procedure com parâmetros IN |

## Requisitos

- Python 3.11+
- Acesso de rede ao banco Oracle

## Instalação de dependências

```bash
uv pip install mcp oracledb python-dotenv
# ou
pip install mcp oracledb python-dotenv
```

## Configuração

Crie um arquivo `.env` na raiz do projeto:

```env
ORACLE_USER=usuario
ORACLE_PASSWORD=senha
ORACLE_DSN=host:porta/service_name
```

Exemplo de DSN: `localhost:1521/XEPDB1`

## Registro no Claude Code

```bash
make mcp-add
# ou diretamente:
claude mcp add --scope local mcp-oracle python mcps/oracle/mcp-oracle.py
```

## Remoção

```bash
make mcp-remove
```

## Referência das ferramentas

### `executar_query`

Executa uma query SELECT com suporte a bind variables.

```
Parâmetros:
  sql        — instrução SELECT (ex: "SELECT * FROM clientes WHERE id = :id")
  parametros — dicionário de bind variables (ex: {"id": 42})

Retorno: lista de dicionários, uma entrada por linha
```

### `executar_dml`

Executa INSERT, UPDATE ou DELETE com commit automático.

```
Parâmetros:
  sql        — instrução DML com bind variables
  parametros — dicionário de bind variables

Retorno: {"linhas_afetadas": int, "status": "OK"}
```

### `listar_tabelas`

Lista tabelas do schema do usuário conectado ou de um schema específico.

```
Parâmetros:
  schema — nome do schema Oracle (opcional)

Retorno: lista de {"schema": str, "tabela": str}
```

### `descrever_tabela`

Retorna as colunas de uma tabela com metadados.

```
Parâmetros:
  tabela — nome da tabela (case-insensitive)
  schema — schema da tabela (opcional)

Retorno: lista de {"coluna", "tipo", "tamanho", "obrigatorio"}
```

### `executar_procedure`

Chama uma stored procedure Oracle com parâmetros IN.

```
Parâmetros:
  nome       — nome da procedure (ex: "SCHEMA.PROC_NOME")
  parametros — dicionário de parâmetros IN (opcional)

Retorno: {"status": "OK"}
```

> Parâmetros OUT não são suportados.
