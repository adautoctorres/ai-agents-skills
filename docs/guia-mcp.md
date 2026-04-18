# Guia: Servidor MCP

## O que é MCP

MCP (Model Context Protocol) é o protocolo que permite ao Claude Code chamar ferramentas externas. Um servidor MCP expõe funções que o Claude pode invocar durante a conversa.

## Servidor disponível: `mcp-oracle`

**Arquivo:** `mcps/oracle/mcp-oracle.py`

Servidor MCP para acesso a banco de dados Oracle. Usa a biblioteca `oracledb` (modo thin, sem cliente Oracle instalado).

### Registrar

```bash
make mcp-add
```

### Remover

```bash
make mcp-remove
```

### Variáveis de ambiente

Crie um arquivo `.env` na raiz do projeto:

```env
ORACLE_USER=usuario
ORACLE_PASSWORD=senha
ORACLE_DSN=host:porta/service_name
```

Exemplo de DSN: `localhost:1521/XEPDB1`

### Ferramentas expostas

#### `executar_query`

Executa uma query SELECT e retorna linhas como lista de dicionários.

```
Parâmetros:
  sql        — instrução SELECT com bind variables (:nome)
  parametros — dicionário de bind variables (opcional)

Retorno: lista de dicionários, uma entrada por linha
```

Exemplo de uso pelo Claude:
```
Liste os 10 primeiros clientes ativos do schema VENDAS.
```

#### `executar_dml`

Executa INSERT, UPDATE ou DELETE com commit automático.

```
Parâmetros:
  sql        — instrução DML com bind variables
  parametros — dicionário de bind variables (opcional)

Retorno: {"linhas_afetadas": int, "status": "OK"}
```

#### `listar_tabelas`

Lista tabelas disponíveis em um schema.

```
Parâmetros:
  schema — nome do schema (opcional; padrão: schema do usuário conectado)

Retorno: lista de {"schema": str, "tabela": str}
```

#### `descrever_tabela`

Retorna colunas de uma tabela com tipo, tamanho e obrigatoriedade.

```
Parâmetros:
  tabela — nome da tabela (case-insensitive)
  schema — schema da tabela (opcional)

Retorno: lista de {"coluna", "tipo", "tamanho", "obrigatorio"}
```

#### `executar_procedure`

Chama uma stored procedure Oracle com parâmetros IN.

```
Parâmetros:
  nome       — nome da procedure (pode incluir schema: "SCHEMA.PROC_NOME")
  parametros — dicionário de parâmetros IN (opcional)

Retorno: {"status": "OK"}
```

> Parâmetros OUT não são suportados por esta ferramenta.

## Dependências Python

```bash
uv sync   # instala mcp, oracledb, anthropic, dotenv
```

## Criando novos servidores MCP

Use a skill `mcp-builder` para orientação na criação de novos servidores MCP com FastMCP (Python) ou MCP SDK (TypeScript):

```
Crie um servidor MCP para [descrição do serviço]
```
