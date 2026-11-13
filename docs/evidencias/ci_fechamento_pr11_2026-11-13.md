# Evidência de CI — Fechamento FiscalGraph BR (2026-11-13)

- Repositório: `Vitorfjs/fiscalgraph-br`
- Commit avaliado: `1f5577be3148d7d9294841bcfc6d55abaf1cd305`
- PR: #11 (`fechamento-finalizacao` → `main`)
- Workflow completo: run `43436377286` — success
- Workflow de integração: run `43436377182` — success

## Etapas do workflow completo

| Etapa | Resultado |
| --- | --- |
| Instalação de dependências | Aprovada |
| Aplicar e validar schema Neo4j (`scripts/apply_schema.py`) | Aprovada |
| Carregar dados canônicos | Aprovada |
| Carregar trechos e menções | Aprovada |
| Gerar embeddings e índice vetorial | Aprovada |
| Executar suíte completa | Aprovada |
| Publicar log de testes | Aprovada |

## Resultado dos testes

`Ran 181 tests in 8.220s`  
`OK`

O artefato `dev5-ci-test-results` foi publicado no run `43436377286`. O workflow está configurado para retenção de 14 dias.

## Escopo desta evidência

Esta validação ocorreu no ambiente temporário do GitHub Actions, com Neo4j `5.26-community`. Não é uma execução local feita pelo grupo. A validação manual 8/8 descrita em `validacao_manual_dev5_etapa4_2026-11-12.md` é uma evidência separada reportada pelo grupo.
