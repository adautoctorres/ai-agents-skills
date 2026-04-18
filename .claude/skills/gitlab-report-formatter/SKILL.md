---
name: gitlab-report-formatter
description: Transforma informações brutas (anotações, logs, resumos informais) em relatos estruturados e profissionais prontos para issues do GitLab. Use esta skill sempre que o usuário quiser formatar, estruturar ou criar um relato, ata, registro, apoio técnico, consultoria, incidente ou status report para o GitLab — mesmo que não mencione explicitamente "GitLab" ou "issue". Exemplos de gatilhos: "monta um relato do que fizemos hoje", "formata essa ata pra jogar no GitLab", "cria uma issue de incidente", "registra o apoio técnico de ontem", "preciso documentar essa reunião".
---

## O que fazer

Transforme o texto bruto fornecido pelo usuário em um relato estruturado, pronto para publicar como issue no GitLab. O objetivo é produzir documentação técnica clara e rastreável a partir de anotações informais, sem inventar nada.

## Processo

1. **Identifique o tipo** de relato a partir do conteúdo (ou pergunte se for ambíguo — veja tabela abaixo)
2. **Extraia** quem, o quê, quando, onde, por quê e como
3. **Separe** fatos de pendências e concluídos de itens em aberto
4. **Proponha um título** conciso para a issue
5. **Formate o corpo** usando o template correspondente ao tipo
6. **Pergunte** se falta alguma informação antes de finalizar

## Tipos suportados

| Tipo | Slug |
|---|---|
| Registro de trabalho executado | `registro-atividades` |
| Reunião / call com pauta e decisões | `ata-reuniao` |
| Ata formal com deliberações | `ata-reuniao` |
| Chamado ou atendimento de suporte | `apoio-tecnico` |
| Análise e recomendações técnicas | `consultoria` |
| Problema ou falha em produção | `incidente` |
| Relatório periódico de progresso | `status-report` |

## Regras de formatação

O GitLab renderiza Markdown, mas issues têm convenções próprias que melhoram a legibilidade:

- Use `**título da seção**` para cabeçalhos — nunca `#` ou `##` no corpo da issue, pois quebram o visual em threads de comentário
- Use `- [ ]` para itens de ação pendentes — permite marcar diretamente na interface do GitLab
- Use blocos de código com linguagem explícita (` ```bash `, ` ```sql `) quando houver comandos ou logs
- Use `>` para destacar excertos de logs ou avisos importantes
- Omita seções sem dados reais (Impedimentos, Riscos, Observações) — seções vazias poluem o relato sem agregar valor
- Nunca sugira labels — o time define labels na triagem, não no corpo do relato

## Templates

Os templates ficam em `templates/`. Leia apenas o arquivo correspondente ao tipo identificado:

| Tipo | Arquivo |
|---|---|
| Registro de atividades | `templates/registro-atividades.md` |
| Apoio técnico / Consultoria | `templates/apoio-tecnico.md` |
| Reunião / Ata | `templates/ata-reuniao.md` |
| Incidente / Problema | `templates/incidente.md` |

## Persistência

Após gerar o relato, salve o conteúdo em `relatos/` na raiz do projeto — isso permite que o usuário acesse o histórico sem depender do histórico do chat.

Convenção de nome: `relatos/{slug}-{yyyymmdd}.md`  
Se o arquivo já existir, acrescente sufixo sequencial: `-2`, `-3`, etc.  
Crie a pasta `relatos/` se não existir.
