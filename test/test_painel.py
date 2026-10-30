"""Testes de painel.py: formato, leitura de um banco em tmp_path e gráficos."""

from datetime import date
from decimal import Decimal

import duckdb
import pandas as pd
import pytest

import painel

# --- formato -------------------------------------------------------------------


def test_reais_tem_milhar_com_ponto_e_decimal_com_virgula():
    assert painel.reais(1234567.891) == "R$ 1.234.567,89"
    assert painel.reais(0) == "R$ 0,00"
    assert painel.reais(Decimal("10.5")) == "R$ 10,50"  # o que vem de DECIMAL
    assert painel.reais(1500, casas=0) == "R$ 1.500"


def test_pct_tem_uma_casa_por_padrao():
    assert painel.pct(12.5) == "12,5%"
    assert painel.pct(7, 2) == "7,00%"
    assert painel.pct(1234.25, 2) == "1.234,25%"


def test_numero_nao_tem_casa_por_padrao():
    assert painel.numero(1234567) == "1.234.567"
    assert painel.numero(999) == "999"
    assert painel.numero(3.25, 1) == "3,2"  # 3,25 arredonda pelo format do Python
    assert painel.numero(4.5, 2) == "4,50"


def test_mes_escreve_o_nome_em_portugues():
    assert painel.mes(date(2017, 1, 1)) == "jan/2017"
    assert painel.mes(pd.Timestamp("2018-12-01")) == "dez/2018"


# --- leitura -------------------------------------------------------------------


def banco_com_um_mart(tmp_path, monkeypatch):
    monkeypatch.setattr(painel, "ARQUIVO", str(tmp_path / "olist.duckdb"))
    con = duckdb.connect(str(tmp_path / "olist.duckdb"))
    con.execute("CREATE SCHEMA marts").complete()
    con.execute("CREATE TABLE marts.a AS SELECT 1 AS x UNION ALL SELECT 2").complete()
    con.close()


def test_ler_devolve_um_dataframe_por_mart(tmp_path, monkeypatch):
    banco_com_um_mart(tmp_path, monkeypatch)

    dados = painel.ler(["a"])

    assert list(dados) == ["a"]
    assert sorted(dados["a"]["x"]) == [1, 2]


def test_ler_deixa_de_fora_o_mart_que_nao_existe(tmp_path, monkeypatch):
    banco_com_um_mart(tmp_path, monkeypatch)

    dados = painel.ler(["a", "nao_existe"])

    assert list(dados) == ["a"]


def test_ler_sem_o_arquivo_levanta_file_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr(painel, "ARQUIVO", str(tmp_path / "olist.duckdb"))

    with pytest.raises(FileNotFoundError):
        painel.ler(["a"])

    # read_only não cria o arquivo vazio.
    assert not (tmp_path / "olist.duckdb").exists()


def test_ler_fecha_a_conexao_e_libera_o_arquivo_para_gravar(tmp_path, monkeypatch):
    banco_com_um_mart(tmp_path, monkeypatch)
    painel.ler(["a"])

    # Com a conexão read_only ainda aberta, o DuckDB recusaria abrir o mesmo
    # arquivo com outra configuração no mesmo processo.
    con = duckdb.connect(str(tmp_path / "olist.duckdb"))
    con.execute("CREATE TABLE marts.b AS SELECT 1 AS y").complete()
    con.close()

    assert list(painel.ler(["b"])) == ["b"]


# --- gráficos ------------------------------------------------------------------

