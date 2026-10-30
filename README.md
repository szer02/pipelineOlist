# Pipeline Olist

Pipeline de dados em Python sobre o dataset público da Olist (e-commerce brasileiro, 2016 a 2018), gravando em um arquivo DuckDB local e terminando em um painel com os principais indicadores do negócio.

## Objetivo

Projeto realizado na trilha de **Engenheiro de Dados Jr** da **Pós em Engenharia de Dados e IA**.

O trabalho segue *spec-driven development*: cada etapa começou por uma especificação escrita (guardadas em [SpecsDDUtilizadas/](SpecsDDUtilizadas/)), e o código é consequência dela. Cada módulo traz a sua spec como docstring no topo, com o porquê de cada regra.

## Tecnologias

| Uso | Ferramenta |
|---|---|
| Linguagem | Python 3.13 |
| Ambiente e dependências | [uv](https://docs.astral.sh/uv/) |
| Banco analítico | DuckDB (arquivo local `olist.duckdb`) |
| Leitura dos CSV | pandas |
| Transformação e marts | SQL dentro do DuckDB |
| Painel | Streamlit + Plotly |
| Testes | pytest + pytest-cov |
| Lint e formatação | ruff |

Não há orquestrador: cada etapa é um script de linha de comando.

## Arquitetura em camadas

O banco é dividido em três schemas, um por etapa:

| Schema | Etapa | O que guarda |
|---|---|---|
| `raw` | 1. Ingestão | O dado como chegou: tudo texto, campo vazio vira nulo, sem deduplicar e sem renomear. |
| `refined` | 2. Transformação | Dado tipado (datas, inteiros, dinheiro em `DECIMAL(10,2)`), colunas em português e linhas idênticas removidas. Não corrige fatos. |
| `marts` | 3. Marts | Tabelas que respondem perguntas de negócio. As decisões sobre nulos e anomalias ficam aqui. |

```
raw/*.csv.gz  ->  raw  ->  refined  ->  marts  ->  painel (app.py) / relatório (relatorio.html)
```

## Os dados em `raw/`

A pasta [raw/](raw/) contém os nove arquivos originais do dataset da Olist, comprimidos em `.csv.gz` e sem alteração de conteúdo. São a entrada do pipeline e **não devem ser modificados**.

| Arquivo | Tabela no banco | Linhas | O que é |
|---|---|---:|---|
| `olist_orders_dataset.csv.gz` | `pedidos` | 99.441 | Um pedido: cliente, status e as datas de compra, aprovação, envio, entrega e entrega prevista. |
| `olist_order_items_dataset.csv.gz` | `itens_pedido` | 112.650 | Itens de cada pedido: produto, vendedor, preço e frete. |
| `olist_order_payments_dataset.csv.gz` | `pagamentos` | 103.886 | Pagamentos de cada pedido: forma, parcelas e valor (um pedido pode ter mais de um). |
| `olist_order_reviews_dataset.csv.gz` | `avaliacoes` | 99.224 | Avaliações dos pedidos: nota de 1 a 5, título e comentário. |
| `olist_customers_dataset.csv.gz` | `clientes` | 99.441 | Cliente de cada pedido, com CEP (prefixo), cidade e UF. |
| `olist_sellers_dataset.csv.gz` | `vendedores` | 3.095 | Vendedores, com CEP (prefixo), cidade e UF. |
| `olist_products_dataset.csv.gz` | `produtos` | 32.951 | Produtos: categoria (em português), medidas, peso e número de fotos. |
| `product_category_name_translation.csv.gz` | `traducao_categorias` | 71 | Tradução das categorias de produto para o inglês. |
| `olist_geolocation_dataset.csv.gz` | `geolocalizacao` | 1.000.163 | Latitude e longitude por prefixo de CEP. Entra só em `raw` e fica fora das etapas seguintes. |

Observação sobre o dado original: `customer_id` muda a cada pedido; quem identifica a pessoa é `customer_unique_id` (`cliente_unico_id` no `refined`).

Para baixar os dados de novo, use a página do dataset no Kaggle: [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce). Comprima cada `.csv` com gzip e mantenha os nomes da tabela acima.

## Estrutura do projeto

```
raw/                     nove .csv.gz originais da Olist (entrada do pipeline)
pipeline/db.py           conexão com o banco e funções compartilhadas
pipeline/ingestao.py     etapa 1: raw/*.csv.gz -> schema raw
pipeline/transformacao.py  etapa 2: raw -> schema refined
pipeline/marts.py        etapa 3: executa sql/marts/*.sql -> schema marts
sql/marts/NN_nome.sql    um SELECT por mart (12 marts)
painel.py                leitura dos marts, formatação e gráficos
app.py                   painel Streamlit
relatorio.py             gera relatorio.html, uma foto estática do painel
ui.py                    abre o banco na interface web do DuckDB
test/                    testes unitários de cada módulo
SpecsDDUtilizadas/       specs que guiaram cada etapa
```

### Marts

| Mart | Pergunta que responde |
|---|---|
| 01 `vendas_mensais` | Quanto vendemos por mês? |
| 02 `top_categorias` | Quais categorias mais vendem? |
| 03 `entrega_no_prazo` | Quanto chegou no prazo? |
| 04 `nota_por_categoria` | Que nota cada categoria recebe, e qual a posição dela? |
| 05 `recompra` | Quantos clientes voltaram a comprar? |
| 06 `ticket_medio_por_estado` | Qual o ticket médio de cada estado? |
| 07 `mix_pagamento` | Quanto do dinheiro pago entra por cartão, boleto, voucher e débito? |
| 08 `nota_por_prazo` | O atraso derruba a nota? |
| 09 `vendedores_pareto` | Que fração dos vendedores faz 80% da receita? |
| 10 `tempo_entrega_por_estado` | Quantos dias leva da compra até a entrega, por estado? |
| 11 `kpis` | Os cartões do painel que não saem dos marts 03 e 05. |
| 12 `clientes_por_uf` | Quantas pessoas compram de cada UF? |

## Como usar

Pré-requisitos: Python 3.13 e [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
# 1. Instalar as dependências (cria o .venv)
uv sync

# 2. Rodar o pipeline, nesta ordem (gera olist.duckdb na raiz)
uv run python -m pipeline.ingestao        # raw/*.csv.gz -> schema raw
uv run python -m pipeline.transformacao   # raw -> schema refined
uv run python -m pipeline.marts           # sql/marts/*.sql -> schema marts

# 3. Ver o resultado
uv run streamlit run app.py               # painel no navegador
uv run python relatorio.py                # gera relatorio.html na raiz
uv run python ui.py                       # interface do DuckDB em http://localhost:4213

# Testes e qualidade de código
uv run pytest --cov
uv run ruff check .
uv run ruff format .
```

O arquivo `olist.duckdb` (~100 MB) não está no repositório: ele é recriado rodando as três etapas.

> O DuckDB aceita **um único processo escrevendo** no arquivo. Feche o `ui.py` (ou qualquer outra conexão aberta) antes de rodar o pipeline, senão as etapas falham com erro de lock. O painel abre o banco só para leitura e pode ficar aberto; depois de rodar o pipeline, clique em **Recarregar dados**.

## Regras

### Do pipeline

- **`raw` nunca é corrigido.** A fronteira entre "o dado que chegou" e "o dado que eu decidi" é a passagem de `raw` para `refined`.
- **`refined` não corrige fatos.** Nulos e anomalias do negócio são preservados (pedidos entregues sem data de entrega, envio antes da compra, produtos sem categoria, pedidos com mais de uma avaliação). A decisão sobre eles fica nos marts.
- **Conversão que falha para tudo.** Datas e números são convertidos com `strptime` e `CAST`, nunca com as versões que transformam erro em nulo, e cada coluna passa antes por uma checagem de formato. Um valor inesperado interrompe a etapa com mensagem clara em vez de virar nulo em silêncio.
- **Dinheiro é `DECIMAL(10,2)`**, nunca ponto flutuante. **CEP continua texto**, para não perder o zero à esquerda.
- **Reexecução idempotente.** Cada etapa recria suas tabelas (`CREATE OR REPLACE`) em vez de acrescentar linhas. O `refined` e os `marts` são gravados em uma transação só: ou grava tudo, ou nada. Toda checagem roda antes de qualquer gravação.
- **Transformação em SQL dentro do DuckDB**, não em pandas.
- **A regra de negócio de cada mart mora inteira no seu `.sql`.** O Python só executa os arquivos. Para criar ou mudar um mart, edite o `.sql`.
- **Nenhum cálculo no painel.** O painel só lê os marts, filtra, ordena e formata. Número novo na tela exige um mart novo.

### Definições de negócio

Usadas por todos os marts, para que os números batam entre si:

| Termo | Definição |
|---|---|
| Pedido válido | `status` diferente de `canceled` e `unavailable` |
| Receita | Soma do preço dos itens, sem frete |
| Cliente | A pessoa (`cliente_unico_id`), não o cadastro por pedido |
| Mês | Mês da data de compra |
| Entregue | `status = 'delivered'` com data de entrega preenchida |
| No prazo | Data de entrega até a data prevista, inclusive |
| Categoria | Nome em inglês; sem tradução, o nome em português; sem categoria, `sem_categoria` |

### Dos testes

- Os testes **nunca usam o banco nem os dados do projeto**: cada um cria um DuckDB temporário e escreve os próprios dados inventados.
- O resultado esperado sai da conta sobre essa entrada inventada, nunca de um número da Olist.
- Meta de 60% de cobertura no total.

## Origem e licença

Dados públicos da Olist Store, via Kaggle: [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce). Redistribuídos aqui comprimidos, sem alteração de conteúdo, sob [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). Veja [LICENSE](LICENSE).
