"""Relatório HTML do painel Olist: uma foto estática da página do app.py.

Execução:  uv run python relatorio.py

A spec do painel (docstring de painel.py) continua valendo aqui: só
SELECT * nos marts, nenhum cálculo sobre os números, formato brasileiro sem
locale do sistema.

SPEC

1. Reaproveitamento
   Lê os marts com painel.ler(), formata com painel.reais/pct/numero e monta
   os gráficos com as mesmas funções de painel.py. Não importa streamlit e
   não desenha nenhum gráfico que não esteja em painel.py.
   Por quê: o relatório é a mesma tela em outro meio. Se o número ou o
   gráfico mudar, muda num lugar só e sai igual nos dois.

2. Saída
   Escreve relatorio.html na raiz: um arquivo só, com as mesmas quatro faixas
   do app.py, na mesma ordem. Cartões em HTML simples, numa grade. Gráficos
   com figura.to_html(full_html=False); a biblioteca do plotly vem do CDN uma
   vez só, no primeiro gráfico (include_plotlyjs="cdn"), e nos outros
   include_plotlyjs=False. Cada gráfico com div_id fixo ("g01", "g02"...).
   Por quê: um arquivo só abre com dois cliques e anda por e-mail. A
   biblioteca do CDN mantém o arquivo pequeno, e carregá-la uma vez basta
   para todos os gráficos. Sem div_id fixo o plotly sorteia um id novo a cada
   execução, e o arquivo muda sem o dado mudar.

3. Período
   Sem filtro: o faturamento mostra o mesmo período padrão do app.py,
   jan/2017 a ago/2018, e o título do gráfico diz o período.
   Por quê: arquivo estático não tem controle de filtro; quem lê precisa
   saber que recorte está vendo.

4. Rodapé
   Data e hora em que o arquivo foi gerado: "Dados de 25/10/2026 14:03".
   Por quê: o arquivo não fala com o banco; quem lê precisa saber de quando
   é o número.

5. Tela
   Imprime o caminho do arquivo e o tamanho em KB. stdout em utf-8.
   Por quê: o Prompt de Comando do Windows embaralha acento por padrão.
"""

import html
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

import painel

SAIDA = Path("relatorio.html")

# Os mesmos marts e o mesmo período padrão do app.py.
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
INICIO = pd.Timestamp("2017-01-01")
FIM = pd.Timestamp("2018-08-01")

ESTILO = """
body { font-family: system-ui, sans-serif; margin: 24px; color: #222; background: #fff; }
h1 { margin: 0 0 4px; }
.nota { color: #666; font-size: .9rem; margin: 0 0 20px; }
.cartoes { display: grid; grid-template-columns: repeat(7, 1fr); gap: 12px; margin-bottom: 16px; }
.cartao { border: 1px solid #ddd; border-radius: 8px; padding: 12px; }
.rotulo { font-size: .85rem; color: #555; }
.valor { font-size: 1.6rem; margin-top: 6px; }
.tres { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.tres > div { min-width: 0; }
footer { color: #666; font-size: .85rem; margin-top: 24px; }
@media (max-width: 900px) {
  .cartoes { grid-template-columns: repeat(2, 1fr); }
  .tres { grid-template-columns: 1fr; }
}
"""


def erro(mensagem):
    print(mensagem)
    sys.exit(1)


def cartoes(dados):
    kpis = dados["kpis"].iloc[0]
    recompra = dados["recompra"]
    um_pedido = recompra[recompra["pedidos_por_cliente"] == 1].iloc[0]
    entrega = dados["entrega_no_prazo"].iloc[0]
    return [
        (
            "Ticket médio · receita por pedido válido",
            painel.reais(kpis["ticket_medio"]),
        ),
        ("Cancelados · % de todos os pedidos", painel.pct(kpis["pct_cancelados"], 2)),
        ("Peso do frete · % de itens + frete", painel.pct(kpis["pct_frete"], 1)),
        # A mesma exceção do app.py: o mart 05 guarda o complemento (quem comprou uma vez só).
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


def graficos(dados):
    """Lista (div_id, figura) na ordem das faixas 2, 3 e 4 do app.py."""
    vendas = dados["vendas_mensais"].sort_values("mes")
    vendas = vendas[(vendas["mes"] >= INICIO) & (vendas["mes"] <= FIM)]
    faturamento = painel.faturamento_mensal(vendas)
    faturamento.update_layout(
        title_text=f"01 · Faturamento mensal · {painel.mes(INICIO)} a {painel.mes(FIM)}"
    )
    # div_id com o número do mart, como no título do gráfico.
    return [
        ("g01", faturamento),
        ("g02", painel.receita_por_categoria(dados["top_categorias"])),
        ("g07", painel.mix_pagamento(dados["mix_pagamento"])),
        ("g06", painel.ticket_por_uf(dados["ticket_medio_por_estado"])),
        ("g12", painel.clientes_por_uf(dados["clientes_por_uf"])),
        ("g04", painel.nota_por_categoria(dados["nota_por_categoria"])),
        ("g09", painel.concentracao_vendedores(dados["vendedores_pareto"])),
    ]


def montar(dados, gerado_em):
    blocos = [
        figura.to_html(
            full_html=False,
            include_plotlyjs="cdn" if i == 0 else False,
            div_id=div_id,
        )
        for i, (div_id, figura) in enumerate(graficos(dados))
    ]
    faixa1 = "\n".join(
        f'<div class="cartao"><div class="rotulo">{html.escape(rotulo)}</div>'
        f'<div class="valor">{html.escape(valor)}</div></div>'
        for rotulo, valor in cartoes(dados)
    )
    faixa3 = "\n".join(f"<div>{b}</div>" for b in blocos[1:4])
    faixa4 = "\n".join(f"<div>{b}</div>" for b in blocos[4:7])
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Olist · visão da operação</title>
<style>{ESTILO}</style>
</head>
<body>
<h1>Olist · visão da operação</h1>
<p class="nota">Os cartões e os gráficos valem para o período inteiro; só o faturamento mensal
mostra {painel.mes(INICIO)} a {painel.mes(FIM)}.</p>
<section class="cartoes">
{faixa1}
</section>
<section>
{blocos[0]}
</section>
<section class="tres">
{faixa3}
</section>
<section class="tres">
{faixa4}
</section>
<footer>Dados de {gerado_em:%d/%m/%Y %H:%M}</footer>
</body>
</html>
"""


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        dados = painel.ler(MARTS)
    except FileNotFoundError:
        erro(
            "Não encontrei o olist.duckdb na pasta do projeto. Rode: uv run python -m pipeline.marts"
        )
    faltando = [nome for nome in MARTS if nome not in dados]
    if faltando:
        erro(
            "Faltam marts no banco: "
            + ", ".join(f"marts.{nome}" for nome in faltando)
            + ". Rode: uv run python -m pipeline.marts"
        )

    SAIDA.write_text(montar(dados, datetime.now()), encoding="utf-8")
    tamanho = SAIDA.stat().st_size / 1024
    print(f"{SAIDA.resolve()}  {painel.numero(tamanho, 1)} KB")


if __name__ == "__main__":
    main()
