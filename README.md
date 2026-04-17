# my-ai-agents-skills

Repositório pessoal de agentes de IA e skills para o Claude Code.

## Agentes

### `gitlab-report-formatter`

Transforma texto bruto — anotações, transcrições de voz, bullets soltos — em relatos estruturados e profissionais, prontos para publicar como issues no GitLab.

**Tipos suportados:**

| Tipo | Slug |
|---|---|
| Registro de Atividades | `registro-atividades` |
| Reunião / Ata | `ata-reuniao` |
| Apoio Técnico | `apoio-tecnico` |
| Consultoria | `consultoria` |
| Incidente / Problema | `incidente` |
| Status Report | `status-report` |

**Como usar:**

Envie o texto bruto ao agente (via `@gitlab-report-formatter` ou invocando o sub-agente no Claude Code). Ele identifica o tipo automaticamente, formata o relato e salva em `relatos/`.

**Saída:**
- Markdown puro com `**seções em negrito**` (sem headers `#`/`##`)
- Sem labels GitLab
- Seções opcionais (Riscos, Impedimentos, Observações) apenas se houver conteúdo real no texto de entrada

**Persistência:**

Relatos salvos em `relatos/{slug}-{yyyymmdd}.md` com sufixo sequencial quando há múltiplos no mesmo dia.

## Estrutura

```
.claude/
  agents/
    gitlab-report-formatter.md   # definição do agente
relatos/                       # relatos gerados, prontos para o GitLab
CLAUDE.md                      # contexto para o Claude Code
```