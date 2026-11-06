# Diagramas do FiscalGraph BR

- `fiscalgraph-br-modelo-conceitual.mmd`: diagrama conceitual LPG editável em Mermaid.
- `fiscalgraph-br-modelo-conceitual.dot`: especificação gráfica em Graphviz.
- `fiscalgraph-br-modelo-conceitual.svg` / `.png`: exportações visuais do modelo.

O diagrama representa o modelo conceitual integrado do FiscalGraph BR, contemplando o núcleo canônico (`Empresa`, `Estabelecimento`, `Socio`, `CNAE`, `Sancao` e `Fonte`) e a extensão Text-to-Graph com o nó documental `Trecho`.

As setas contínuas representam relações cadastrais/societárias (`PARTICIPA_DE`, `POSSUI_ESTABELECIMENTO`, `EXERCE_CNAE`), de conformidade (`APLICADA_A`), estruturais de extrato (`EXTRATO_DE`) e menções textuais candidatas (`MENCIONA`). As setas de proveniência (`ORIGINADO_DE`) associam cada entidade à respetiva fonte de coleta. A relação `APLICADA_A` é estabelecida estritamente mediante correspondência exata do CNPJ completo; similaridade de nome não é suficiente.