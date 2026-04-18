.PHONY: mcp-add mcp-remove

mcp-add:
	claude mcp add --scope local mcp-oracle python mcps/oracle/mcp-oracle.py

mcp-remove:
	claude mcp remove mcp-oracle --scope local
