"""Painel Olist: leitura dos marts, formatação de números e gráficos.

Usado por app.py (a página Streamlit). Não importa streamlit: as funções de
gráfico também servem ao relatório HTML.

SPEC

1. Leitura
   ler(marts) -> dict nome -> DataFrame. Para cada nome, só
   SELECT * FROM marts.<nome>; nenhuma outra SQL. A conexão é
   duckdb.connect("olist.duckdb", read_only=True), aberta e fechada dentro
   de ler().
   Por quê: conexão aberta segura o arquivo, e o pipeline.marts não consegue
   gravar com o painel de pé. Abrindo e fechando a cada leitura, o lock dura
   só o tempo do SELECT.
   Sem o arquivo, ler() levanta FileNotFoundError; um mart que não existe no
   banco fica fora do dict. Quem chama compara as chaves com a lista que
   pediu e diz quais faltam.

2. Nenhum cálculo
   Proibido aqui e em app.py: agrupar, somar, tirar média, contar, juntar
   tabelas, pivotar e qualquer conta entre colunas. Permitido: ordenar,
   filtrar linhas, pegar as n primeiras, renomear coluna e formatar texto.
   Por quê: número novo na tela exige um .sql novo em marts. A regra de
   negócio mora inteira no SQL; o painel só mostra o que o mart já tem.
   Única exceção, em app.py: o cartão de recompra é 100 menos o pct_clientes
   da linha pedidos_por_cliente = 1, porque o mart 05 guarda o complemento.

3. Formato
   reais(valor, casas=2)  -> "R$ 1.003.862,14"
   pct(valor, casas=1)    -> "93,2%"
   numero(valor, casas=0) -> "96.470"
   mes(data)              -> "jan/2017"
   Milhar com ponto, decimal com vírgula, sempre, sem usar o locale do
   sistema. Funções puras, sem streamlit e sem banco.
   Por quê: o resultado não pode depender da máquina de quem roda.

4. Gráficos
   Uma função por gráfico, recebendo o DataFrame do mart e devolvendo a
   figura plotly. Título com o número do mart ("01 · Faturamento mensal"),
   uma cor só, eixo com unidade. Separadores brasileiros também nos eixos e
   no texto ao passar o mouse.
   Por quê: o relatório HTML reaproveita as mesmas funções; o número do mart
   no título diz de qual .sql o gráfico sai.
"""

from pathlib import Path

import duckdb
import plotly.express as px

ARQUIVO = "olist.duckdb"

COR = "#1f5fa8"
ALTURA = 520  # gráficos das faixas 3 e 4: cabe as 27 UFs sem esmagar as barras

MESES = [
    "jan",
    "fev",
    "mar",
    "abr",
    "mai",
    "jun",
    "jul",
    "ago",
    "set",
    "out",
    "nov",
    "dez",
]


# --- leitura ---------------------------------------------------------------


def ler(marts):
    if not Path(ARQUIVO).exists():
        raise FileNotFoundError(ARQUIVO)
    con = duckdb.connect(ARQUIVO, read_only=True)
    try:
        dados = {}
        for nome in marts:
            try:
                dados[nome] = con.sql(f"SELECT * FROM marts.{nome}").df()
            except duckdb.CatalogException:
                continue  # mart ausente: quem chama lista os que faltam
        return dados
    finally:
        con.close()


# --- formato ---------------------------------------------------------------


def _brasil(valor, casas):
    # O format do Python usa vírgula no milhar e ponto no decimal; troca os dois.
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def reais(valor, casas=2):
    return f"R$ {_brasil(valor, casas)}"


def pct(valor, casas=1):
    return f"{_brasil(valor, casas)}%"


def numero(valor, casas=0):
    return _brasil(valor, casas)


def mes(data):
    return f"{MESES[data.month - 1]}/{data.year}"


# --- gráficos --------------------------------------------------------------


def _layout(fig, titulo, eixo_x, eixo_y, altura=None):
    fig.update_layout(
        title=titulo,
        xaxis_title=eixo_x,
        yaxis_title=eixo_y,
        separators=",.",  # decimal vírgula, milhar ponto (formato d3 do plotly)
        showlegend=False,
        height=altura,
        margin={"l": 10, "r": 10, "t": 50, "b": 10},
    )
    return fig


