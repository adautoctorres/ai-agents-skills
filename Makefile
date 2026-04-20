.PHONY: mcp-add mcp-remove mcp-k8s-add mcp-k8s-remove mcp-gitlab-add mcp-gitlab-remove

mcp-add:
	claude mcp add --scope local mcp-oracle python mcps/oracle/mcp-oracle.py

mcp-remove:
	claude mcp remove mcp-oracle --scope local

mcp-k8s-add:
	claude mcp add --scope local mcp-k8s python mcps/k8s/mcp-k8s.py

mcp-k8s-remove:
	claude mcp remove mcp-k8s --scope local

mcp-gitlab-add:
	claude mcp add --scope local mcp-gitlab python mcps/gitlab/mcp-gitlab.py

mcp-gitlab-remove:
	claude mcp remove mcp-gitlab --scope local
