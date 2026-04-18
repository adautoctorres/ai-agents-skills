# Skill: `gitlab-report-formatter`

Transforma anotações, transcrições e resumos informais em relatos estruturados prontos para publicar como issues no GitLab.

## Ativação

A skill é ativada automaticamente quando o usuário pede para formatar, estruturar ou criar qualquer tipo de relato — mesmo sem mencionar "GitLab" explicitamente.

Exemplos de gatilhos:
- "monta um relato do que fizemos hoje"
- "formata essa ata pra jogar no GitLab"
- "cria uma issue de incidente"
- "registra o apoio técnico de ontem"
- "preciso documentar essa reunião"

Ou diretamente via slash command:

```
/gitlab-report-formatter <texto livre ou tipo de relato>
```

## Tipos suportados

| Tipo | Quando usar |
|---|---|
| **Registro de atividades** | Trabalho executado, tarefas concluídas |
| **Reunião / Ata** | Calls, reuniões com pauta e decisões |
| **Apoio técnico** | Chamados, atendimentos de suporte |
| **Consultoria** | Análises e recomendações técnicas |
| **Incidente** | Problemas ou falhas em produção |
| **Status report** | Relatórios periódicos de progresso |

## Templates

Os templates ficam em `templates/` e definem a estrutura de cada tipo de relato:

| Arquivo | Tipo |
|---|---|
| `templates/registro-atividades.md` | Registro de trabalho executado |
| `templates/apoio-tecnico.md` | Apoio técnico e consultoria |
| `templates/ata-reuniao.md` | Reunião e ata formal |
| `templates/incidente.md` | Incidente e problema em produção |

## Regras de formatação

- Seções com `**negrito**` — nunca `#` ou `##` no corpo de issues GitLab
- `- [ ]` para itens de ação pendentes (marcáveis diretamente na interface)
- Blocos de código com linguagem explícita (` ```bash `, ` ```sql `)
- `>` para destacar excertos de logs ou avisos
- Seções sem dados são omitidas (sem seções vazias)
- Nunca sugerir labels — definidas pelo time na triagem

## Persistência

Relatos gerados são salvos automaticamente em `relatos/` na raiz do projeto.

Convenção de nome: `relatos/{slug}-{yyyymmdd}.md`  
Múltiplos relatos no mesmo dia: sufixo sequencial `-2`, `-3` etc.