def faturamento_mensal(df):
    fig = px.line(df, x="mes", y="receita", markers=True, color_discrete_sequence=[COR])
    fig.update_traces(hovertemplate="%{x|%m/%Y}<br>R$ %{y:,.2f}<extra></extra>")
    # Data como mm/aaaa: o nome do mês do plotly sairia em inglês.
    fig.update_xaxes(tickformat="%m/%Y")
    fig.update_yaxes(tickprefix="R$ ", tickformat=",.0f")
    return _layout(
        fig, "01 · Faturamento mensal", "Mês da compra", "Receita (R$, sem frete)"
    )


def receita_por_categoria(df):
    top = df.sort_values("receita", ascending=False).head(10)
    fig = px.bar(
        top, x="receita", y="categoria", orientation="h", color_discrete_sequence=[COR]
    )
    fig.update_traces(hovertemplate="%{y}<br>R$ %{x:,.2f}<extra></extra>")
    # Barra horizontal desenha a primeira linha embaixo; inverter põe a maior em cima.
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(tickprefix="R$ ", tickformat=",.0f")
    return _layout(
        fig,
        "02 · Receita por categoria (top 10)",
        "Receita (R$, sem frete)",
        "Categoria",
        ALTURA,
    )


def mix_pagamento(df):
    ordenado = df.sort_values("pct_valor", ascending=False)
    fig = px.bar(ordenado, x="tipo", y="pct_valor", color_discrete_sequence=[COR])
    fig.update_traces(hovertemplate="%{x}<br>%{y:,.1f}%<extra></extra>")
    fig.update_yaxes(ticksuffix="%")
    return _layout(
        fig, "07 · Mix de pagamento", "Tipo de pagamento", "Valor pago (%)", ALTURA
    )


def ticket_por_uf(df):
    ordenado = df.sort_values(["ticket_medio", "uf"], ascending=[False, True])
    fig = px.bar(
        ordenado,
        x="ticket_medio",
        y="uf",
        orientation="h",
        color_discrete_sequence=[COR],
    )
    fig.update_traces(hovertemplate="%{y}<br>R$ %{x:,.2f}<extra></extra>")
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(tickprefix="R$ ", tickformat=",.0f")
    return _layout(
        fig,
        "06 · Ticket médio por UF",
        "Ticket médio (R$ por pedido)",
        "UF do cliente",
        ALTURA,
    )


def clientes_por_uf(df):
    ordenado = df.sort_values(["clientes", "uf"], ascending=[False, True])
    fig = px.bar(
        ordenado, x="clientes", y="uf", orientation="h", color_discrete_sequence=[COR]
    )
    fig.update_traces(hovertemplate="%{y}<br>%{x:,.0f} pessoas<extra></extra>")
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(tickformat=",.0f")
    return _layout(
        fig, "12 · Clientes por UF", "Clientes (pessoas)", "UF do cliente", ALTURA
    )


def nota_por_categoria(df):
    piores = df.sort_values(["posicao_pior", "categoria"]).head(10)
    fig = px.scatter(
        piores, x="nota_media", y="categoria", color_discrete_sequence=[COR]
    )
    fig.update_traces(
        marker_size=11, hovertemplate="%{y}<br>nota %{x:,.2f}<extra></extra>"
    )
    fig.update_yaxes(autorange="reversed")
    return _layout(
        fig,
        "04 · Nota por categoria (10 piores)",
        "Nota média (1 a 5)",
        "Categoria",
        ALTURA,
    )


def concentracao_vendedores(df):
    ordenado = df.sort_values("posicao")
    fig = px.line(
        ordenado, x="posicao", y="pct_acumulado", color_discrete_sequence=[COR]
    )
    fig.update_traces(
        hovertemplate="%{x:,.0f}º vendedor<br>%{y:,.2f}% da receita<extra></extra>"
    )
    fig.add_hline(y=80, line_dash="dash", line_color=COR)
    fig.update_xaxes(tickformat=",.0f")
    fig.update_yaxes(ticksuffix="%")
    return _layout(
        fig,
        "09 · Concentração de vendedores",
        "Vendedores (posição por receita)",
        "Receita acumulada (%)",
        ALTURA,
    )
