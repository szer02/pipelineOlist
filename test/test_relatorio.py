"""Testes de relatorio.py: marts inventados num olist.duckdb dentro de tmp_path."""

from datetime import datetime

import duckdb
import pandas as pd
import pytest

import painel
import relatorio

# Um SELECT por mart que o relatório lê, com as colunas e os tipos dos marts
# de verdade e valores escolhidos para a conta ser feita de cabeça.
MARTS = {
    "kpis": """
        SELECT 100.5::DOUBLE AS ticket_medio, 80.0::DOUBLE AS ticket_mediana,
               12.3::DOUBLE AS pct_frete, 1.25::DOUBLE AS pct_cancelados,
               9.5::DOUBLE AS dias_entrega, 8.0::DOUBLE AS dias_entrega_mediana,
               4.25::DOUBLE AS nota_media""",
    # 90% compraram uma vez: o cartão de recompra tem que dar 10,00%.
    "recompra": """
        SELECT * FROM (VALUES (1, 90, 90.0::DOUBLE), (2, 10, 10.0::DOUBLE))
            AS t(pedidos_por_cliente, clientes, pct_clientes)""",
    "entrega_no_prazo": """
        SELECT 4 AS entregues, 3.0::DOUBLE AS no_prazo, 1.0::DOUBLE AS atrasados,
               75.0::DOUBLE AS pct_no_prazo""",
    # Um mês antes e um depois do período padrão (jan/2017 a ago/2018).
    "vendas_mensais": """
        SELECT * FROM (VALUES
            (DATE '2016-12-01', 1, 10.0::DOUBLE),
            (DATE '2017-01-01', 2, 20.0::DOUBLE),
            (DATE '2018-08-01', 3, 30.0::DOUBLE),
            (DATE '2018-09-01', 4, 40.0::DOUBLE)
        ) AS t(mes, pedidos, receita)""",
    "top_categorias": """
        SELECT * FROM (VALUES ('a', 1, 1, 10.0::DOUBLE), ('b', 2, 2, 20.0::DOUBLE))
            AS t(categoria, pedidos, itens, receita)""",
    "mix_pagamento": """
        SELECT * FROM (VALUES ('boleto', 1, 1, 25.0::DOUBLE, 25.0::DOUBLE),
                              ('credit_card', 3, 3, 75.0::DOUBLE, 75.0::DOUBLE))
            AS t(tipo, pagamentos, pedidos, valor, pct_valor)""",
    "ticket_medio_por_estado": """
        SELECT * FROM (VALUES ('SP', 2, 50.0::DOUBLE), ('RJ', 1, 70.0::DOUBLE))
            AS t(uf, pedidos, ticket_medio)""",
    "clientes_por_uf": """
        SELECT * FROM (VALUES ('SP', 5), ('RJ', 2)) AS t(uf, clientes)""",
    "nota_por_categoria": """
        SELECT * FROM (VALUES ('a', 100, 3.5::DOUBLE, 1), ('b', 120, 4.5::DOUBLE, 2))
            AS t(categoria, pedidos_avaliados, nota_media, posicao_pior)""",
    "vendedores_pareto": """
        SELECT * FROM (VALUES ('v1', 'SP', 80.0::DOUBLE, 1, 80.0::DOUBLE),
                              ('v2', 'RJ', 20.0::DOUBLE, 2, 100.0::DOUBLE))
            AS t(vendedor_id, uf, receita, posicao, pct_acumulado)""",
}

CARTOES = ["R$ 100,50", "1,25%", "12,3%", "10,00%", "75,0%", "9,5", "4,25"]


class Relogio:
    """Substitui datetime em relatorio.py para o rodapé ter hora conhecida."""

    def __init__(self, instante):
        self.instante = instante

    def now(self):
        return self.instante


def preparar(tmp_path, monkeypatch, sem=()):
    # chdir: painel.ARQUIVO e relatorio.SAIDA são caminhos relativos à pasta atual.
    monkeypatch.chdir(tmp_path)
    con = duckdb.connect(str(tmp_path / "olist.duckdb"))
    con.execute("CREATE SCHEMA marts").complete()
    for nome, sql in MARTS.items():
        if nome not in sem:
            con.execute(f"CREATE TABLE marts.{nome} AS {sql}").complete()
    con.close()


def gerar(monkeypatch, instante):
    monkeypatch.setattr(relatorio, "datetime", Relogio(instante))
    relatorio.main()
    return relatorio.SAIDA.read_text(encoding="utf-8")


def test_gera_o_arquivo_dentro_da_pasta_atual(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)

    gerar(monkeypatch, datetime(2026, 1, 5, 9, 7))

    assert (tmp_path / "relatorio.html").is_file()


def test_mostra_os_sete_cartoes_formatados(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)

    html = gerar(monkeypatch, datetime(2026, 1, 5, 9, 7))

    valores = [
        trecho.split("</div>")[0] for trecho in html.split('<div class="valor">')[1:]
    ]
    assert valores == CARTOES


def test_rodape_diz_quando_o_arquivo_foi_gerado(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)

    html = gerar(monkeypatch, datetime(2026, 1, 5, 9, 7))

    assert "<footer>Dados de 05/01/2026 09:07</footer>" in html


def test_rodar_duas_vezes_muda_so_o_rodape(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)

    primeira = gerar(monkeypatch, datetime(2026, 1, 5, 9, 7)).splitlines()
    segunda = gerar(monkeypatch, datetime(2026, 1, 6, 18, 30)).splitlines()

    diferentes = [(a, b) for a, b in zip(primeira, segunda) if a != b]
    assert len(primeira) == len(segunda)
    assert diferentes == [
        (
            "<footer>Dados de 05/01/2026 09:07</footer>",
            "<footer>Dados de 06/01/2026 18:30</footer>",
        )
    ]


def test_plotly_vem_do_cdn_uma_vez_e_cada_grafico_tem_id_fixo(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)

    html = gerar(monkeypatch, datetime(2026, 1, 5, 9, 7))

    assert html.count("cdn.plot.ly") == 1
    for div_id in ["g01", "g02", "g07", "g06", "g12", "g04", "g09"]:
        assert f'id="{div_id}"' in html
    # O primeiro gráfico (com a biblioteca) vem antes de todos os outros.
    assert html.index("cdn.plot.ly") < html.index('id="g02"')


def test_faturamento_mostra_so_jan2017_a_ago2018_e_diz_o_periodo(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)
    dados = painel.ler(relatorio.MARTS)

    div_id, figura = relatorio.graficos(dados)[0]

    assert div_id == "g01"
    # A figura guarda o eixo como numpy.datetime64; pd.Timestamp dá .month e .year.
    meses = [painel.mes(pd.Timestamp(m)) for m in figura.data[0].x]
    assert meses == ["jan/2017", "ago/2018"]
    assert "jan/2017 a ago/2018" in figura.layout.title.text


def test_sem_o_banco_encerra(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as saida:
        relatorio.main()

    assert saida.value.code == 1
    assert not (tmp_path / "relatorio.html").exists()


def test_mart_faltando_encerra_sem_escrever_o_arquivo(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, sem=("kpis",))

    with pytest.raises(SystemExit) as saida:
        relatorio.main()

    assert saida.value.code == 1
    assert not (tmp_path / "relatorio.html").exists()
