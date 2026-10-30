"""Página do painel Olist. Execução: uv run streamlit run app.py

A spec está no docstring de painel.py. Aqui só ficam o layout, o filtro de
período, o cache e as mensagens de erro.
"""

import pandas as pd
import streamlit as st

import painel

# Os marts que a página usa (item 3 da spec). Faltando qualquer um, a página para.
MARTS = [
    "kpis",
    "recompra",
    "entrega_no_prazo",
    "vendas_mensais",
    "top_categorias",
    "mix_pagamento",
    "ticket_medio_por_estado",
    "clientes_por_uf",
    "nota_por_categoria",
    "vendedores_pareto",
]

st.set_page_config(page_title="Olist · visão da operação", layout="wide")


@st.cache_data
def carregar():
    return painel.ler(MARTS)


col_titulo, col_filtro = st.columns([2, 1])

with col_titulo:
    st.title("Olist · visão da operação")
    # Antes da leitura, para o botão existir também na tela de erro.
    if st.button("Recarregar dados"):
        carregar.clear()

try:
    dados = carregar()
except FileNotFoundError:
    st.error(
        "Não encontrei o olist.duckdb na pasta do projeto. Rode: uv run python -m pipeline.marts"
    )
    st.stop()

faltando = [nome for nome in MARTS if nome not in dados]
if faltando:
    st.error(
        "Faltam marts no banco: "
        + ", ".join(f"marts.{nome}" for nome in faltando)
        + ". Rode: uv run python -m pipeline.marts"
    )
    st.stop()

# --- filtro de período: recorta só as linhas do faturamento mensal ---------

vendas = dados["vendas_mensais"].sort_values("mes")
meses = list(vendas["mes"])

with col_filtro:
    inicio, fim = st.select_slider(
        "Período do faturamento",
        options=meses,
        value=(pd.Timestamp("2017-01-01"), pd.Timestamp("2018-08-01")),
        format_func=painel.mes,
    )
    st.caption("os cartões valem para o período inteiro")

vendas_periodo = vendas[(vendas["mes"] >= inicio) & (vendas["mes"] <= fim)]

# --- faixa 1: cartões ------------------------------------------------------

kpis = dados["kpis"].iloc[0]
recompra = dados["recompra"]
um_pedido = recompra[recompra["pedidos_por_cliente"] == 1].iloc[0]
entrega = dados["entrega_no_prazo"].iloc[0]

cartoes = [
    ("Ticket médio · receita por pedido válido", painel.reais(kpis["ticket_medio"])),
    ("Cancelados · % de todos os pedidos", painel.pct(kpis["pct_cancelados"], 2)),
    ("Peso do frete · % de itens + frete", painel.pct(kpis["pct_frete"], 1)),
    # Única conta permitida pela spec: o mart 05 guarda o complemento (quem comprou uma vez só).
    (
        "Recompra · % de clientes com 2+ pedidos",
        painel.pct(100 - um_pedido["pct_clientes"], 2),
    ),
    ("No prazo · % dos pedidos entregues", painel.pct(entrega["pct_no_prazo"], 1)),
    (
        "Dias até entregar · média, da compra à entrega",
        painel.numero(kpis["dias_entrega"], 1),
    ),
    ("Nota média · avaliações, de 1 a 5", painel.numero(kpis["nota_media"], 2)),
]
for coluna, (rotulo, valor) in zip(st.columns(7), cartoes):
    coluna.metric(rotulo, valor, border=True)

# --- faixa 2: faturamento mensal -------------------------------------------

st.plotly_chart(painel.faturamento_mensal(vendas_periodo), width="stretch")

# --- faixa 3 ---------------------------------------------------------------

c1, c2, c3 = st.columns(3)
c1.plotly_chart(painel.receita_por_categoria(dados["top_categorias"]), width="stretch")
c2.plotly_chart(painel.mix_pagamento(dados["mix_pagamento"]), width="stretch")
c3.plotly_chart(painel.ticket_por_uf(dados["ticket_medio_por_estado"]), width="stretch")

# --- faixa 4 ---------------------------------------------------------------

c1, c2, c3 = st.columns(3)
c1.plotly_chart(painel.clientes_por_uf(dados["clientes_por_uf"]), width="stretch")
c2.plotly_chart(painel.nota_por_categoria(dados["nota_por_categoria"]), width="stretch")
c3.plotly_chart(
    painel.concentracao_vendedores(dados["vendedores_pareto"]), width="stretch"
)
