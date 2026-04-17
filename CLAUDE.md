# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Visão geral

Repositório pessoal de agentes e skills para o Claude Code. Não há código Python ou dependências — o projeto é composto exclusivamente por arquivos Markdown.

## Configuração

- Linguagem padrão: **pt-BR** (definida em `.claude/settings.json`)

## Agentes (`.claude/agents/`)

Cada arquivo `.md` é um sub-agente invocável pelo Claude Code.

### `gitlab-report-formatter`

Transforma texto bruto (anotações, transcrições, bullets) em relatos estruturados prontos para issues do GitLab.

**Tipos suportados:** Registro de Atividades, Reunião/Ata, Apoio Técnico, Consultoria, Incidente, Status Report.

**Saída:** Markdown puro com `**seções**` (sem `#`/`##`), checkboxes para ações, sem labels.

**Persistência:** relatos salvos automaticamente em `relatos/{tipo}-{yyyymmdd}.md`.

## Relatos (`relatos/`)

Pasta com os relatos gerados pelo `gitlab-report-formatter`, prontos para colar em issues do GitLab. Convenção de nome: `{slug-do-tipo}-{yyyymmdd}.md` com sufixo sequencial (`-2`, `-3`) em caso de múltiplos relatos no mesmo dia.
