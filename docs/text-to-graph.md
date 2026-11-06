# Text-to-Graph — dev4

Etapa que transforma os campos textuais dos registros de compliance (CEIS/CNEP) em nós `Trecho`
rastreáveis e em menções candidatas de entidades, para alimentar a busca semântica/full-text do
GraphRAG (dev5). **Nenhuma menção extraída de texto é tratada como vínculo confirmado.**

## Arquivos

| Arquivo | Função |
| --- | --- |
| `pipeline/text_to_graph/extractor.py` | Lê `compliance.csv`, monta trechos, mascara CPF e extrai menções (CNPJ por regex, ORG por spaCy). Gera `trechos.jsonl`. |
| `pipeline/text_to_graph/load_graph.py` | Carrega `Trecho` no Neo4j e cria `EXTRATO_DE`, `ORIGINADO_DE` e `MENCIONA` (candidata). Possui `--dry-run`. |
| `tests/test_text_to_graph.py` | 27 testes unitários com dados sintéticos (sem Neo4j e sem spaCy). |
| `data/fixtures/compliance_sintetico.csv` | Fixture 100% sintética; não representa registro real. |
| `requirements-dev4.txt` | Dependência adicional: spaCy. |

## Etapas

1. **Trecho textual.** Concatena, nesta ordem e separados por quebra de linha, os campos disponíveis
   `descricao`, `observacoes` e `fundamentacao_legal`. Registros sem nenhum texto são ignorados e contabilizados.
   `trecho_id = sha256(registro_id | texto)[:24]`: estável entre execuções (mesma entrada → mesmo id).
2. **Privacidade.** CPF formatado (`000.000.000-00`) é substituído por `[CPF REMOVIDO]` **antes** da extração;
   a quantidade mascarada fica em `cpf_mascarados`. CPF não sai do pipeline.
3. **Menções de CNPJ (regex estrutural).** Aceita `XX.XXX.XXX/XXXX-XX` e a forma contínua de 14 posições.
   As 12 primeiras posições aceitam letras maiúsculas e dígitos (CNPJ alfanumérico, emitido pela RFB desde
   31/07/2026); as 2 últimas são dígitos. O valor é normalizado para string de 14 posições, preservando zeros à
   esquerda e letras. Sequências contínuas sem nenhum dígito nas 12 primeiras posições são descartadas (palavras).
   Dígitos verificadores **não** são calculados (validação apenas estrutural).
4. **NER de organizações.** spaCy `pt_core_news_sm`, entidades `ORG`, ativado com `--with-spacy`. Filtros:
   - linhas com mais de 80% de letras maiúsculas (transcrição de lei em `fundamentacao_legal`) são descartadas,
     pois o modelo marca quase toda palavra em CAIXA ALTA como `ORG` nesse tipo de texto;
   - entidades com menos de 3 caracteres, sem letras ou em lista de termos genéricos (`DOU`, `CNPJ`, `Decisão`…).
5. **Relação (RE por regra).** Cada menção recebe `status = "CANDIDATA"`. No grafo, apenas menções de **CNPJ**
   com igualdade **exata** a `Estabelecimento.cnpj` geram `(Trecho)-[:MENCIONA {metodo, status, inicio, fim}]->(Estabelecimento)`.
   Menções de organização ficam somente no JSONL e na propriedade `Trecho.mencoes_json`. Nome nunca funde entidades.
6. **Procedência.** Cada trecho preserva `registro_id`, `fonte_id`, `url_fonte`, `registro_origem` e
   `metodo_extracao`; os offsets `inicio`/`fim` apontam para o trecho exato de `texto`.

`RegistroCompliance/Sancao-[:REFERE_SE_A|APLICADA_A]->Empresa/Estabelecimento` **não** é criada por esta etapa:
pertence à carga estruturada (dev3), a partir da coluna `cnpj_sancionado`.

### Formato de `data/processed/trechos.jsonl`

```json
{"trecho_id": "…", "registro_id": "CEIS-289814", "texto": "…", "fonte_id": "F-CGU-CEIS",
 "url_fonte": "https://portaldatransparencia.gov.br/download-de-dados/ceis",
 "registro_origem": "20261104_CEIS.csv:L…", "metodo_extracao": "regex_cnpj+spacy_ner",
 "mencoes": [{"tipo": "CNPJ", "valor": "01340937000179", "inicio": 120, "fim": 138,
              "metodo": "regex_cnpj_estrutural", "status": "CANDIDATA"}]}
```

## Como executar

Na raiz do repositório, com a `.venv` ativa:

```bash
pip install -r requirements.txt -r requirements-dev4.txt
python -m spacy download pt_core_news_sm

# 1. Testes (não exigem spaCy nem Neo4j)
python -m unittest discover -s tests -p "test_text_to_graph.py" -v

# 2. Extração no recorte canônico de dev2
python pipeline/text_to_graph/extractor.py --input data/processed/canonical/compliance.csv --output data/processed/trechos.jsonl --with-spacy --stats data/processed/trechos_stats.json

# 3. Conferência sem banco
python pipeline/text_to_graph/load_graph.py --input data/processed/trechos.jsonl --dry-run

# 4. Carga no Neo4j (após schema e carga estruturada de dev3; requer .env local)
python pipeline/text_to_graph/load_graph.py --input data/processed/trechos.jsonl
```