# Um DataFrame inventado por gráfico, com as colunas do mart que ele lê.
MESES = pd.DataFrame(
    {
        "mes": pd.to_datetime(["2017-01-01", "2017-02-01", "2017-03-01"]),
        "pedidos": [10, 20, 30],
        "receita": [100.0, 250.0, 175.5],
    }
)
CATEGORIAS = pd.DataFrame(
    {
        "categoria": ["a", "b", "c", "d"],
        "pedidos": [1, 2, 3, 4],
        "itens": [1, 2, 3, 4],
        "receita": [50.0, 400.0, 10.0, 90.0],  # fora de ordem de propósito
    }
)
PAGAMENTOS = pd.DataFrame(
    {
        "tipo": ["boleto", "credit_card"],
        "pagamentos": [5, 15],
        "pedidos": [5, 14],
        "valor": [250.0, 750.0],
        "pct_valor": [25.0, 75.0],
    }
)
TICKETS = pd.DataFrame(
    {
        "uf": ["SP", "PB", "RJ"],
        "pedidos": [9, 2, 4],
        "ticket_medio": [80.0, 210.0, 120.0],
    }
)
CLIENTES = pd.DataFrame({"uf": ["RJ", "SP"], "clientes": [30, 70]})
NOTAS = pd.DataFrame(
    {
        "categoria": ["x", "y", "z"],
        "pedidos_avaliados": [100, 200, 300],
        "nota_media": [4.5, 3.1, 3.9],
        "posicao_pior": [3, 1, 2],
    }
)
VENDEDORES = pd.DataFrame(
    {
        "vendedor_id": ["v1", "v2", "v3", "v4"],
        "uf": ["SP", "SP", "RJ", "MG"],
        "receita": [50.0, 30.0, 15.0, 5.0],
        "posicao": [1, 2, 3, 4],
        "pct_acumulado": [50.0, 80.0, 95.0, 100.0],
    }
)

GRAFICOS = [
    (painel.faturamento_mensal, MESES, "01 ·"),
    (painel.receita_por_categoria, CATEGORIAS, "02 ·"),
    (painel.mix_pagamento, PAGAMENTOS, "07 ·"),
    (painel.ticket_por_uf, TICKETS, "06 ·"),
    (painel.clientes_por_uf, CLIENTES, "12 ·"),
    (painel.nota_por_categoria, NOTAS, "04 ·"),
    (painel.concentracao_vendedores, VENDEDORES, "09 ·"),
]


@pytest.mark.parametrize("funcao, df, numero", GRAFICOS)
def test_grafico_tem_um_ponto_por_linha_do_dataframe(funcao, df, numero):
    figura = funcao(df)

    assert len(figura.data) == 1
    assert len(figura.data[0].x) == len(df)
    assert len(figura.data[0].y) == len(df)


@pytest.mark.parametrize("funcao, df, numero", GRAFICOS)
def test_grafico_tem_o_numero_do_mart_no_titulo_e_uma_cor_so(funcao, df, numero):
    figura = funcao(df)

    assert figura.layout.title.text.startswith(numero)
    assert (
        figura.data[0].marker.color == painel.COR
        or figura.data[0].line.color == painel.COR
    )
    assert figura.layout.xaxis.title.text
    assert figura.layout.yaxis.title.text


def test_receita_por_categoria_mostra_dez_com_a_maior_primeiro():
    # Doze categorias com receita 1..12: ficam as dez maiores, de 12 a 3.
    doze = pd.DataFrame(
        {
            "categoria": [f"cat{n:02d}" for n in range(1, 13)],
            "pedidos": range(1, 13),
            "itens": range(1, 13),
            "receita": [float(n) for n in range(1, 13)],
        }
    )

    figura = painel.receita_por_categoria(doze)

    assert list(figura.data[0].y) == [f"cat{n:02d}" for n in range(12, 2, -1)]
    assert figura.layout.yaxis.autorange == "reversed"  # primeira linha em cima


def test_nota_por_categoria_mostra_as_dez_piores_com_a_pior_primeiro():
    doze = pd.DataFrame(
        {
            "categoria": [f"cat{n:02d}" for n in range(1, 13)],
            "pedidos_avaliados": [100] * 12,
            "nota_media": [3.0 + n / 10 for n in range(1, 13)],
            "posicao_pior": list(range(12, 0, -1)),  # cat12 é a pior
        }
    )

    figura = painel.nota_por_categoria(doze)

    assert list(figura.data[0].y) == [f"cat{n:02d}" for n in range(12, 2, -1)]


def test_ticket_por_uf_poe_o_maior_em_cima():
    figura = painel.ticket_por_uf(TICKETS)

    assert list(figura.data[0].y) == ["PB", "RJ", "SP"]
    assert figura.layout.yaxis.autorange == "reversed"


def test_concentracao_de_vendedores_tem_linha_tracejada_em_80():
    figura = painel.concentracao_vendedores(VENDEDORES)

    linha = figura.layout.shapes[0]
    assert (linha.y0, linha.y1) == (80, 80)
    assert linha.line.dash == "dash"
