# Artigo técnico — FiscalGraph BR

- Arquivo principal: paper/main.tex.
- Bibliografia BibTeX: paper/references.bib.
- Classe inicial: IEEEtran Conference, duas colunas, em português.
- Compilação: latexmk -pdf main.tex ou pdflatex duas vezes, a partir da pasta paper.

## Pendências antes da submissão
1. Substituir nomes, instituição, disciplina e e-mails dos integrantes.
2. Confirmar se o docente disponibilizou classe SBC/IEEE específica. O repositório não continha esse template; a fonte atual usa IEEEtran como base e precisa ser ajustada ao arquivo oficial, se houver.
3. Conferir os números do benchmark após a última execução reproduzível.
4. Configurar endpoint LLM autorizado e executar o planejamento Cypher antes de declarar validação externa.
5. Executar NER no corpus real e avaliar precisão/recall com amostra anotada, se a equipe decidir reportar qualidade da extração.
6. Anexar evidências reais da reprodução local e capturas da interface.
