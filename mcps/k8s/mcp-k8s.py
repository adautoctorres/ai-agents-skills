#!/usr/bin/env python3
"""
MCP Server para Kubernetes (kubectl).

Fornece ferramentas de leitura controlada para interagir com clusters Kubernetes
via kubectl, com validação de segurança, auditoria e saída estruturada em JSON.
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

KUBECTL_TIMEOUT = int(os.getenv("KUBECTL_TIMEOUT", "30"))
KUBECONFIG = os.getenv("KUBECONFIG", os.path.expanduser("~/.kube/config"))

# Apenas comandos de leitura são permitidos
ALLOWED_SUBCOMMANDS = {"get", "describe", "logs", "config", "version", "top"}

BLOCKED_SUBCOMMANDS = {
    "delete", "apply", "patch", "exec", "port-forward",
    "create", "replace", "edit", "annotate", "label",
    "scale", "rollout", "set", "run", "expose",
    "drain", "taint", "cordon", "uncordon",
    "cp", "attach", "debug",
}

# ---------------------------------------------------------------------------
# Logging / Auditoria
# ---------------------------------------------------------------------------

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [AUDIT] %(message)s",
)
logger = logging.getLogger("mcp-k8s")


def _audit(command: str, context: str, success: bool, detail: str = "") -> None:
    status = "OK" if success else "ERROR"
    logger.info("status=%s context=%r command=%r detail=%r", status, context, command, detail)


# ---------------------------------------------------------------------------
# Camada de segurança
# ---------------------------------------------------------------------------

def _validate_command(args: List[str]) -> None:
    """Garante que apenas subcomandos de leitura sejam executados."""
    if not args:
        raise ValueError("Nenhum argumento fornecido ao kubectl.")

    subcommand = args[0].lower()

    if subcommand in BLOCKED_SUBCOMMANDS:
        raise PermissionError(
            f"Comando bloqueado por política de segurança: 'kubectl {subcommand}'. "
            "Apenas operações de leitura são permitidas."
        )

    if subcommand not in ALLOWED_SUBCOMMANDS:
        raise PermissionError(
            f"Subcomando não reconhecido: '{subcommand}'. "
            f"Permitidos: {sorted(ALLOWED_SUBCOMMANDS)}"
        )

    # Impede injeção de shell através dos args
    for arg in args:
        for dangerous in (";", "&&", "||", "`", "$(", "|", ">", "<", "\n"):
            if dangerous in arg:
                raise ValueError(f"Caractere não permitido nos argumentos: {dangerous!r}")


# ---------------------------------------------------------------------------
# Executor de comandos
# ---------------------------------------------------------------------------

def _run_kubectl(args: List[str], context: Optional[str] = None) -> Dict[str, Any]:
    """Executa kubectl de forma segura e retorna saída estruturada."""
    _validate_command(args)

    cmd = ["kubectl"]
    if context:
        cmd += ["--context", context]

    env = os.environ.copy()
    if KUBECONFIG:
        env["KUBECONFIG"] = KUBECONFIG

    cmd += args
    command_str = " ".join(cmd)
    active_context = context or _get_current_context_name()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=KUBECTL_TIMEOUT,
            env=env,
        )
    except subprocess.TimeoutExpired:
        _audit(command_str, active_context or "", False, "timeout")
        return _error_response(
            "Timeout ao executar o comando kubectl.",
            f"Timeout configurado: {KUBECTL_TIMEOUT}s",
            command_str,
            active_context,
        )
    except FileNotFoundError:
        _audit(command_str, active_context or "", False, "kubectl não encontrado")
        return _error_response(
            "kubectl não encontrado no PATH.",
            "Verifique se o kubectl está instalado e acessível.",
            command_str,
            active_context,
        )

    if result.returncode != 0:
        _audit(command_str, active_context or "", False, result.stderr.strip())
        return _error_response(
            result.stderr.strip() or "Erro desconhecido.",
            f"Código de saída: {result.returncode}",
            command_str,
            active_context,
        )

    _audit(command_str, active_context or "", True)
    return {
        "status": "success",
        "context": active_context,
        "command": command_str,
        "data": _parse_output(result.stdout, args),
        "raw": result.stdout,
        "timestamp": _now(),
    }


# ---------------------------------------------------------------------------
# Parser de saída
# ---------------------------------------------------------------------------

def _parse_output(output: str, args: List[str]) -> Any:
    """Tenta converter a saída para JSON/dict; caso contrário, retorna texto."""
    text = output.strip()
    if not text:
        return None

    # Tenta JSON direto
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Tenta YAML (kubectl config view retorna YAML)
    if args and args[0] == "config":
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError:
            pass

    return text


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _get_current_context_name() -> Optional[str]:
    try:
        result = subprocess.run(
            ["kubectl", "config", "current-context"],
            capture_output=True, text=True, timeout=10,
            env={**os.environ, "KUBECONFIG": KUBECONFIG},
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _error_response(message: str, details: str, command: str, context: Optional[str]) -> Dict[str, Any]:
    return {
        "status": "error",
        "context": context,
        "command": command,
        "message": message,
        "details": details,
        "timestamp": _now(),
    }


def _to_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP("kubernetes_mcp")


# ---------------------------------------------------------------------------
# Modelos Pydantic
# ---------------------------------------------------------------------------

class SwitchContextInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    context_name: str = Field(
        ...,
        description="Nome do contexto kubeconfig (ex: 'prod-cluster', 'minikube')",
        min_length=1,
        max_length=253,
    )

    @field_validator("context_name")
    @classmethod
    def no_shell_injection(cls, v: str) -> str:
        for ch in (";", "&", "|", "`", "$", ">", "<", "\n", " "):
            if ch in v:
                raise ValueError(f"Caractere inválido no nome do contexto: {ch!r}")
        return v


class GetPodsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    namespace: Optional[str] = Field(
        default=None,
        description="Namespace específico. Se omitido, lista todos (-A).",
        max_length=253,
    )
    context: Optional[str] = Field(
        default=None,
        description="Contexto kubeconfig a usar. Se omitido, usa o contexto ativo.",
    )


class GetServicesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    namespace: Optional[str] = Field(
        default=None,
        description="Namespace específico. Se omitido, lista todos (-A).",
    )
    context: Optional[str] = Field(default=None, description="Contexto kubeconfig.")


class DescribeResourceInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    resource_type: str = Field(
        ...,
        description="Tipo do recurso (ex: pod, deployment, service, node, pvc).",
        min_length=1,
        max_length=100,
    )
    name: str = Field(
        ...,
        description="Nome do recurso.",
        min_length=1,
        max_length=253,
    )
    namespace: Optional[str] = Field(
        default=None,
        description="Namespace do recurso (omitir para recursos de cluster como nodes).",
    )
    context: Optional[str] = Field(default=None, description="Contexto kubeconfig.")


class GetLogsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    pod: str = Field(..., description="Nome do pod.", min_length=1, max_length=253)
    namespace: str = Field(
        default="default",
        description="Namespace do pod (padrão: 'default').",
        min_length=1,
    )
    container: Optional[str] = Field(
        default=None,
        description="Nome do container (necessário quando o pod tem múltiplos containers).",
    )
    tail: int = Field(
        default=100,
        description="Número de linhas finais a retornar (padrão: 100).",
        ge=1,
        le=5000,
    )
    context: Optional[str] = Field(default=None, description="Contexto kubeconfig.")


class GetNodesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: Optional[str] = Field(default=None, description="Contexto kubeconfig.")


class GetNamespacesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: Optional[str] = Field(default=None, description="Contexto kubeconfig.")


# ---------------------------------------------------------------------------
# Ferramentas MCP
# ---------------------------------------------------------------------------

@mcp.tool(
    name="k8s_list_contexts",
    annotations={
        "title": "Listar contextos Kubernetes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def k8s_list_contexts() -> str:
    """Lista todos os contextos definidos no kubeconfig.

    Executa `kubectl config get-contexts -o json` e retorna a lista estruturada
    de contextos disponíveis, incluindo nome, cluster, usuário e se é o contexto atual.

    Returns:
        str: JSON com campos:
            - status: "success" ou "error"
            - context: contexto ativo no momento
            - command: comando executado
            - timestamp: ISO 8601
            - data: lista de contextos com name, cluster, authInfo, namespace, current (bool)

    Exemplos de uso:
        - "Quais clusters estão configurados?" → use este tool
        - "Liste todos os contextos disponíveis" → use este tool
    """
    result = await asyncio.to_thread(
        _run_kubectl, ["config", "view", "-o", "json"]
    )

    if result["status"] == "success" and isinstance(result.get("data"), dict):
        items = result["data"].get("contexts", [])
        current = _get_current_context_name()
        contexts = [
            {
                "name": item.get("name"),
                "cluster": item.get("context", {}).get("cluster"),
                "user": item.get("context", {}).get("user"),
                "namespace": item.get("context", {}).get("namespace", "default"),
                "current": item.get("name") == current,
            }
            for item in items
        ]
        result["data"] = contexts

    return _to_json(result)


@mcp.tool(
    name="k8s_get_current_context",
    annotations={
        "title": "Obter contexto Kubernetes atual",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def k8s_get_current_context() -> str:
    """Retorna o contexto Kubernetes atualmente ativo.

    Executa `kubectl config current-context`.

    Returns:
        str: JSON com:
            - status: "success" ou "error"
            - data.context: nome do contexto ativo
            - data.cluster: cluster associado
            - data.user: usuário associado
            - timestamp: ISO 8601
    """
    result = await asyncio.to_thread(
        _run_kubectl, ["config", "current-context"]
    )

    if result["status"] == "success":
        context_name = result.get("data", "").strip() if isinstance(result.get("data"), str) else ""
        # Busca detalhes do contexto via config view
        view = await asyncio.to_thread(
            _run_kubectl, ["config", "view", "--minify", "-o", "json"]
        )
        details: Dict[str, Any] = {"context": context_name}
        if view["status"] == "success" and isinstance(view.get("data"), dict):
            contexts = view["data"].get("contexts", [])
            if contexts:
                ctx = contexts[0].get("context", {})
                details["cluster"] = ctx.get("cluster")
                details["user"] = ctx.get("user")
                details["namespace"] = ctx.get("namespace", "default")
        result["data"] = details

    return _to_json(result)


@mcp.tool(
    name="k8s_switch_context",
    annotations={
        "title": "Trocar contexto Kubernetes",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def k8s_switch_context(params: SwitchContextInput) -> str:
    """Troca o contexto Kubernetes ativo no kubeconfig local.

    Valida se o contexto existe antes de executar `kubectl config use-context`.
    Operação local que altera apenas o kubeconfig — não afeta o cluster.

    Args:
        params (SwitchContextInput):
            - context_name (str): nome exato do contexto de destino

    Returns:
        str: JSON com status da operação e contexto agora ativo.

    Exemplos:
        - "Muda para o cluster de produção" → params com context_name="prod"
        - "Troca para minikube" → params com context_name="minikube"
    """
    # Valida existência do contexto antes de trocar
    list_result = await asyncio.to_thread(
        _run_kubectl, ["config", "view", "-o", "json"]
    )

    if list_result["status"] == "success" and isinstance(list_result.get("data"), dict):
        items = list_result["data"].get("contexts", [])
        available = [i.get("name") for i in items]
        if params.context_name not in available:
            return _to_json(_error_response(
                f"Contexto '{params.context_name}' não encontrado.",
                f"Contextos disponíveis: {available}",
                f"kubectl config use-context {params.context_name}",
                _get_current_context_name(),
            ))

    result = await asyncio.to_thread(
        _run_kubectl, ["config", "use-context", params.context_name]
    )
    return _to_json(result)


@mcp.tool(
    name="k8s_get_pods",
    annotations={
        "title": "Listar pods Kubernetes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def k8s_get_pods(params: GetPodsInput) -> str:
    """Lista pods no cluster Kubernetes em JSON estruturado.

    Executa `kubectl get pods -o json` com suporte a namespace específico ou todos (-A).

    Args:
        params (GetPodsInput):
            - namespace (Optional[str]): namespace alvo; omitir para todos
            - context (Optional[str]): contexto kubeconfig; omitir para usar o ativo

    Returns:
        str: JSON com lista de pods incluindo nome, namespace, status, restarts, IP, node.

    Exemplos:
        - "Liste os pods em produção" → namespace="production"
        - "Mostre todos os pods do cluster" → namespace=None
        - "Quais pods estão rodando no kube-system?" → namespace="kube-system"
    """
    args = ["get", "pods", "-o", "json"]
    if params.namespace:
        args += ["-n", params.namespace]
    else:
        args.append("-A")

    result = await asyncio.to_thread(_run_kubectl, args, params.context)

    if result["status"] == "success" and isinstance(result.get("data"), dict):
        items = result["data"].get("items", [])
        pods = [
            {
                "name": p.get("metadata", {}).get("name"),
                "namespace": p.get("metadata", {}).get("namespace"),
                "status": p.get("status", {}).get("phase"),
                "ready": _pod_ready(p),
                "restarts": _pod_restarts(p),
                "ip": p.get("status", {}).get("podIP"),
                "node": p.get("spec", {}).get("nodeName"),
                "age": p.get("metadata", {}).get("creationTimestamp"),
            }
            for p in items
        ]
        result["data"] = {"total": len(pods), "pods": pods}

    return _to_json(result)


@mcp.tool(
    name="k8s_get_services",
    annotations={
        "title": "Listar serviços Kubernetes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def k8s_get_services(params: GetServicesInput) -> str:
    """Lista serviços (Services) no cluster Kubernetes.

    Executa `kubectl get svc -o json`.

    Args:
        params (GetServicesInput):
            - namespace (Optional[str]): namespace alvo; omitir para todos
            - context (Optional[str]): contexto kubeconfig

    Returns:
        str: JSON com lista de services: nome, namespace, tipo, clusterIP, portas, externalIP.

    Exemplos:
        - "Quais serviços existem no namespace 'app'?" → namespace="app"
        - "Liste todos os LoadBalancers" → namespace=None (filtre pelo tipo no cliente)
    """
    args = ["get", "svc", "-o", "json"]
    if params.namespace:
        args += ["-n", params.namespace]
    else:
        args.append("-A")

    result = await asyncio.to_thread(_run_kubectl, args, params.context)

    if result["status"] == "success" and isinstance(result.get("data"), dict):
        items = result["data"].get("items", [])
        services = [
            {
                "name": s.get("metadata", {}).get("name"),
                "namespace": s.get("metadata", {}).get("namespace"),
                "type": s.get("spec", {}).get("type"),
                "clusterIP": s.get("spec", {}).get("clusterIP"),
                "externalIP": s.get("status", {}).get("loadBalancer", {}).get("ingress"),
                "ports": [
                    {"port": p.get("port"), "targetPort": p.get("targetPort"), "protocol": p.get("protocol")}
                    for p in s.get("spec", {}).get("ports", [])
                ],
                "age": s.get("metadata", {}).get("creationTimestamp"),
            }
            for s in items
        ]
        result["data"] = {"total": len(services), "services": services}

    return _to_json(result)


@mcp.tool(
    name="k8s_get_nodes",
    annotations={
        "title": "Listar nós Kubernetes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def k8s_get_nodes(params: GetNodesInput) -> str:
    """Lista os nós (nodes) do cluster Kubernetes com status e capacidade.

    Executa `kubectl get nodes -o json`.

    Args:
        params (GetNodesInput):
            - context (Optional[str]): contexto kubeconfig

    Returns:
        str: JSON com lista de nós: nome, status, roles, versão, CPU, memória, OS.

    Exemplos:
        - "Quantos nós tem o cluster?" → use este tool
        - "Algum nó está NotReady?" → use este tool e filtre por status
    """
    result = await asyncio.to_thread(
        _run_kubectl, ["get", "nodes", "-o", "json"], params.context
    )

    if result["status"] == "success" and isinstance(result.get("data"), dict):
        items = result["data"].get("items", [])
        nodes = [
            {
                "name": n.get("metadata", {}).get("name"),
                "status": _node_status(n),
                "roles": _node_roles(n),
                "version": n.get("status", {}).get("nodeInfo", {}).get("kubeletVersion"),
                "os": n.get("status", {}).get("nodeInfo", {}).get("osImage"),
                "cpu": n.get("status", {}).get("capacity", {}).get("cpu"),
                "memory": n.get("status", {}).get("capacity", {}).get("memory"),
                "age": n.get("metadata", {}).get("creationTimestamp"),
            }
            for n in items
        ]
        result["data"] = {"total": len(nodes), "nodes": nodes}

    return _to_json(result)


@mcp.tool(
    name="k8s_get_namespaces",
    annotations={
        "title": "Listar namespaces Kubernetes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def k8s_get_namespaces(params: GetNamespacesInput) -> str:
    """Lista todos os namespaces do cluster Kubernetes.

    Executa `kubectl get namespaces -o json`.

    Args:
        params (GetNamespacesInput):
            - context (Optional[str]): contexto kubeconfig; omitir para usar o ativo

    Returns:
        str: JSON com lista de namespaces: nome, status e data de criação.

    Exemplos:
        - "Quais namespaces existem no cluster?" → use este tool
        - "Liste os namespaces disponíveis" → use este tool
    """
    result = await asyncio.to_thread(
        _run_kubectl, ["get", "namespaces", "-o", "json"], params.context
    )

    if result["status"] == "success" and isinstance(result.get("data"), dict):
        items = result["data"].get("items", [])
        namespaces = [
            {
                "name": ns.get("metadata", {}).get("name"),
                "status": ns.get("status", {}).get("phase"),
                "age": ns.get("metadata", {}).get("creationTimestamp"),
            }
            for ns in items
        ]
        result["data"] = {"total": len(namespaces), "namespaces": namespaces}

    return _to_json(result)


@mcp.tool(
    name="k8s_describe_resource",
    annotations={
        "title": "Descrever recurso Kubernetes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def k8s_describe_resource(params: DescribeResourceInput) -> str:
    """Retorna a descrição detalhada de um recurso Kubernetes específico.

    Executa `kubectl describe <tipo> <nome>`. Útil para diagnóstico de eventos,
    condições, volumes montados, probes etc.

    Args:
        params (DescribeResourceInput):
            - resource_type (str): tipo do recurso (ex: pod, deployment, node, pvc, ingress)
            - name (str): nome exato do recurso
            - namespace (Optional[str]): namespace (omitir para recursos de cluster)
            - context (Optional[str]): contexto kubeconfig

    Returns:
        str: JSON com a saída textual do describe (campo 'data').

    Exemplos:
        - "Describe o pod nginx-xxx no namespace app" → type="pod", name="nginx-xxx", ns="app"
        - "Detalhes do node worker-1" → type="node", name="worker-1"
        - "O que está acontecendo com o deployment frontend?" → type="deployment", name="frontend"
    """
    args = ["describe", params.resource_type, params.name]
    if params.namespace:
        args += ["-n", params.namespace]

    result = await asyncio.to_thread(_run_kubectl, args, params.context)
    return _to_json(result)


@mcp.tool(
    name="k8s_get_logs",
    annotations={
        "title": "Obter logs de pod Kubernetes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def k8s_get_logs(params: GetLogsInput) -> str:
    """Retorna os logs de um pod Kubernetes (últimas N linhas).

    Executa `kubectl logs <pod> --tail=<N>`.

    Args:
        params (GetLogsInput):
            - pod (str): nome do pod
            - namespace (str): namespace do pod (padrão: "default")
            - container (Optional[str]): nome do container (necessário em pods multi-container)
            - tail (int): linhas finais a retornar (1-5000, padrão: 100)
            - context (Optional[str]): contexto kubeconfig

    Returns:
        str: JSON com os logs no campo 'data' como texto.

    Exemplos:
        - "Mostre os logs do pod api-server-xxx" → pod="api-server-xxx"
        - "Últimos 500 logs do container 'app' no pod 'web-pod'" → container="app", tail=500
    """
    args = [
        "logs", params.pod,
        "-n", params.namespace,
        f"--tail={params.tail}",
    ]
    if params.container:
        args += ["-c", params.container]

    result = await asyncio.to_thread(_run_kubectl, args, params.context)
    return _to_json(result)


# ---------------------------------------------------------------------------
# Helpers de extração de dados
# ---------------------------------------------------------------------------

def _pod_ready(pod: Dict) -> str:
    containers = pod.get("status", {}).get("containerStatuses", [])
    if not containers:
        return "0/0"
    ready = sum(1 for c in containers if c.get("ready"))
    return f"{ready}/{len(containers)}"


def _pod_restarts(pod: Dict) -> int:
    containers = pod.get("status", {}).get("containerStatuses", [])
    return sum(c.get("restartCount", 0) for c in containers)


def _node_status(node: Dict) -> str:
    conditions = node.get("status", {}).get("conditions", [])
    for cond in conditions:
        if cond.get("type") == "Ready":
            return "Ready" if cond.get("status") == "True" else "NotReady"
    return "Unknown"


def _node_roles(node: Dict) -> List[str]:
    labels = node.get("metadata", {}).get("labels", {})
    return [
        key.split("/")[-1].replace("node-role.kubernetes.io/", "")
        for key in labels
        if "node-role.kubernetes.io" in key
    ]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
