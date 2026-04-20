.PHONY: help install \
        mcp-add mcp-remove \
        mcp-k8s-add mcp-k8s-remove \
        mcp-gitlab-add mcp-gitlab-remove \
        mcp-add-all mcp-remove-all

help:
	@echo "Targets disponíveis:"
	@echo "  install           Instala dependências Python via uv"
	@echo "  mcp-add           Registra mcp-oracle"
	@echo "  mcp-remove        Remove mcp-oracle"
	@echo "  mcp-k8s-add       Registra mcp-k8s"
	@echo "  mcp-k8s-remove    Remove mcp-k8s"
	@echo "  mcp-gitlab-add    Registra mcp-gitlab"
	@echo "  mcp-gitlab-remove Remove mcp-gitlab"
	@echo "  mcp-add-all       Registra todos os MCPs"
	@echo "  mcp-remove-all    Remove todos os MCPs"

install:
	uv sync

mcp-oracle-add:
	claude mcp add --scope local mcp-oracle python mcps/oracle/mcp-oracle.py

mcp-oracle-remove:
	claude mcp remove mcp-oracle --scope local

mcp-k8s-add:
	claude mcp add --scope local mcp-k8s python mcps/k8s/mcp-k8s.py

mcp-k8s-remove:
	claude mcp remove mcp-k8s --scope local

mcp-gitlab-add:
	claude mcp add --scope local mcp-gitlab python mcps/gitlab/mcp-gitlab.py

mcp-gitlab-remove:
	claude mcp remove mcp-gitlab --scope local

mcp-add-all: mcp-oracle-add mcp-k8s-add mcp-gitlab-add

mcp-remove-all: mcp-oracle-remove mcp-k8s-remove mcp-gitlab-remove
