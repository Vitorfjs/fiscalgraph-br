# FiscalGraph BR — Validação do Neo4j

> Preencher este documento somente com resultados efetivamente observados. Não declarar execução concluída com base apenas na existência dos scripts.

## 1. Ambiente utilizado

| Item | Valor observado |
|---|---|
| Neo4j | 5.x Community (registrar versão completa exibida pelo `dbms.components()`) |
| Execução | Docker Compose local |
| Data/hora da validação | preencher após executar |
| Responsável pela execução | preencher |
| Branch/commit testado | preencher |

Consulta para registrar a versão:

```cypher
CALL dbms.components() YIELD name, versions, edition
RETURN name, versions, edition;
```

## 2. Preparação

1. Iniciar o container Neo4j já configurado pelo projeto.
2. Confirmar que `python scripts/check_neo4j.py` retorna conexão bem-sucedida.
3. Confirmar que os sete CSVs existem em `data/processed/canonical/`.
4. Executar primeiro `python scripts/load_canonical_data.py --dry-run`.
5. Não executar a carga real enquanto o dry-run apresentar erro.

## 3. Criação do schema

Executar todos os comandos do arquivo `cypher/01_schema_fiscalgraph.cypher` no Neo4j Browser, um comando por vez.

O schema cria:

- 7 constraints de unicidade: Empresa, Estabelecimento, Socio, CNAE, Sancao, Fonte e Trecho;
- índices de filtro para situação cadastral, localização, porte, tipo de registro e número de processo;
- 1 índice full-text compartilhado para campos textuais de Empresa, Socio, Sancao e Trecho.

As constraints de unicidade criam os respectivos índices de apoio. Não criar índices duplicados para as mesmas chaves.

## 4. Carga dos dados canônicos

Na raiz do repositório:

```bash
python scripts/load_canonical_data.py --dry-run
python scripts/load_canonical_data.py
```

O carregador usa `MERGE`, preserva os identificadores como strings e não apaga nós ou relacionamentos existentes. A execução repetida deve manter as contagens, sem duplicar entidades ou relações.

A carga deste script cria Empresa, Estabelecimento, Socio, CNAE, Sancao e Fonte. Os nós Trecho e seus relacionamentos são criados posteriormente pelo loader do Dev4.

## 5. Consultas de validação

Executar as consultas do arquivo `cypher/02_validacao_schema.cypher`, uma por vez. Registrar os resultados observados:

| Verificação | Resultado observado | Esperado |
|---|---|---|
| Constraints de unicidade | preencher | 7 constraints nomeadas |
| Índices | preencher | índices criados; estado `ONLINE` |
| Nós Empresa | preencher | 16 no snapshot atual |
| Nós Estabelecimento | preencher | 16 no snapshot atual |
| Nós Socio | preencher | 24 no snapshot atual |
| Nós CNAE | preencher | 31 no snapshot atual |
| Nós Sancao | preencher | 50 no snapshot atual |
| Nós Fonte | preencher | 4 no snapshot atual |
| Estabelecimentos sem Empresa | preencher | 0 |
| Sócios sem Empresa | preencher | 0 |
| Sanções sem Estabelecimento de CNPJ exato | preencher | 0 |
| Entidades sem ORIGINADO_DE | preencher | 0 após as cargas correspondentes |

As quantidades acima correspondem aos CSVs atuais examinados. Se os CSVs forem regenerados, as quantidades esperadas devem ser atualizadas para a versão realmente carregada.

## 6. Idempotência

1. Anotar as contagens de nós e relacionamentos após a primeira carga.
2. Executar novamente `python scripts/load_canonical_data.py`.
3. Executar novamente as consultas de contagem.
4. Confirmar que as contagens não aumentaram por duplicação.

Resultado observado: preencher.

## 7. Evidências

Salvar capturas do Neo4j Browser mostrando:

- `SHOW CONSTRAINTS`;
- `SHOW INDEXES` com estado dos índices;
- contagens dos nós e relacionamentos;
- consultas de integridade com zero referências órfãs.

Armazenar as capturas em `docs/evidencias/` ou em outro diretório definido pelo grupo. Não incluir senha, token ou arquivo `.env` nas evidências.

## 8. Limitações

- O carregador valida referências por identificadores e não realiza resolução de identidade por nome.
- CNPJ é mantido como texto; a validação estrutural não calcula os dígitos verificadores.
- Ausência de `data_fim` em uma sanção não prova vigência atual.
- Os dados representam o snapshot documentado nos arquivos de fonte.
- O índice vetorial e a geração de embeddings pertencem à etapa Dev5.
- O nó Trecho é gerado a partir dos campos textuais do registro de compliance; `MENCIONA` permanece como relação candidata.
