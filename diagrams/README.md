# Diagramas do FiscalGraph BR

- `fiscalgraph-br-modelo-conceitual.mmd`: diagrama conceitual LPG editável em Mermaid.

O diagrama representa somente o núcleo inicial sustentado pelos CSVs canônicos documentados pelo Dev 2: `Empresa`, `Estabelecimento`, `Socio`, `CNAE`, `Sancao` e `Fonte`.

As setas contínuas representam relações cadastrais/societárias ou a associação de compliance. As setas tracejadas representam proveniência (`ORIGINADO_DE`) e o critério de associação de sanções. A relação `APLICADA_A` só deve ser criada mediante correspondência exata do CNPJ completo normalizado; similaridade de nome não é suficiente.
