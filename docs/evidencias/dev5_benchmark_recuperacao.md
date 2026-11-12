# Avaliação Quantitativa da Recuperação e Multi-hop (top-5)

- **Dataset:** versão `1.0` (20 perguntas em 10 categorias)

## 1. Comparação entre Modos de Recuperação (`k=5`)

| Modo | Consultas | Precision@5 | Recall@5 | MRR@5 | nDCG@5 | Hit@5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Vetorial puro | 16 | 0.1750 | 0.4353 | 0.4479 | 0.4065 | 0.5625 |
| Full-text puro | 16 | 0.4125 | 0.9821 | 1.0000 | 1.0000 | 1.0000 |
| Híbrido (RRF) | 16 | 0.3000 | 0.7061 | 0.6250 | 0.6218 | 0.8125 |

**Leitura correta do resultado:** neste benchmark, o **Full-text foi superior ao híbrido RRF em todas as métricas agregadas apresentadas**. O RRF superou a busca vetorial pura, mas não superou o Full-text isolado. Portanto, os dados sustentam a complementaridade do vetor em relação ao Full-text e a melhora sobre o vetor puro, não uma superioridade geral da fusão híbrida. A conclusão se limita a este recorte de 54 trechos e às 16 consultas positivas rotuladas.

## 2. Desempenho do Modo Híbrido (RRF) por Categoria (`k=5`)

| Categoria | Consultas | Precision@5 | Recall@5 | MRR@5 | nDCG@5 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `cnpj_exato` | 2 | 0.2000 | 1.0000 | 0.7500 | 0.8155 |
| `entidade_mencionada` | 2 | 0.3000 | 1.0000 | 1.0000 | 0.9386 |
| `tipo_sancao_especifica` | 2 | 0.1000 | 0.5000 | 0.5000 | 0.5000 |
| `dispositivo_legal` | 2 | 0.2000 | 0.5000 | 0.5000 | 0.5000 |
| `busca_semantica_parafrase` | 2 | 0.1000 | 0.5000 | 0.1250 | 0.2153 |
| `decisao_reconsideracao` | 2 | 0.4000 | 0.6667 | 0.3750 | 0.4572 |
| `retificacao_dou` | 2 | 0.5000 | 0.8750 | 1.0000 | 0.8545 |
| `fundamentacao_detalhada` | 2 | 0.6000 | 0.6071 | 0.7500 | 0.6934 |

## 3. Acurácia da Política de Abstenção (Orquestrador Dev1 + Dev5)

- **Acurácia global:** 100.0% (20/20)
- **Abstenções corretas (TP):** 4 | **Respostas corretas (TN):** 16
- **Falsas abstenções (FP):** 0 | **Abstenções perdidas (FN):** 0

## 4. Análise Multi-hop: Real (Dados Canônicos) vs. Sintético

| Cenário | Pares avaliados / Caminhos | Societário (`PARTICIPA_DE`) | Por CNAE (`EXERCE_CNAE`) | Saltos observados |
| --- | --- | ---: | ---: | --- |
| **Real (18 empresas)** | 4 pares / 3 com caminho | 0 | 3 | [4, 4, 4] |
| **Sintético (`PARTICIPA_DE` com rollback)** | 1 par controlado / 1 caminho | 1 | 0 | [2] |