Sem o modelo spaCy, rode o passo 2 sem `--with-spacy`: somente CNPJ é extraído e a etapa NER deve ser
registrada como pendente.

## Resultados (execução local de 05/11/2026)

- **CSV de entrada:** `data/processed/canonical/compliance.csv` da branch `dev2` (PR ainda não integrado à `main`
  no momento da execução); fontes `F-CGU-CEIS` e `F-CGU-CNEP`, competência 2026-11-04.
- **Ambiente:** Python 3.13, spaCy 3.8, `pt_core_news_sm` 3.8.0.
- **Registros lidos:** 50 (CEIS e CNEP).
- **Registros sem texto:** 0.
- **Trechos gerados:** 50 (tamanho médio ≈ 738 caracteres; nenhum duplicado).
- **CPFs mascarados:** 0.
- **Menções CNPJ:** 2 (2 CNPJs distintos), ambas iguais ao `cnpj_sancionado` do próprio registro
  (`CNEP-310577` e `CEIS-289814`).
- **CNPJs que existem como `Estabelecimento.cnpj` no recorte:** 2 de 2 → candidatos a `MENCIONA` na carga.
- **Organizações extraídas via NER:** 4, em 2 trechos — `GALVÃO ENGENHARIA`, `Diretoria de Empreendimentos`,
  `Diretoria Executiva` (CEIS-387835) e `REFIS` (CNEP-349213). Cada menção inclui `valor_normalizado` (sem acento,
  em maiúsculas e sem sufixos jurídicos como S/A ou EIRELI) para agrupamento e resolução leve de entidades.
- **Validação no Neo4j 5.26:**
  - 50 nós `:Trecho` carregados com sucesso;
  - 50 relações `:EXTRATO_DE` conectadas aos registros de compliance correspondentes;
  - 50 relações `:ORIGINADO_DE` conectadas às fontes oficiais (`F-CGU-CEIS` e `F-CGU-CNEP`);
  - 2 relações `:MENCIONA` criadas com `status = 'CANDIDATA'` por correspondência exata de CNPJ;
  - 0 menções não resolvidas;
  - 4 menções de organização preservadas em `mencoes_json` sem criar vínculos espúrios por nome;
  - Idempotência validada: re-execução do loader manteve exatamente a mesma contagem de nós e relações;
  - Multi-hop validado: travessia de 4 saltos (`Trecho -> Sancao -> Estabelecimento <- Empresa <- Socio`) retornou 68 caminhos para as 16 empresas do recorte.

### Revisão

- Conferência automática dos 50 trechos: todos têm `registro_id`, `fonte_id`, `url_fonte` e `registro_origem`
  preenchidos, os 50 `trecho_id` são distintos e os offsets das menções apontam para o texto correto.
- As menções foram revisadas manualmente e os trechos amostrais foram validados visualmente no Neo4j Browser.
- Antes do filtro de linhas em maiúsculas, o NER produzia 239 "organizações" (ex.: `GARANTIDA`, `PODERÁ`, `PRAZO`),
  quase todas falsos positivos vindos da transcrição de lei. Com o filtro restaram 4.
- **Erros típicos observados:**
  - falso negativo: "Agroservice Empreiteira Agrícola EIRELI" (CNEP-310577) não foi reconhecida como ORG;
  - `REFIS` e `Diretoria Executiva` são programas/unidades, não pessoas jurídicas;
  - `GALVÃO ENGENHARIA` aparece sem o sufixo `S/A` (span parcial).

Não são reportadas métricas de acurácia (precisão/recall), pois não há conjunto de verdade-terreno anotado.

## Limitações

- O `pt_core_news_sm` é um modelo pequeno, treinado em texto jornalístico; reconhece mal organizações em texto
  administrativo curto e em CAIXA ALTA.
- O filtro de linhas em maiúsculas pode descartar nomes válidos escritos em uma linha totalmente maiúscula.
- O regex de CNPJ não verifica dígitos verificadores; um número de 14 dígitos qualquer pode ser capturado.
- Apenas CPF formatado é mascarado; CPF sem pontuação não é distinguido de outros números de 11 dígitos.
- `MENCIONA` indica que o texto cita um CNPJ — não prova que a organização é sancionada, responsável ou parte
  do processo.
- Correspondência por nome permanece fora do processo automático.
- A fixture é totalmente sintética e não pode ser usada como evidência de domínio real.

## Pontos de integração (para o coordenador)

- A modelagem de dev3 usa o rótulo `Sancao`; o contrato usa `RegistroCompliance`. O loader procura o registro
  pelos **dois** rótulos (por `registro_id`), então funciona com qualquer um.
- `docs/modelagem-lpg.md` (dev3) lista `Trecho` como fora do escopo atual. Para a carga, o schema precisa da
  constraint `Trecho.trecho_id IS UNIQUE`; o índice full-text em `Trecho.texto` e o índice vetorial de 384
  dimensões em `Trecho.embedding` são usados por dev5. O loader não grava `embedding` (responsabilidade de dev5).
