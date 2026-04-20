#!/usr/bin/env python3
"""
MCP Server para GitLab corporativo (leitura + escrita controlada).

Ferramentas de leitura:
  - gitlab_list_projects         Lista projetos dentro do group_path permitido
  - gitlab_get_project           Retorna metadados de um projeto
  - gitlab_list_merge_requests   Lista MRs de um projeto
  - gitlab_list_issues           Lista issues com filtro por assignee e estado
  - gitlab_get_file_content      Retorna conteúdo de um arquivo em um repositório
  - gitlab_search_code           Busca código dentro do escopo do grupo
  - gitlab_get_issue_notes       Lista comentários/notas de uma issue
  - gitlab_get_user_activity     Lista eventos/atividades de um usuário no grupo

Ferramentas de escrita (requerem GITLAB_WRITE_ENABLED=true):
  - gitlab_create_issue          Cria issue em projeto do grupo (com deduplicação)
  - gitlab_add_issue_comment     Adiciona comentário em issue existente

Variáveis de ambiente obrigatórias:
  GITLAB_URL         URL base da instância GitLab (ex: https://gitlab.example.com)
  GITLAB_TOKEN       Personal Access Token (nunca exposto ao agente)
  GITLAB_GROUP_PATH  Caminho do grupo raiz (ex: minha-empresa/time)

Opcionais:
  GITLAB_TIMEOUT          Timeout HTTP em segundos (padrão: 30)
  GITLAB_RATE_LIMIT       Requisições de leitura por minuto (padrão: 60)
  GITLAB_WRITE_ENABLED    Habilita operações de escrita: true | false (padrão: false)
  GITLAB_WRITE_RATE_LIMIT Operações de escrita por minuto (padrão: 10)
  GITLAB_DRY_RUN          Simula escritas sem executar: true | false (padrão: false)
  GITLAB_AGENT_LABEL      Label adicionada automaticamente a issues (padrão: created-by-agent)
  GITLAB_SSL_VERIFY       Valida certificado SSL: true | false (padrão: true)
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field, field_validator

load_dotenv(Path(__file__).parent.parent.parent / ".env")

# ---------------------------------------------------------------------------
# Configuração via variáveis de ambiente
# ---------------------------------------------------------------------------

GITLAB_URL = os.getenv("GITLAB_URL", "").rstrip("/")
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN", "")
GITLAB_GROUP_PATH = os.getenv("GITLAB_GROUP_PATH", "").strip("/")
GITLAB_TIMEOUT = int(os.getenv("GITLAB_TIMEOUT", "30"))
GITLAB_RATE_LIMIT = int(os.getenv("GITLAB_RATE_LIMIT", "60"))
GITLAB_WRITE_ENABLED = os.getenv("GITLAB_WRITE_ENABLED", "false").lower() == "true"
GITLAB_WRITE_RATE_LIMIT = int(os.getenv("GITLAB_WRITE_RATE_LIMIT", "10"))
GITLAB_DRY_RUN = os.getenv("GITLAB_DRY_RUN", "false").lower() == "true"
GITLAB_AGENT_LABEL = os.getenv("GITLAB_AGENT_LABEL", "created-by-agent")
GITLAB_SSL_VERIFY: bool | str = os.getenv("GITLAB_SSL_VERIFY", "true").lower() != "false"

# Tamanhos máximos de payload para operações de escrita
_MAX_TITLE_LEN = 255
_MAX_DESCRIPTION_LEN = 10_000
_MAX_COMMENT_LEN = 5_000

# ---------------------------------------------------------------------------
# Logging / Auditoria
# ---------------------------------------------------------------------------

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [AUDIT] %(message)s",
)
logger = logging.getLogger("mcp-gitlab")


def _audit(tool: str, resource: str, success: bool, detail: str = "") -> None:
    status = "OK" if success else "BLOCKED"
    logger.info("status=%s tool=%r resource=%r detail=%r", status, tool, resource, detail)


def _audit_write(tool: str, resource: str, payload: Dict[str, Any], dry_run: bool) -> None:
    safe_payload = {
        k: ("***" if k.lower() in {"token", "password", "secret", "key"} else v)
        for k, v in payload.items()
    }
    mode = "DRY-RUN" if dry_run else "WRITE"
    logger.info(
        "mode=%s tool=%r resource=%r payload=%s",
        mode, tool, resource, json.dumps(safe_payload, ensure_ascii=False),
    )


# ---------------------------------------------------------------------------
# Rate limiter (token bucket simples — thread-safe via asyncio.Lock)
# ---------------------------------------------------------------------------

class _RateLimiter:
    def __init__(self, requests_per_minute: int) -> None:
        self._interval = 60.0 / max(requests_per_minute, 1)
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._interval - (now - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()


_rate_limiter = _RateLimiter(GITLAB_RATE_LIMIT)
_write_rate_limiter = _RateLimiter(GITLAB_WRITE_RATE_LIMIT)

# ---------------------------------------------------------------------------
# Cache leve com TTL (dict em memória)
# ---------------------------------------------------------------------------

_cache: Dict[str, tuple[Any, float]] = {}
_CACHE_TTL = 120.0  # segundos


def _cache_get(key: str) -> Optional[Any]:
    entry = _cache.get(key)
    if entry and (time.monotonic() - entry[1]) < _CACHE_TTL:
        return entry[0]
    return None


def _cache_set(key: str, value: Any) -> None:
    _cache[key] = (value, time.monotonic())


# Cache de deduplicação de issues (hash → issue_iid)
_issue_hashes: Dict[str, int] = {}


# ---------------------------------------------------------------------------
# Validação de escopo (CRÍTICO)
# ---------------------------------------------------------------------------

_DANGEROUS_CHARS = re.compile(r"[;|&`$<>()\n\r]")
_SAFE_PATH = re.compile(r"^[a-zA-Z0-9_.\/\-]+$")


def _sanitize(value: str, label: str = "parâmetro") -> str:
    if _DANGEROUS_CHARS.search(value):
        raise ValueError(f"Caractere não permitido em {label}: {value!r}")
    return value.strip()


def _validate_group_scope(path: str) -> None:
    """Garante que o path pertence ao grupo raiz configurado."""
    if not GITLAB_GROUP_PATH:
        raise PermissionError("GITLAB_GROUP_PATH não configurado.")
    normalized = path.strip("/")
    if not (normalized == GITLAB_GROUP_PATH or normalized.startswith(GITLAB_GROUP_PATH + "/")):
        _audit("scope-check", path, False, "fora do escopo")
        raise PermissionError(
            f"Acesso negado: '{path}' está fora do escopo permitido '{GITLAB_GROUP_PATH}'."
        )


def _validate_project_scope(project_path: str) -> None:
    """Garante que o project_path pertence ao grupo raiz."""
    _validate_group_scope(project_path)


def _validate_file_path(file_path: str) -> None:
    """Proteção contra path traversal em caminhos de arquivo."""
    normalized = os.path.normpath(file_path)
    if normalized.startswith("..") or "//" in file_path or ".." in file_path.split("/"):
        raise ValueError(f"Caminho de arquivo inválido (path traversal detectado): {file_path!r}")
    if not _SAFE_PATH.match(file_path):
        raise ValueError(f"Caminho de arquivo contém caracteres não permitidos: {file_path!r}")


# ---------------------------------------------------------------------------
# Cliente HTTP GitLab
# ---------------------------------------------------------------------------

def _headers() -> Dict[str, str]:
    if not GITLAB_TOKEN:
        raise EnvironmentError("GITLAB_TOKEN não configurado.")
    return {
        "PRIVATE-TOKEN": GITLAB_TOKEN,
        "Accept": "application/json",
    }


def _write_guard(tool: str) -> None:
    """Bloqueia operações de escrita quando GITLAB_WRITE_ENABLED=false."""
    if not GITLAB_WRITE_ENABLED:
        raise PermissionError(
            f"Operação de escrita bloqueada. "
            f"Defina GITLAB_WRITE_ENABLED=true para habilitar '{tool}'."
        )


async def _post(path: str, payload: Dict) -> Any:
    """Executa POST na API do GitLab com rate limiting de escrita."""
    if not GITLAB_URL:
        raise EnvironmentError("GITLAB_URL não configurado.")

    await _write_rate_limiter.acquire()

    if GITLAB_DRY_RUN:
        return {"dry_run": True, "would_post": path, "payload": payload}

    url = f"{GITLAB_URL}/api/v4{path}"
    async with httpx.AsyncClient(timeout=GITLAB_TIMEOUT, verify=GITLAB_SSL_VERIFY) as client:
        resp = await client.post(url, headers=_headers(), json=payload)

    if resp.status_code == 401:
        raise PermissionError("Token GitLab inválido ou sem permissão.")
    if resp.status_code == 403:
        raise PermissionError("Acesso negado pela API do GitLab.")
    if resp.status_code == 404:
        raise FileNotFoundError("Recurso não encontrado no GitLab.")
    if resp.status_code >= 400:
        raise RuntimeError(f"Erro da API GitLab: HTTP {resp.status_code} — {resp.text[:200]}")

    return resp.json()


async def _get(path: str, params: Optional[Dict] = None) -> Any:
    """Executa GET na API do GitLab com rate limiting e cache."""
    if not GITLAB_URL:
        raise EnvironmentError("GITLAB_URL não configurado.")

    cache_key = f"{path}?{json.dumps(params or {}, sort_keys=True)}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    await _rate_limiter.acquire()

    url = f"{GITLAB_URL}/api/v4{path}"
    async with httpx.AsyncClient(timeout=GITLAB_TIMEOUT, verify=GITLAB_SSL_VERIFY) as client:
        resp = await client.get(url, headers=_headers(), params=params)

    if resp.status_code == 401:
        raise PermissionError("Token GitLab inválido ou sem permissão.")
    if resp.status_code == 403:
        raise PermissionError("Acesso negado pela API do GitLab.")
    if resp.status_code == 404:
        raise FileNotFoundError("Recurso não encontrado no GitLab.")
    if resp.status_code >= 400:
        raise RuntimeError(f"Erro da API GitLab: HTTP {resp.status_code}")

    data = resp.json()
    _cache_set(cache_key, data)
    return data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ok(tool: str, resource: str, data: Any) -> str:
    _audit(tool, resource, True)
    return json.dumps(
        {"status": "success", "tool": tool, "resource": resource, "data": data, "timestamp": _now()},
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def _err(tool: str, resource: str, message: str, detail: str = "") -> str:
    _audit(tool, resource, False, detail or message)
    return json.dumps(
        {"status": "error", "tool": tool, "resource": resource, "message": message, "timestamp": _now()},
        ensure_ascii=False,
        indent=2,
    )


def _encode(path: str) -> str:
    return quote(path, safe="")


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP("gitlab_mcp")

# ---------------------------------------------------------------------------
# Modelos Pydantic
# ---------------------------------------------------------------------------

class ListProjectsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    group_path: Optional[str] = Field(
        default=None,
        description=(
            "Caminho do subgrupo a listar (deve estar dentro do grupo raiz). "
            "Se omitido, usa o grupo raiz configurado em GITLAB_GROUP_PATH."
        ),
        max_length=255,
    )
    page: int = Field(default=1, ge=1, le=100, description="Página da listagem.")
    per_page: int = Field(default=20, ge=1, le=100, description="Itens por página.")

    @field_validator("group_path")
    @classmethod
    def validate_path(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            _sanitize(v, "group_path")
        return v


class GetProjectInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    project_path: str = Field(
        ...,
        description="Caminho completo do projeto (ex: grupo/subgrupo/projeto).",
        min_length=3,
        max_length=255,
    )

    @field_validator("project_path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        _sanitize(v, "project_path")
        return v


class ListMergeRequestsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    project_path: str = Field(
        ...,
        description="Caminho completo do projeto.",
        min_length=3,
        max_length=255,
    )
    state: str = Field(
        default="opened",
        description="Estado dos MRs: opened, closed, merged, all.",
    )
    page: int = Field(default=1, ge=1, le=100)
    per_page: int = Field(default=20, ge=1, le=100)

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        allowed = {"opened", "closed", "merged", "all"}
        if v not in allowed:
            raise ValueError(f"State inválido. Use um de: {allowed}")
        return v

    @field_validator("project_path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        _sanitize(v, "project_path")
        return v


class GetFileContentInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    project_path: str = Field(
        ...,
        description="Caminho completo do projeto.",
        min_length=3,
        max_length=255,
    )
    file_path: str = Field(
        ...,
        description="Caminho do arquivo dentro do repositório (ex: src/main.py).",
        min_length=1,
        max_length=500,
    )
    branch: str = Field(
        default="main",
        description="Branch ou tag (padrão: main).",
        min_length=1,
        max_length=255,
    )

    @field_validator("project_path")
    @classmethod
    def validate_project(cls, v: str) -> str:
        _sanitize(v, "project_path")
        return v

    @field_validator("file_path")
    @classmethod
    def validate_file(cls, v: str) -> str:
        _validate_file_path(v)
        return v

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, v: str) -> str:
        _sanitize(v, "branch")
        return v


class ListIssuesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    group_path: Optional[str] = Field(
        default=None,
        description=(
            "Caminho do subgrupo (deve estar dentro do grupo raiz). "
            "Se omitido, usa o grupo raiz configurado em GITLAB_GROUP_PATH."
        ),
        max_length=255,
    )
    assignee_username: Optional[str] = Field(
        default=None,
        description="Filtra issues pelo username do responsável (ex: user).",
        max_length=255,
    )
    state: str = Field(
        default="opened",
        description="Estado das issues: opened, closed, all.",
    )
    page: int = Field(default=1, ge=1, le=100)
    per_page: int = Field(default=20, ge=1, le=100)

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        allowed = {"opened", "closed", "all"}
        if v not in allowed:
            raise ValueError(f"State inválido. Use um de: {allowed}")
        return v

    @field_validator("group_path", "assignee_username")
    @classmethod
    def validate_strings(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            _sanitize(v, "parâmetro")
        return v


class SearchCodeInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(
        ...,
        description="Termo de busca no código.",
        min_length=2,
        max_length=200,
    )
    group_path: Optional[str] = Field(
        default=None,
        description=(
            "Subgrupo onde buscar (deve estar dentro do grupo raiz). "
            "Se omitido, busca no grupo raiz."
        ),
        max_length=255,
    )
    page: int = Field(default=1, ge=1, le=20)
    per_page: int = Field(default=20, ge=1, le=100)

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        _sanitize(v, "query")
        return v

    @field_validator("group_path")
    @classmethod
    def validate_path(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            _sanitize(v, "group_path")
        return v


# ---------------------------------------------------------------------------
# Ferramentas MCP
# ---------------------------------------------------------------------------

@mcp.tool(
    name="gitlab_list_projects",
    annotations={
        "title": "Listar projetos GitLab",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def gitlab_list_projects(params: ListProjectsInput) -> str:
    """Lista projetos dentro do grupo GitLab permitido (escopo restrito).

    O acesso é limitado ao grupo configurado em GITLAB_GROUP_PATH e seus subgrupos.
    Qualquer tentativa de listar projetos fora desse escopo é bloqueada.

    Args:
        params (ListProjectsInput):
            - group_path (Optional[str]): subgrupo a listar; usa raiz se omitido
            - page (int): página (padrão: 1)
            - per_page (int): itens por página (padrão: 20, max: 100)

    Returns:
        str: JSON com lista de projetos: id, name, path_with_namespace, description,
             visibility, default_branch, last_activity_at, web_url.

    Exemplos:
        - "Liste os projetos do time de backend" → group_path="empresa/backend"
        - "Quais repositórios existem no grupo?" → sem group_path
    """
    tool = "gitlab_list_projects"
    group = (params.group_path or GITLAB_GROUP_PATH).strip("/")
    try:
        _validate_group_scope(group)
        data = await _get(
            f"/groups/{_encode(group)}/projects",
            params={
                "include_subgroups": "true",
                "with_shared": "false",
                "order_by": "last_activity_at",
                "sort": "desc",
                "page": params.page,
                "per_page": params.per_page,
            },
        )
        projects = [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "path": p.get("path_with_namespace"),
                "description": p.get("description"),
                "visibility": p.get("visibility"),
                "default_branch": p.get("default_branch"),
                "last_activity_at": p.get("last_activity_at"),
            }
            for p in data
        ]
        return _ok(tool, group, {"total": len(projects), "page": params.page, "projects": projects})
    except PermissionError as exc:
        return _err(tool, group, str(exc))
    except FileNotFoundError:
        return _err(tool, group, f"Grupo '{group}' não encontrado.")
    except Exception as exc:
        return _err(tool, group, "Erro ao listar projetos.", str(exc))


@mcp.tool(
    name="gitlab_get_project",
    annotations={
        "title": "Obter detalhes de projeto GitLab",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def gitlab_get_project(params: GetProjectInput) -> str:
    """Retorna metadados detalhados de um projeto GitLab.

    O projeto deve pertencer ao grupo raiz configurado (GITLAB_GROUP_PATH).

    Args:
        params (GetProjectInput):
            - project_path (str): caminho completo do projeto (ex: empresa/time/repo)

    Returns:
        str: JSON com id, name, description, visibility, default_branch, clone_url (HTTPS),
             open_issues_count, star_count, forks_count, last_activity_at.

    Exemplos:
        - "Detalhes do projeto api-gateway" → project_path="empresa/backend/api-gateway"
    """
    tool = "gitlab_get_project"
    path = params.project_path.strip("/")
    try:
        _validate_project_scope(path)
        data = await _get(f"/projects/{_encode(path)}")
        project = {
            "id": data.get("id"),
            "name": data.get("name"),
            "path": data.get("path_with_namespace"),
            "description": data.get("description"),
            "visibility": data.get("visibility"),
            "default_branch": data.get("default_branch"),
            "http_url_to_repo": data.get("http_url_to_repo"),
            "open_issues_count": data.get("open_issues_count"),
            "star_count": data.get("star_count"),
            "forks_count": data.get("forks_count"),
            "last_activity_at": data.get("last_activity_at"),
            "created_at": data.get("created_at"),
        }
        return _ok(tool, path, project)
    except PermissionError as exc:
        return _err(tool, path, str(exc))
    except FileNotFoundError:
        return _err(tool, path, f"Projeto '{path}' não encontrado.")
    except Exception as exc:
        return _err(tool, path, "Erro ao obter projeto.", str(exc))


@mcp.tool(
    name="gitlab_list_merge_requests",
    annotations={
        "title": "Listar Merge Requests GitLab",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def gitlab_list_merge_requests(params: ListMergeRequestsInput) -> str:
    """Lista Merge Requests de um projeto GitLab (somente leitura).

    O projeto deve pertencer ao grupo raiz permitido.

    Args:
        params (ListMergeRequestsInput):
            - project_path (str): caminho completo do projeto
            - state (str): opened | closed | merged | all (padrão: opened)
            - page (int): página (padrão: 1)
            - per_page (int): itens por página (padrão: 20)

    Returns:
        str: JSON com lista de MRs: iid, title, state, author, source_branch,
             target_branch, created_at, updated_at.

    Exemplos:
        - "Quais MRs estão abertos no repo X?" → state="opened"
        - "Liste os MRs mergeados esta semana" → state="merged"
    """
    tool = "gitlab_list_merge_requests"
    path = params.project_path.strip("/")
    try:
        _validate_project_scope(path)
        data = await _get(
            f"/projects/{_encode(path)}/merge_requests",
            params={
                "state": params.state,
                "order_by": "updated_at",
                "sort": "desc",
                "page": params.page,
                "per_page": params.per_page,
            },
        )
        mrs = [
            {
                "iid": mr.get("iid"),
                "title": mr.get("title"),
                "state": mr.get("state"),
                "author": mr.get("author", {}).get("username"),
                "source_branch": mr.get("source_branch"),
                "target_branch": mr.get("target_branch"),
                "created_at": mr.get("created_at"),
                "updated_at": mr.get("updated_at"),
                "draft": mr.get("draft", False),
            }
            for mr in data
        ]
        return _ok(tool, path, {"total": len(mrs), "state": params.state, "merge_requests": mrs})
    except PermissionError as exc:
        return _err(tool, path, str(exc))
    except FileNotFoundError:
        return _err(tool, path, f"Projeto '{path}' não encontrado.")
    except Exception as exc:
        return _err(tool, path, "Erro ao listar MRs.", str(exc))


@mcp.tool(
    name="gitlab_get_file_content",
    annotations={
        "title": "Obter conteúdo de arquivo GitLab",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def gitlab_get_file_content(params: GetFileContentInput) -> str:
    """Retorna o conteúdo de um arquivo de um repositório GitLab.

    Validações aplicadas:
    - O projeto deve pertencer ao grupo raiz permitido.
    - O caminho do arquivo é sanitizado contra path traversal.
    - O conteúdo é decodificado de base64 (conforme API do GitLab).

    Args:
        params (GetFileContentInput):
            - project_path (str): caminho completo do projeto
            - file_path (str): caminho do arquivo no repo (ex: src/app.py)
            - branch (str): branch ou tag (padrão: main)

    Returns:
        str: JSON com file_name, file_path, branch, size, encoding, content (texto).

    Exemplos:
        - "Mostre o conteúdo do Dockerfile do projeto X" → file_path="Dockerfile"
        - "Leia o arquivo config/settings.py na branch develop" → branch="develop"
    """
    tool = "gitlab_get_file_content"
    project = params.project_path.strip("/")
    resource = f"{project}/{params.file_path}@{params.branch}"
    try:
        _validate_project_scope(project)
        data = await _get(
            f"/projects/{_encode(project)}/repository/files/{_encode(params.file_path)}",
            params={"ref": params.branch},
        )
        import base64
        raw_content = data.get("content", "")
        encoding = data.get("encoding", "base64")
        if encoding == "base64":
            try:
                content = base64.b64decode(raw_content).decode("utf-8", errors="replace")
            except Exception:
                content = raw_content
        else:
            content = raw_content

        result = {
            "file_name": data.get("file_name"),
            "file_path": data.get("file_path"),
            "branch": data.get("ref"),
            "size": data.get("size"),
            "last_commit_id": data.get("last_commit_id"),
            "content": content,
        }
        return _ok(tool, resource, result)
    except PermissionError as exc:
        return _err(tool, resource, str(exc))
    except FileNotFoundError:
        return _err(tool, resource, f"Arquivo '{params.file_path}' não encontrado na branch '{params.branch}'.")
    except Exception as exc:
        return _err(tool, resource, "Erro ao obter arquivo.", str(exc))


@mcp.tool(
    name="gitlab_search_code",
    annotations={
        "title": "Buscar código no GitLab",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def gitlab_search_code(params: SearchCodeInput) -> str:
    """Busca código-fonte dentro do grupo GitLab permitido.

    A busca é sempre restrita ao grupo raiz (GITLAB_GROUP_PATH) ou a um subgrupo
    explicitamente informado. Nunca acessa escopo externo ao grupo raiz.

    Args:
        params (SearchCodeInput):
            - query (str): termo de busca (mínimo 2 caracteres)
            - group_path (Optional[str]): subgrupo alvo; usa raiz se omitido
            - page (int): página (padrão: 1)
            - per_page (int): resultados por página (padrão: 20)

    Returns:
        str: JSON com lista de resultados: project_id, filename, path,
             ref (branch), startline, data (trecho encontrado).

    Exemplos:
        - "Onde usamos a função send_email?" → query="send_email"
        - "Busca por TODO no grupo backend" → query="TODO", group_path="empresa/backend"
    """
    tool = "gitlab_search_code"
    group = (params.group_path or GITLAB_GROUP_PATH).strip("/")
    resource = f"{group}?q={params.query}"
    try:
        _validate_group_scope(group)
        data = await _get(
            f"/groups/{_encode(group)}/search",
            params={
                "scope": "blobs",
                "search": params.query,
                "page": params.page,
                "per_page": params.per_page,
            },
        )
        results = [
            {
                "project_id": item.get("project_id"),
                "filename": item.get("filename"),
                "path": item.get("path"),
                "ref": item.get("ref"),
                "startline": item.get("startline"),
                "data": item.get("data"),
            }
            for item in data
        ]
        return _ok(tool, resource, {"total": len(results), "query": params.query, "results": results})
    except PermissionError as exc:
        return _err(tool, resource, str(exc))
    except FileNotFoundError:
        return _err(tool, resource, f"Grupo '{group}' não encontrado.")
    except Exception as exc:
        return _err(tool, resource, "Erro na busca de código.", str(exc))


@mcp.tool(
    name="gitlab_list_issues",
    annotations={
        "title": "Listar issues GitLab",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def gitlab_list_issues(params: ListIssuesInput) -> str:
    """Lista issues dentro do grupo GitLab, com filtro opcional por assignee e estado.

    O acesso é restrito ao grupo raiz (GITLAB_GROUP_PATH) e seus subgrupos.

    Args:
        params (ListIssuesInput):
            - group_path (Optional[str]): subgrupo alvo; usa raiz se omitido
            - assignee_username (Optional[str]): username do responsável (ex: user)
            - state (str): opened | closed | all (padrão: opened)
            - page (int): página (padrão: 1)
            - per_page (int): itens por página (padrão: 20, max: 100)

    Returns:
        str: JSON com lista de issues: iid, title, state, author, assignees,
             labels, created_at, updated_at, web_url.

    Exemplos:
        - "Issues abertas em nome de user" → assignee_username="user", state="opened"
        - "Todas as issues do subgrupo backend" → group_path="empresa/backend", state="all"
    """
    tool = "gitlab_list_issues"
    group = (params.group_path or GITLAB_GROUP_PATH).strip("/")
    resource = f"{group}?assignee={params.assignee_username or '*'}&state={params.state}"
    try:
        _validate_group_scope(group)
        query: Dict[str, Any] = {
            "state": params.state,
            "order_by": "updated_at",
            "sort": "desc",
            "page": params.page,
            "per_page": params.per_page,
        }
        if params.assignee_username:
            query["assignee_username"] = params.assignee_username
        data = await _get(f"/groups/{_encode(group)}/issues", params=query)
        issues = [
            {
                "iid": issue.get("iid"),
                "project_id": issue.get("project_id"),
                "title": issue.get("title"),
                "state": issue.get("state"),
                "author": issue.get("author", {}).get("username"),
                "assignees": [a.get("username") for a in issue.get("assignees", [])],
                "labels": issue.get("labels", []),
                "created_at": issue.get("created_at"),
                "updated_at": issue.get("updated_at"),
                "web_url": issue.get("web_url"),
            }
            for issue in data
        ]
        return _ok(tool, resource, {
            "total": len(issues),
            "state": params.state,
            "assignee": params.assignee_username,
            "issues": issues,
        })
    except PermissionError as exc:
        return _err(tool, resource, str(exc))
    except FileNotFoundError:
        return _err(tool, resource, f"Grupo '{group}' não encontrado.")
    except Exception as exc:
        return json.dumps({"status": "error", "tool": tool, "resource": resource, "message": "Erro ao listar issues.", "detail": str(exc), "timestamp": _now()}, ensure_ascii=False, indent=2)


class GetIssueNotesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    project_path: str = Field(
        ...,
        description="Caminho completo do projeto (ex: empresa/time/repo).",
        min_length=3,
        max_length=255,
    )
    issue_iid: int = Field(
        ...,
        description="IID da issue dentro do projeto (número visível na UI do GitLab).",
        ge=1,
    )
    author_username: Optional[str] = Field(
        default=None,
        description="Filtra comentários pelo username do autor (ex: user).",
        max_length=255,
    )
    after: Optional[str] = Field(
        default=None,
        description="Retorna apenas notas criadas após esta data (formato: YYYY-MM-DD).",
        max_length=10,
    )
    before: Optional[str] = Field(
        default=None,
        description="Retorna apenas notas criadas antes desta data (formato: YYYY-MM-DD).",
        max_length=10,
    )
    page: int = Field(default=1, ge=1, le=100)
    per_page: int = Field(default=50, ge=1, le=100)

    @field_validator("project_path")
    @classmethod
    def validate_project(cls, v: str) -> str:
        _sanitize(v, "project_path")
        return v

    @field_validator("author_username")
    @classmethod
    def validate_author(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            _sanitize(v, "author_username")
        return v

    @field_validator("after", "before")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
                raise ValueError("Data deve estar no formato YYYY-MM-DD.")
        return v


class GetUserActivityInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    username: str = Field(
        ...,
        description="Username GitLab do usuário (ex: user).",
        min_length=1,
        max_length=255,
    )
    group_path: Optional[str] = Field(
        default=None,
        description=(
            "Subgrupo onde buscar eventos (deve estar dentro do grupo raiz). "
            "Se omitido, usa o grupo raiz configurado em GITLAB_GROUP_PATH."
        ),
        max_length=255,
    )
    after: Optional[str] = Field(
        default=None,
        description="Retorna eventos criados após esta data (formato: YYYY-MM-DD).",
        max_length=10,
    )
    before: Optional[str] = Field(
        default=None,
        description="Retorna eventos criados antes desta data (formato: YYYY-MM-DD).",
        max_length=10,
    )
    page: int = Field(default=1, ge=1, le=100)
    per_page: int = Field(default=50, ge=1, le=100)

    @field_validator("username", "group_path")
    @classmethod
    def validate_strings(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            _sanitize(v, "parâmetro")
        return v

    @field_validator("after", "before")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
                raise ValueError("Data deve estar no formato YYYY-MM-DD.")
        return v


# ---------------------------------------------------------------------------
# Ferramentas MCP — notas e atividade
# ---------------------------------------------------------------------------

@mcp.tool(
    name="gitlab_get_issue_notes",
    annotations={
        "title": "Listar comentários de issue GitLab",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def gitlab_get_issue_notes(params: GetIssueNotesInput) -> str:
    """Lista os comentários (notes) de uma issue GitLab.

    Retorna apenas notas de usuário (exclui notas de sistema automáticas).
    Permite filtrar por autor e intervalo de datas.

    Args:
        params (GetIssueNotesInput):
            - project_path (str): caminho completo do projeto
            - issue_iid (int): IID da issue (número visível na UI)
            - author_username (Optional[str]): filtra pelo username do autor
            - after (Optional[str]): data mínima de criação (YYYY-MM-DD)
            - before (Optional[str]): data máxima de criação (YYYY-MM-DD)
            - page (int): página (padrão: 1)
            - per_page (int): itens por página (padrão: 50)

    Returns:
        str: JSON com lista de notas: id, author, body, created_at, updated_at.

    Exemplos:
        - "Comentários da issue #532 do projeto bigdata-info"
        - "O que user comentou na issue #528 na sexta?"
          → author_username="user", after="2026-04-17", before="2026-04-19"
    """
    tool = "gitlab_get_issue_notes"
    project = params.project_path.strip("/")
    resource = f"{project}#{params.issue_iid}/notes"
    try:
        _validate_project_scope(project)
        data = await _get(
            f"/projects/{_encode(project)}/issues/{params.issue_iid}/notes",
            params={
                "sort": "asc",
                "order_by": "created_at",
                "page": params.page,
                "per_page": params.per_page,
            },
        )
        notes = []
        for note in data:
            if note.get("system", False):
                continue
            author = note.get("author", {}).get("username", "")
            if params.author_username and author != params.author_username:
                continue
            created = note.get("created_at", "")
            if params.after and created[:10] < params.after:
                continue
            if params.before and created[:10] > params.before:
                continue
            notes.append({
                "id": note.get("id"),
                "author": author,
                "body": note.get("body"),
                "created_at": created,
                "updated_at": note.get("updated_at"),
            })
        return _ok(tool, resource, {
            "total": len(notes),
            "issue_iid": params.issue_iid,
            "project": project,
            "notes": notes,
        })
    except PermissionError as exc:
        return _err(tool, resource, str(exc))
    except FileNotFoundError:
        return _err(tool, resource, f"Issue #{params.issue_iid} ou projeto '{project}' não encontrado.")
    except Exception as exc:
        return _err(tool, resource, "Erro ao listar notas.", str(exc))


@mcp.tool(
    name="gitlab_get_user_activity",
    annotations={
        "title": "Listar atividade de usuário GitLab",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def gitlab_get_user_activity(params: GetUserActivityInput) -> str:
    """Lista eventos e atividades de um usuário no grupo GitLab.

    Resolve automaticamente o username para o ID numérico do GitLab e
    busca os eventos do usuário no grupo raiz. Útil para responder
    "o que eu fiz na sexta-feira?" ou "quais atividades registrei hoje?".

    Args:
        params (GetUserActivityInput):
            - username (str): username GitLab (ex: user)
            - group_path (Optional[str]): subgrupo alvo; usa raiz se omitido
            - after (Optional[str]): data mínima (YYYY-MM-DD)
            - before (Optional[str]): data máxima (YYYY-MM-DD)
            - page (int): página (padrão: 1)
            - per_page (int): itens por página (padrão: 50)

    Returns:
        str: JSON com lista de eventos: action_name, target_type, target_title,
             target_iid, project_id, project_path, created_at.
             Para eventos target_type="Note", inclui também noteable_type e
             noteable_iid (IID da issue/MR comentada — use este para gitlab_get_issue_notes).

    Exemplos:
        - "O que user fez na sexta-feira (17/04)?"
          → username="user", after="2026-04-17", before="2026-04-19"
        - "Atividades de user esta semana"
          → username="user", after="2026-04-14"
    """
    tool = "gitlab_get_user_activity"
    group = (params.group_path or GITLAB_GROUP_PATH).strip("/")
    resource = f"{group}?author={params.username}"
    try:
        _validate_group_scope(group)

        # Resolve username → user_id
        users = await _get("/users", params={"username": params.username})
        if not users:
            return _err(tool, resource, f"Usuário '{params.username}' não encontrado.")
        user_id = users[0].get("id")

        query: Dict[str, Any] = {
            "author_id": user_id,
            "sort": "desc",
            "page": params.page,
            "per_page": params.per_page,
        }
        if params.after:
            query["after"] = params.after
        if params.before:
            query["before"] = params.before

        data = await _get(f"/users/{user_id}/events", params=query)

        # Resolve project_id → project_path para todos os eventos
        project_ids = {ev.get("project_id") for ev in data if ev.get("project_id")}
        project_paths: Dict[int, str] = {}
        for pid in project_ids:
            try:
                proj = await _get(f"/projects/{pid}")
                project_paths[pid] = proj.get("path_with_namespace", "")
            except Exception:
                project_paths[pid] = ""

        events = []
        for ev in data:
            pid = ev.get("project_id")
            event: Dict[str, Any] = {
                "action_name": ev.get("action_name"),
                "target_type": ev.get("target_type"),
                "target_title": ev.get("target_title"),
                "target_iid": ev.get("target_iid"),
                "project_id": pid,
                "project_path": project_paths.get(pid, ""),
                "created_at": ev.get("created_at"),
            }
            # Para eventos de nota, extrai o IID e tipo do noteable (issue/MR)
            if ev.get("target_type") == "Note":
                note = ev.get("note", {})
                event["noteable_type"] = note.get("noteable_type")
                event["noteable_iid"] = note.get("noteable_iid")
            events.append(event)
        return _ok(tool, resource, {
            "total": len(events),
            "username": params.username,
            "after": params.after,
            "before": params.before,
            "events": events,
        })
    except PermissionError as exc:
        return _err(tool, resource, str(exc))
    except FileNotFoundError:
        return _err(tool, resource, f"Grupo '{group}' não encontrado.")
    except Exception as exc:
        return _err(tool, resource, "Erro ao listar atividade do usuário.", str(exc))


# ---------------------------------------------------------------------------
# Modelos Pydantic — escrita
# ---------------------------------------------------------------------------

class CreateIssueInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    project_path: str = Field(
        ...,
        description="Caminho completo do projeto (ex: empresa/time/repo).",
        min_length=3,
        max_length=255,
    )
    title: str = Field(
        ...,
        description="Título da issue.",
        min_length=3,
        max_length=_MAX_TITLE_LEN,
    )
    description: str = Field(
        default="",
        description="Descrição da issue em Markdown.",
        max_length=_MAX_DESCRIPTION_LEN,
    )
    labels: List[str] = Field(
        default_factory=list,
        description="Labels a aplicar na issue (além da label automática do agente).",
        max_length=20,
    )
    dry_run: bool = Field(
        default=False,
        description="Se true, simula a criação sem executar (sobrescreve GITLAB_DRY_RUN).",
    )

    @field_validator("project_path")
    @classmethod
    def validate_project(cls, v: str) -> str:
        _sanitize(v, "project_path")
        return v

    @field_validator("title", "description")
    @classmethod
    def sanitize_text(cls, v: str) -> str:
        return v.strip()

    @field_validator("labels", mode="before")
    @classmethod
    def validate_labels(cls, v: Any) -> List[str]:
        if not isinstance(v, list):
            raise ValueError("labels deve ser uma lista de strings.")
        for label in v:
            _sanitize(str(label), "label")
        return v


class AddIssueCommentInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    project_path: str = Field(
        ...,
        description="Caminho completo do projeto.",
        min_length=3,
        max_length=255,
    )
    issue_iid: int = Field(
        ...,
        description="IID da issue dentro do projeto (número visível na UI do GitLab).",
        ge=1,
    )
    comment: str = Field(
        ...,
        description="Texto do comentário em Markdown.",
        min_length=1,
        max_length=_MAX_COMMENT_LEN,
    )
    dry_run: bool = Field(
        default=False,
        description="Se true, simula o comentário sem executar.",
    )

    @field_validator("project_path")
    @classmethod
    def validate_project(cls, v: str) -> str:
        _sanitize(v, "project_path")
        return v

    @field_validator("comment")
    @classmethod
    def sanitize_comment(cls, v: str) -> str:
        return v.strip()


# ---------------------------------------------------------------------------
# Ferramentas MCP — escrita
# ---------------------------------------------------------------------------

@mcp.tool(
    name="gitlab_create_issue",
    annotations={
        "title": "Criar issue no GitLab",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def gitlab_create_issue(params: CreateIssueInput) -> str:
    """Cria uma issue em um projeto GitLab (requer GITLAB_WRITE_ENABLED=true).

    Proteções aplicadas:
    - Operação bloqueada se GITLAB_WRITE_ENABLED=false.
    - O projeto deve pertencer ao GITLAB_GROUP_PATH.
    - Deduplicação por hash (title + description): não cria duplicata na mesma sessão.
    - Label automática GITLAB_AGENT_LABEL adicionada a todas as issues criadas.
    - Suporte a dry_run para simular sem executar.
    - Payload auditado no log (sem dados sensíveis).

    Args:
        params (CreateIssueInput):
            - project_path (str): caminho completo do projeto
            - title (str): título da issue (3–255 chars)
            - description (str): corpo em Markdown (max 10.000 chars)
            - labels (List[str]): labels adicionais
            - dry_run (bool): simula sem criar (padrão: false)

    Returns:
        str: JSON com id, iid, title, web_url e status da operação.

    Exemplos:
        - "Cria issue 'Bug no login' no projeto auth-service"
        - "Cria issue de melhoria com dry_run=true para ver o payload"
    """
    tool = "gitlab_create_issue"
    project = params.project_path.strip("/")
    try:
        _write_guard(tool)
        _validate_project_scope(project)

        effective_dry_run = GITLAB_DRY_RUN or params.dry_run

        # Deduplicação por hash (title + description)
        content_hash = hashlib.sha256(
            f"{project}|{params.title}|{params.description}".encode()
        ).hexdigest()
        if content_hash in _issue_hashes and not effective_dry_run:
            existing_iid = _issue_hashes[content_hash]
            return _ok(tool, project, {
                "deduplicated": True,
                "message": f"Issue idêntica já criada nesta sessão (iid={existing_iid}). Nenhuma ação executada.",
                "issue_iid": existing_iid,
            })

        all_labels = list({GITLAB_AGENT_LABEL, *params.labels})
        payload = {
            "title": params.title,
            "description": params.description,
            "labels": ",".join(all_labels),
        }

        _audit_write(tool, project, {"title": params.title, "labels": all_labels}, effective_dry_run)

        data = await _post(f"/projects/{_encode(project)}/issues", payload)

        if effective_dry_run:
            return _ok(tool, project, {"dry_run": True, "simulated_payload": payload})

        iid = data.get("iid")
        _issue_hashes[content_hash] = iid
        return _ok(tool, project, {
            "id": data.get("id"),
            "iid": iid,
            "title": data.get("title"),
            "state": data.get("state"),
            "web_url": data.get("web_url"),
            "labels": data.get("labels"),
            "created_at": data.get("created_at"),
        })
    except PermissionError as exc:
        return _err(tool, project, str(exc))
    except FileNotFoundError:
        return _err(tool, project, f"Projeto '{project}' não encontrado.")
    except Exception as exc:
        return _err(tool, project, "Erro ao criar issue.", str(exc))


@mcp.tool(
    name="gitlab_add_issue_comment",
    annotations={
        "title": "Adicionar comentário em issue GitLab",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def gitlab_add_issue_comment(params: AddIssueCommentInput) -> str:
    """Adiciona um comentário (note) em uma issue GitLab (requer GITLAB_WRITE_ENABLED=true).

    Proteções aplicadas:
    - Operação bloqueada se GITLAB_WRITE_ENABLED=false.
    - O projeto deve pertencer ao GITLAB_GROUP_PATH.
    - Rate limiting de escrita aplicado (GITLAB_WRITE_RATE_LIMIT req/min).
    - Prefixo automático `[Agent Activity]` adicionado ao comentário.
    - Suporte a dry_run para simular sem executar.
    - Payload auditado (sem dados sensíveis).

    Args:
        params (AddIssueCommentInput):
            - project_path (str): caminho completo do projeto
            - issue_iid (int): IID da issue (número visível na UI)
            - comment (str): texto em Markdown (max 5.000 chars)
            - dry_run (bool): simula sem comentar (padrão: false)

    Returns:
        str: JSON com id, author, created_at e body do comentário criado.

    Exemplos:
        - "Comenta na issue #42 do projeto api-gateway: 'Deploy concluído'"
        - "Adiciona nota de triagem na issue 7 do projeto backend"
    """
    tool = "gitlab_add_issue_comment"
    project = params.project_path.strip("/")
    resource = f"{project}#!{params.issue_iid}"
    try:
        _write_guard(tool)
        _validate_project_scope(project)

        effective_dry_run = GITLAB_DRY_RUN or params.dry_run
        body = f"[Agent Activity] {params.comment}"
        payload = {"body": body}

        _audit_write(tool, resource, {"issue_iid": params.issue_iid, "body_length": len(body)}, effective_dry_run)

        data = await _post(
            f"/projects/{_encode(project)}/issues/{params.issue_iid}/notes",
            payload,
        )

        if effective_dry_run:
            return _ok(tool, resource, {"dry_run": True, "simulated_body": body})

        return _ok(tool, resource, {
            "id": data.get("id"),
            "author": data.get("author", {}).get("username"),
            "body": data.get("body"),
            "created_at": data.get("created_at"),
        })
    except PermissionError as exc:
        return _err(tool, resource, str(exc))
    except FileNotFoundError:
        return _err(tool, resource, f"Issue !{params.issue_iid} ou projeto '{project}' não encontrado.")
    except Exception as exc:
        return _err(tool, resource, "Erro ao adicionar comentário.", str(exc))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    missing = [v for v in ("GITLAB_URL", "GITLAB_TOKEN", "GITLAB_GROUP_PATH") if not os.getenv(v)]
    if missing:
        logger.error("Variáveis de ambiente obrigatórias não definidas: %s", missing)
        sys.exit(1)
    mcp.run()
