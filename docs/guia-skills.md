# Guia: Skills e Slash Commands

## Conceitos

**Slash command** — arquivo único `.md` em `.claude/commands/`. Funciona como atalho de prompt: quando invocado, seu conteúdo é enviado ao Claude com `$ARGUMENTS` substituído pelo texto digitado.

**Skill** — pasta em `.claude/skills/<nome>/` com um arquivo `SKILL.md` e recursos auxiliares (templates, exemplos). O Claude lê o `SKILL.md` para entender como executar a skill. Skills são invocadas automaticamente quando o Claude reconhece o contexto, ou explicitamente via slash command.

## Slash Command: `/gitlab-report-formatter`

**Arquivo:** `.claude/commands/gitlab-report-formatter.md`

**Uso:**
```
/gitlab-report-formatter <texto ou descrição da atividade>
```

Se nenhum argumento for fornecido, o Claude perguntará o tipo de relato e coletará as informações necessárias.

O comando delega para a skill `gitlab-report-formatter`.

## Skill: `gitlab-report-formatter`

**Localização:** `.claude/skills/gitlab-report-formatter/`

### O que faz

Transforma informações brutas (anotações, logs, bullets, transcrições) em relatos estruturados e profissionais prontos para publicar como issues no GitLab.

### Tipos de relato suportados

| Tipo | Slug do arquivo salvo |
|------|-----------------------|
| Registro de trabalho executado | `registro-atividades` |
| Reunião / call com pauta e decisões | `ata-reuniao` |
| Chamado ou atendimento de suporte | `apoio-tecnico` |
| Análise e recomendações técnicas | `apoio-tecnico` |
| Problema ou falha em produção | `incidente` |
| Relatório periódico de progresso | `status-report` |

### Templates

Os templates ficam em `.claude/skills/gitlab-report-formatter/templates/`:

| Arquivo | Quando usar |
|---------|-------------|
| `registro-atividades.md` | Trabalho executado, tarefas do dia |
| `apoio-tecnico.md` | Suporte, chamados, consultoria técnica |
| `ata-reuniao.md` | Reuniões, calls, deliberações |
| `incidente.md` | Falhas em produção, incidentes |

### Regras de formatação

- Cabeçalhos de seção com `**texto**` — nunca `#` ou `##` (quebram visual em threads do GitLab)
- Itens de ação pendentes com `- [ ]` — permite marcar direto na interface do GitLab
- Blocos de código com linguagem explícita (` ```bash `, ` ```sql `)
- Excertos de log com `>`
- Seções sem dados (Impedimentos, Riscos, Observações) devem ser **omitidas**
- Nunca sugerir labels — o time define labels na triagem

### Persistência automática

Após gerar o relato, a skill salva o conteúdo em `relatos/`:

```
relatos/{slug}-{yyyymmdd}.md
```

Se o arquivo já existir no mesmo dia, acrescenta sufixo: `-2`, `-3`, etc.

### Exemplos de uso

```
/gitlab-report-formatter reunião de alinhamento com o cliente sobre migração do Oracle, discutimos cronograma e riscos
```

```
/gitlab-report-formatter apoio técnico: usuário não conseguia conectar ao banco, causa era senha expirada, resolvido
```

Ou simplesmente:

```
/gitlab-report-formatter
```

O Claude perguntará o tipo e coletará os dados interativamente.

## Criando novas skills

Use a skill `skill-creator` para criar e iterar novas skills com evals automatizados:

```
Crie uma nova skill para [descrição do objetivo]
```
