# 🧠 Prompt — Criação de MCP para Kubernetes (`kubectl`)

## 🎯 Objetivo

Criar um **MCP (Model Context Protocol)** em Python capaz de executar comandos `kubectl` de forma segura, controlada e auditável, permitindo que uma IA interaja com múltiplos clusters Kubernetes através dos contextos definidos no kubeconfig.

---

## 🧩 Descrição do MCP

Você deve implementar um servidor MCP que:

* Execute comandos `kubectl`
* Leia e interprete `kubeconfig`
* Liste e altere contextos
* Retorne saídas estruturadas (JSON sempre que possível)
* Aplique controles de segurança rigorosos

---

## ⚙️ Funcionalidades obrigatórias

### 1. 📊 Listar contextos

* Comando base:

  * `kubectl config get-contexts`
* Retorno estruturado contendo:

  * nome do contexto
  * cluster associado
  * usuário
  * contexto atual

---

### 2. 🔍 Obter configuração completa

* Comando:

  * `kubectl config view --raw`
* Retornar YAML/JSON completo

---

### 3. 🔄 Trocar contexto

* Comando:

  * `kubectl config use-context <context>`
* Validar existência antes de executar

---

### 4. 📦 Consultar recursos

Permitir execução controlada de:

* `kubectl get pods -A`
* `kubectl get svc -A`
* `kubectl get nodes`
* `kubectl describe <resource>`
* `kubectl logs <pod>`

⚠️ Sempre tentar usar:

* `-o json` quando possível

---

### 5. 🚨 Validação de segurança (OBRIGATÓRIO)

O MCP deve bloquear comandos perigosos como:

* `kubectl delete`
* `kubectl apply`
* `kubectl patch`
* `kubectl exec`
* `kubectl port-forward`

Permitir apenas comandos de leitura (`get`, `describe`, `logs`)

---

### 6. 🧠 Normalização de saída

* Converter saída para JSON quando possível
* Caso não seja possível:

  * retornar texto estruturado
* Incluir:

  * comando executado
  * timestamp
  * contexto ativo

---

### 7. 🧾 Logging e auditoria

Registrar todas as execuções com:

* comando
* contexto
* timestamp
* resultado (sucesso/erro)

---

### 8. ❌ Tratamento de erros

Capturar e retornar erros como:

* contexto inexistente
* cluster inacessível
* timeout
* erro de autenticação

Formato padronizado:

{
"status": "error",
"message": "...",
"details": "..."
}

---

## 🔐 Requisitos de segurança

* Nunca permitir execução arbitrária de shell
* Sanitizar inputs
* Trabalhar com whitelist de comandos
* Não expor credenciais sensíveis
* Suportar execução em modo read-only

---

## 🧱 Arquitetura esperada

* Linguagem: Python
* Uso de:

  * subprocess (controlado) OU client oficial Kubernetes (`kubernetes-python`)
* Estrutura modular:

  * executor de comandos
  * parser de saída
  * camada de segurança
  * handlers MCP

---

## 📡 Interface MCP

O MCP deve expor métodos como:

* `list_contexts()`
* `get_current_context()`
* `switch_context(context_name)`
* `get_pods(all_namespaces=True)`
* `get_services()`
* `get_nodes()`
* `describe_resource(type, name, namespace)`
* `get_logs(pod, namespace)`

---

## 📤 Formato de resposta

Sempre retornar JSON no padrão:

{
"status": "success",
"context": "nome-do-contexto",
"command": "kubectl ...",
"data": {...},
"timestamp": "ISO8601"
}

---

## 🧪 Exemplo de uso

### Input:

"Liste os pods de todos os namespaces"

### Execução:

`kubectl get pods -A -o json`

### Output esperado:

JSON estruturado com lista de pods

---

## 🚀 Diferenciais desejados

* Cache opcional de respostas
* Timeout configurável
* Suporte a múltiplos kubeconfigs
* Integração futura com RBAC
* Facilidade para rodar em container (Docker/Kubernetes)

---

## 📦 Entregáveis esperados

* Código completo em Python
* Estrutura de projeto organizada
* Exemplo de execução
* README com instruções

---

## ⚠️ Regras finais

* Priorizar segurança acima de flexibilidade
* Nunca executar comandos destrutivos
* Código deve ser pronto para produção
* Seguir boas práticas de engenharia

---

## 💡 Observação

Este MCP será utilizado por uma IA em ambiente Kubernetes, podendo atuar como base para:

* automação de operações (observabilidade)
* troubleshooting assistido
* análise de múltiplos clusters


