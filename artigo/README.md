# Artigo técnico — FiscalGraph BR

O diretório contém a fonte LaTeX do artigo e a bibliografia no formato SBC para conferência acadêmica.

## Arquivos

- `main.tex: artigo em português, com resumo e abstract, metodologia, modelagem, implementação, avaliação, limitações e conclusão.
- `referencias.bib: referências de trabalhos científicos e das fontes institucionais.
- `sbc-template.sty e `sbc.bst: arquivos do template SBC incluídos para compilação reproduzível.

## Compilação local

Na pasta `artigo/, com uma distribuição LaTeX que inclua os pacotes requeridos:

```bash
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

No Overleaf, crie um projeto em branco, envie todos os arquivos desta pasta e selecione `main.tex como documento principal. O projeto segue o template de conferências SBC disponibilizado publicamente; o docente deve confirmar se há uma edição específica exigida para a disciplina.

## Pendências antes da submissão

1. Substituir todos os campos `[ ... ]` pelos nomes reais, e-mail e instituição dos integrantes.
2. Conferir com o docente limite de páginas, versão do template e convenção de resumo/abstract.
3. Inserir figuras/capturas reais do grupo, caso exigidas, com legendas e referência no texto.
4. Fazer revisão de conteúdo, referências, ortografia e formatação por todos os integrantes.
5. Atualizar as métricas somente após nova CI, sem misturar os resultados medidos na versão de referência com as extensões experimentais desta branch.

## Regra de integridade dos resultados

Os números na seção de avaliação são transcritos dos registros de benchmark e CI da versão de referência PR #11. A extensão de geração de Cypher por LLM e a resolução nominal `MENCAO_NOME foram adicionadas depois e não participaram desses experimentos. Não apresentar essas extensões como avaliadas até que o grupo execute a validação correspondente e registre a evidência.