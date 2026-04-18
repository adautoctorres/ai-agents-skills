"""
MCP Server para acesso a banco de dados Oracle.

Dependências:
    pip install mcp oracledb

Variáveis de ambiente necessárias:
    ORACLE_USER     - usuário do banco
    ORACLE_PASSWORD - senha do banco
    ORACLE_DSN      - DSN no formato host:porta/service_name
                      Exemplo: localhost:1521/XEPDB1

Registro no Claude Code:
    claude mcp add --scope local mcp-oracle python mcp/mcp-oracle.py
"""

import os
from pathlib import Path
from typing import Any

import oracledb
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv(Path(__file__).parent.parent / ".env")

mcp = FastMCP("mcp-oracle")


def _get_connection() -> oracledb.Connection:
    """Cria e retorna uma conexão com o banco Oracle usando variáveis de ambiente."""
    user = os.environ.get("ORACLE_USER")
    password = os.environ.get("ORACLE_PASSWORD")
    dsn = os.environ.get("ORACLE_DSN")

    if not all([user, password, dsn]):
        raise ValueError(
            "Variáveis de ambiente ausentes. Defina ORACLE_USER, ORACLE_PASSWORD e ORACLE_DSN."
        )

    return oracledb.connect(user=user, password=password, dsn=dsn)


@mcp.tool()
def executar_query(sql: str, parametros: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """
    Executa uma query SELECT e retorna as linhas como lista de dicionários.

    Args:
        sql:        Instrução SQL SELECT. Use :nome para bind variables.
                    Exemplo: "SELECT id, nome FROM clientes WHERE id = :id"
        parametros: Dicionário de bind variables.
                    Exemplo: {"id": 42}

    Returns:
        Lista de dicionários, onde cada dicionário representa uma linha.
    """
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, parametros or {})
            colunas = [col[0].lower() for col in cur.description]
            return [dict(zip(colunas, linha)) for linha in cur.fetchall()]


@mcp.tool()
def executar_dml(sql: str, parametros: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Executa INSERT, UPDATE ou DELETE e retorna o número de linhas afetadas.

    Args:
        sql:        Instrução SQL DML. Use :nome para bind variables.
                    Exemplo: "UPDATE clientes SET nome = :nome WHERE id = :id"
        parametros: Dicionário de bind variables.
                    Exemplo: {"nome": "João", "id": 42}

    Returns:
        Dicionário com {"linhas_afetadas": int, "status": str}.
    """
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, parametros or {})
            linhas = cur.rowcount
            conn.commit()
            return {"linhas_afetadas": linhas, "status": "OK"}


@mcp.tool()
def listar_tabelas(schema: str | None = None) -> list[dict[str, str]]:
    """
    Lista as tabelas disponíveis no schema informado (padrão: schema do usuário conectado).

    Args:
        schema: Nome do schema Oracle (opcional). Se omitido, usa o schema do usuário conectado.

    Returns:
        Lista de dicionários com {"schema": str, "tabela": str}.
    """
    if schema:
        sql = (
            "SELECT owner AS schema, table_name AS tabela "
            "FROM all_tables WHERE owner = UPPER(:schema) ORDER BY table_name"
        )
        params: dict[str, Any] = {"schema": schema}
    else:
        sql = "SELECT user AS schema, table_name AS tabela FROM user_tables ORDER BY table_name"
        params = {}

    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            colunas = [col[0].lower() for col in cur.description]
            return [dict(zip(colunas, linha)) for linha in cur.fetchall()]


@mcp.tool()
def descrever_tabela(tabela: str, schema: str | None = None) -> list[dict[str, str]]:
    """
    Retorna as colunas de uma tabela com nome, tipo de dado, tamanho e obrigatoriedade.

    Args:
        tabela: Nome da tabela (case-insensitive).
        schema: Schema da tabela (opcional). Se omitido, usa o schema do usuário conectado.

    Returns:
        Lista de dicionários com {"coluna", "tipo", "tamanho", "obrigatorio"}.
    """
    owner = schema.upper() if schema else None
    sql = (
        "SELECT column_name AS coluna, "
        "       data_type AS tipo, "
        "       NVL(TO_CHAR(data_length), '-') AS tamanho, "
        "       CASE nullable WHEN 'N' THEN 'SIM' ELSE 'NAO' END AS obrigatorio "
        "FROM all_tab_columns "
        "WHERE table_name = UPPER(:tabela) "
        "  AND owner = NVL(UPPER(:schema), user) "
        "ORDER BY column_id"
    )
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"tabela": tabela, "schema": owner})
            colunas = [col[0].lower() for col in cur.description]
            return [dict(zip(colunas, linha)) for linha in cur.fetchall()]


@mcp.tool()
def executar_procedure(
    nome: str,
    parametros: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Chama uma stored procedure Oracle.

    Args:
        nome:       Nome da procedure (pode incluir schema, ex: "SCHEMA.PROC_NOME").
        parametros: Dicionário de parâmetros IN. Parâmetros OUT não são suportados aqui.

    Returns:
        Dicionário com {"status": "OK"} em caso de sucesso.
    """
    params = parametros or {}
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.callproc(nome, keywordParameters=params)
            conn.commit()
            return {"status": "OK"}


if __name__ == "__main__":
    mcp.run()
