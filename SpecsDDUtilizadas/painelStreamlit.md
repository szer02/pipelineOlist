CONTEXTO
Estou construindo um pipeline de dados em Python sobre o dataset público da
Olist. Trabalho com spec-driven development: a spec abaixo é a fonte da
verdade e o código é consequência dela. Não acrescente requisito que não
esteja escrito aqui. Se algo estiver ambíguo, pergunte antes de escrever código.

STACK
- Python 3.13, uv, DuckDB (olist.duckdb na raiz do projeto)
- streamlit e plotly (plotly.express), já instalados com uv add

O QUE JÁ EXISTE (use, não reimplemente)
O schema marts, com doze tabelas, criado por pipeline/marts.py:
  vendas_mensais, top_categorias, entrega_no_prazo, nota_por_categoria,
  recompra, ticket_medio_por_estado, mix_pagamento, nota_por_prazo,
  vendedores_pareto, tempo_entrega_por_estado, kpis, clientes_por_uf.
O rascunho da tela em design/rascunho.png.

ARTEFATOS A PRODUZIR
painel.py, na raiz: leitura, formatação e gráficos. Não importa streamlit.
app.py, na raiz: a página. Executável com:
  uv run streamlit run app.py

SPEC
1. LEITURA (painel.py)
   ler(marts) -> dict nome -> DataFrame. Para cada nome, só
   SELECT * FROM marts.<nome>. Nenhuma outra SQL.
   Conexão com duckdb.connect("olist.duckdb", read_only=True), aberta e
   fechada dentro de ler(). Motivo: conexão aberta segura o arquivo, e o
   pipeline.marts não consegue gravar com o painel de pé.

2. NENHUM CÁLCULO
   Proibido em painel.py e app.py: groupby, sum, mean, count, merge, pivot,
   e qualquer conta entre colunas. Permitido: ordenar, filtrar linhas,
   head(n), renomear coluna e formatar texto.
   Motivo: número novo na tela exige um .sql novo em marts. Se faltar
   algum número, pare e diga qual mart está faltando.

3. LAYOUT (app.py) — de cima para baixo, layout="wide"
   Cabeçalho: título "Olist · visão da operação" à esquerda; à direita,
     filtro de período (seção 5).
   Faixa 1: sete cartões (st.metric), nesta ordem, cada rótulo com a
     definição curta:
     Ticket médio (kpis.ticket_medio, reais)
     Cancelados · % de todos os pedidos (kpis.pct_cancelados, 2 casas)
     Peso do frete (kpis.pct_frete, 1 casa)
     Recompra (100 - recompra.pct_clientes da linha pedidos_por_cliente = 1,
       2 casas) -- esta é a única conta permitida, e só porque o mart 05
       guarda o complemento; se preferir, crie a coluna no mart.
     No prazo (entrega_no_prazo.pct_no_prazo, 1 casa)
     Dias até entregar (kpis.dias_entrega, 1 casa)
     Nota média (kpis.nota_media, 2 casas)
   Faixa 2, largura inteira: faturamento mensal, linha com marcadores.
   Faixa 3, três colunas iguais: receita por categoria (top 10, barras
     horizontais, maior em cima); mix de pagamento (barras por pct_valor);
     ticket médio por UF (barras horizontais, maior em cima).
   Faixa 4, três colunas iguais: clientes por UF (barras horizontais,
     maior em cima); nota por categoria (as 10 primeiras por posicao_pior,
     pontos, pior em cima); concentração de vendedores (linha de pct_acumulado por
     posicao, com linha horizontal tracejada em 80).
   Cada gráfico: título com o número do mart ("01 · Faturamento mensal"),
   uma cor só, eixo com unidade. width="stretch" (use_container_width
   está descontinuado).

4. FORMATO (painel.py), funções puras, sem streamlit e sem banco
   reais(valor, casas=2)  -> "R$ 1.003.862,14"
   pct(valor, casas=1)    -> "93,2%"
   numero(valor, casas=0) -> "96.470"
   Milhar com ponto, decimal com vírgula, sempre. Não use locale do sistema.
   Motivo: o resultado não pode depender da máquina de quem roda.
   Uma função por gráfico, recebendo o DataFrame e devolvendo a figura
   plotly. Motivo: o relatório HTML reaproveita as mesmas funções.

5. FILTRO DE PERÍODO
   st.select_slider com os meses de vendas_mensais, padrão de jan/2017 a
   ago/2018. Recorta só as linhas do gráfico de faturamento. Os cartões e
   os outros gráficos não mudam, e a página diz isso embaixo do filtro:
   "os cartões valem para o período inteiro".
   Motivo: recortar linha é SELECT; recalcular cartão por período seria
   regra de negócio fora do SQL.

6. CACHE E ERRO
   Leitura com st.cache_data. Um botão "Recarregar dados" limpa o cache.
   Sem olist.duckdb, ou faltando qualquer mart da lista do item 3: st.error
   dizendo quais e o comando "uv run python -m pipeline.marts", e st.stop().

CRITÉRIOS DE ACEITE
- Os sete cartões mostram: R$ 137,42 · 0,63% · 14,2% · 3,04% · 93,2% ·
  12,5 · 4,09.
- O faturamento abre com 20 meses (jan/2017 a ago/2018) e, com o filtro
  aberto até as pontas, mostra os 24.
- Top 10 de categorias com health_beauty em cima; nota com office_furniture
  em cima; ticket por UF com PB em cima e SP embaixo.
- Uma busca por "groupby", ".sum(", ".mean(" e "merge" em painel.py e
  app.py não encontra nada.
- Com o painel de pé, uv run python -m pipeline.marts roda sem erro de lock.

ENTREGA
1. A spec como docstring no topo de painel.py, com o motivo de cada regra.
2. O código, comentado só onde a decisão não é óbvia.
3. Uma lista final do que você assumiu e que não estava na spec.