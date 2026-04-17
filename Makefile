.PHONY:

install-agents:
	mkdir -p ~/.claude/agents
	cp .claude/agents/* ~/.claude/agents/

uninstall-agents:
	rm -rf ~/.claude/agents