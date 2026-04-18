# MCP Kubernetes (`mcp-k8s`)

Servidor MCP em Python para interação segura e auditável com clusters Kubernetes via `kubectl`. Apenas operações de leitura são permitidas — comandos destrutivos são bloqueados por política.

## Ferramentas expostas

| Tool | Descrição |
|---|---|
| `k8s_list_contexts` | Lista todos os contextos do kubeconfig |
| `k8s_get_current_context` | Retorna o contexto ativo com cluster e usuário |
| `k8s_switch_context` | Troca o contexto ativo (valida existência antes) |
| `k8s_get_pods` | Lista pods com status, restarts, IP e node |
| `k8s_get_services` | Lista services com tipo, portas e externalIP |
| `k8s_get_nodes` | Lista nós com status, versão, CPU e memória |
| `k8s_describe_resource` | Descreve qualquer recurso em detalhe |
| `k8s_get_logs` | Retorna as últimas N linhas de log de um pod |

## Requisitos

- Python 3.11+
- `kubectl` instalado e no `$PATH`
- `~/.kube/config` configurado (ou variável `$KUBECONFIG`)

## Instalação de dependências

Dependências gerenciadas via `pyproject.toml` na raiz do projeto:

```bash
uv sync
```

## Registro no Claude Code

```bash
make mcp-k8s-add
# ou diretamente:
claude mcp add --scope local mcp-k8s python mcps/k8s/mcp-k8s.py
```

## Remoção

```bash
make mcp-k8s-remove
```

## Variáveis de ambiente

| Variável | Padrão | Descrição |
|---|---|---|
| `KUBECONFIG` | `~/.kube/config` | Caminho para o kubeconfig |
| `KUBECTL_TIMEOUT` | `30` | Timeout em segundos por comando kubectl |

## Segurança

**Subcomandos permitidos (whitelist):** `get`, `describe`, `logs`, `config`, `version`, `top`

**Bloqueados:** `delete`, `apply`, `patch`, `exec`, `port-forward`, `create`, `replace`, `edit`, `scale`, `drain`, `cordon`, `run`, `cp`, `attach`, `debug` e outros destrutivos.

Adicionalmente:
- Inputs sanitizados contra injeção de shell (`;`, `&&`, `|`, `$()` etc.)
- Credenciais do kubeconfig nunca expostas na saída
- Todas as execuções auditadas no stderr com timestamp, contexto e resultado

## Referência das ferramentas

### `k8s_list_contexts`

```
Retorno: lista de contextos — name, cluster, user, namespace, current (bool)
```

### `k8s_get_current_context`

```
Retorno: {"context", "cluster", "user", "namespace"}
```

### `k8s_switch_context`

```
Parâmetros:
  context_name — nome exato do contexto de destino
```

### `k8s_get_pods`

```
Parâmetros:
  namespace — namespace específico (omitir para todos)
  context   — contexto kubeconfig (omitir para o ativo)

Retorno: {"total": int, "pods": [{name, namespace, status, ready, restarts, ip, node, age}]}
```

### `k8s_get_services`

```
Parâmetros:
  namespace — namespace específico (omitir para todos)
  context   — contexto kubeconfig (omitir para o ativo)

Retorno: {"total": int, "services": [{name, namespace, type, clusterIP, externalIP, ports, age}]}
```

### `k8s_get_nodes`

```
Parâmetros:
  context — contexto kubeconfig (omitir para o ativo)

Retorno: {"total": int, "nodes": [{name, status, roles, version, os, cpu, memory, age}]}
```

### `k8s_describe_resource`

```
Parâmetros:
  resource_type — tipo do recurso (ex: pod, deployment, node, pvc, ingress)
  name          — nome do recurso
  namespace     — namespace (omitir para recursos de cluster como nodes)
  context       — contexto kubeconfig (omitir para o ativo)
```

### `k8s_get_logs`

```
Parâmetros:
  pod       — nome do pod
  namespace — namespace do pod (padrão: "default")
  container — nome do container (necessário em pods multi-container)
  tail      — linhas finais, 1–5000 (padrão: 100)
  context   — contexto kubeconfig (omitir para o ativo)
```

## Formato de resposta

Todas as ferramentas retornam JSON no padrão:

```json
{
  "status": "success",
  "context": "nome-do-contexto",
  "command": "kubectl get pods -A -o json",
  "data": { ... },
  "timestamp": "2026-04-18T12:00:00+00:00"
}
```

Erros:

```json
{
  "status": "error",
  "message": "Descrição do erro",
  "details": "Detalhes adicionais",
  "context": "nome-do-contexto",
  "command": "kubectl ...",
  "timestamp": "2026-04-18T12:00:00+00:00"
}
```
