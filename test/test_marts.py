"""Testes de pipeline/marts.py (executor) e de sql/marts/01 e 03 sobre dado inventado."""

import io
import sys
from datetime import date
from decimal import Decimal

import duckdb
import pytest

from pipeline import db, marts, transformacao

# Os .sql de verdade do projeto, lidos antes de qualquer monkeypatch.
SQL_DO_PROJETO = marts.PASTA_SQL


def criar_refined(arquivo):
    """As oito tabelas de refined, vazias, com os nomes e tipos da transformação."""
    con = duckdb.connect(str(arquivo))
    con.execute("CREATE SCHEMA refined").complete()
    for tabela, colunas in transformacao.COLUNAS.items():
        definicao = ", ".join(
            f"{destino} {tipo or 'VARCHAR'}" for _, destino, tipo in colunas
        )
        con.execute(f"CREATE TABLE refined.{tabela} ({definicao})").complete()
    con.close()


def preparar(tmp_path, monkeypatch):
    """Banco com refined vazio e pasta sql/marts vazia, ambos em tmp_path."""
    monkeypatch.setattr(db, "ARQUIVO_BANCO", tmp_path / "olist.duckdb")
    criar_refined(tmp_path / "olist.duckdb")
    pasta = tmp_path / "sql" / "marts"
    pasta.mkdir(parents=True)
    monkeypatch.setattr(marts, "PASTA_PROJETO", tmp_path)
    monkeypatch.setattr(marts, "PASTA_SQL", pasta)
    return pasta


def tabelas_em_marts(tmp_path):
    con = duckdb.connect(str(tmp_path / "olist.duckdb"), read_only=True)
    try:
        linhas = con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'marts' ORDER BY 1"
        ).fetchall()
    finally:
        con.close()
    return [t for (t,) in linhas]


def executar(monkeypatch):
    """Roda marts.main() e devolve o que ele imprimiu."""
    saida = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    monkeypatch.setattr(sys, "stdout", saida)
    marts.main()
    saida.flush()
    return saida.buffer.getvalue().decode("utf-8")


# --- executor ------------------------------------------------------------------


def test_arquivo_com_select_1_cria_mart_com_uma_linha(tmp_path, monkeypatch):
    pasta = preparar(tmp_path, monkeypatch)
    (pasta / "00_teste.sql").write_text("SELECT 1 AS x", encoding="utf-8")

    texto = executar(monkeypatch)

    assert tabelas_em_marts(tmp_path) == ["teste"]
    assert "marts.teste" in texto
    assert texto.splitlines()[-1] == "1 marts, 1 linhas"


def test_arquivo_apagado_faz_o_mart_sumir(tmp_path, monkeypatch):
    pasta = preparar(tmp_path, monkeypatch)
    (pasta / "00_teste.sql").write_text("SELECT 1 AS x", encoding="utf-8")
    (pasta / "01_outro.sql").write_text("SELECT 2 AS y", encoding="utf-8")
    executar(monkeypatch)

    (pasta / "00_teste.sql").unlink()
    executar(monkeypatch)

    assert tabelas_em_marts(tmp_path) == ["outro"]


def test_arquivos_rodam_em_ordem_alfabetica(tmp_path, monkeypatch):
    pasta = preparar(tmp_path, monkeypatch)
    # O 02 lê o mart do 01: só funciona se o 01 rodar antes.
    (pasta / "01_base.sql").write_text("SELECT 7 AS x", encoding="utf-8")
    (pasta / "02_derivado.sql").write_text("SELECT x FROM marts.base", encoding="utf-8")

    executar(monkeypatch)

    assert tabelas_em_marts(tmp_path) == ["base", "derivado"]


def test_conteudo_tira_espacos_bom_e_um_ponto_e_virgula(tmp_path):
    arquivo = tmp_path / "01_a.sql"
    # BOM no início (PowerShell 5.1) e ";" com espaços no fim.
    arquivo.write_bytes(b"\xef\xbb\xbfSELECT 1 AS x ;  \n")

    assert marts.conteudo(arquivo) == "SELECT 1 AS x"


def test_rodar_duas_vezes_imprime_a_mesma_coisa(tmp_path, monkeypatch):
    pasta = preparar(tmp_path, monkeypatch)
    (pasta / "00_teste.sql").write_text("SELECT 1 AS x", encoding="utf-8")
    (pasta / "01_mil.sql").write_text("SELECT * FROM range(1000)", encoding="utf-8")

    primeira = executar(monkeypatch)
    segunda = executar(monkeypatch)

    assert primeira == segunda
    assert "1.000 linhas" in primeira  # milhar com ponto


def test_arquivo_sem_prefixo_para_antes_de_executar_qualquer_sql(tmp_path, monkeypatch):
    pasta = preparar(tmp_path, monkeypatch)
    (pasta / "01_valido.sql").write_text("SELECT 1 AS x", encoding="utf-8")
    (pasta / "teste.sql").write_text("SELECT 1 AS x", encoding="utf-8")

    with pytest.raises(SystemExit) as saida:
        marts.main()

    assert saida.value.code == 1
    # Nem o arquivo válido rodou: o schema marts nem chegou a ser criado.
    assert tabelas_em_marts(tmp_path) == []


def test_dois_arquivos_com_o_mesmo_nome_de_tabela_param(tmp_path, monkeypatch):
    pasta = preparar(tmp_path, monkeypatch)
    (pasta / "01_vendas.sql").write_text("SELECT 1 AS x", encoding="utf-8")
    # Maiúscula não diferencia identificador no DuckDB: seria a mesma tabela.
    (pasta / "02_Vendas.sql").write_text("SELECT 2 AS x", encoding="utf-8")

    with pytest.raises(SystemExit):
        marts.main()

    assert tabelas_em_marts(tmp_path) == []


def test_pasta_sem_sql_encerra(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)

    with pytest.raises(SystemExit) as saida:
        marts.main()

    assert saida.value.code == 1


def test_mart_vazio_encerra_e_deixa_marts_como_estava(tmp_path, monkeypatch):
    pasta = preparar(tmp_path, monkeypatch)
    (pasta / "00_teste.sql").write_text("SELECT 1 AS x", encoding="utf-8")
    executar(monkeypatch)
    # Mart novo sem linhas, como um JOIN que não casou.
    (pasta / "01_vazio.sql").write_text("SELECT 1 AS x WHERE false", encoding="utf-8")

    with pytest.raises(SystemExit) as saida:
        marts.main()

    assert saida.value.code == 1
    assert tabelas_em_marts(tmp_path) == ["teste"]


def test_sql_com_erro_encerra_e_deixa_marts_como_estava(tmp_path, monkeypatch):
    pasta = preparar(tmp_path, monkeypatch)
    (pasta / "00_teste.sql").write_text("SELECT 1 AS x", encoding="utf-8")
    executar(monkeypatch)
    (pasta / "01_quebrado.sql").write_text("SELEC 1", encoding="utf-8")  # sintaxe

    with pytest.raises(SystemExit) as saida:
        marts.main()

    assert saida.value.code == 1
    assert tabelas_em_marts(tmp_path) == ["teste"]


def test_refined_incompleto_encerra(tmp_path, monkeypatch):
    pasta = preparar(tmp_path, monkeypatch)
    (pasta / "00_teste.sql").write_text("SELECT 1 AS x", encoding="utf-8")
    con = duckdb.connect(str(tmp_path / "olist.duckdb"))
    con.execute("DROP TABLE refined.avaliacoes").complete()
    con.close()

    with pytest.raises(SystemExit) as saida:
        marts.main()

    assert saida.value.code == 1
    assert tabelas_em_marts(tmp_path) == []


# --- sql/marts/01 e 03 sobre tabelas inventadas --------------------------------


def rodar_mart(tmp_path, arquivo, pedidos, itens=()):
    """Cria refined com as linhas dadas e devolve o resultado do .sql do projeto."""
    criar_refined(tmp_path / "olist.duckdb")
    con = duckdb.connect(str(tmp_path / "olist.duckdb"))
    try:
        for linha in pedidos:
            con.execute(
                "INSERT INTO refined.pedidos (pedido_id, status, data_compra, "
                "data_entrega, data_entrega_prevista) VALUES (?, ?, ?, ?, ?)",
                linha,
            ).complete()
        for linha in itens:
            con.execute(
                "INSERT INTO refined.itens_pedido (pedido_id, item_seq, preco, frete) "
                "VALUES (?, ?, ?, ?)",
                linha,
            ).complete()
        return con.execute(marts.conteudo(SQL_DO_PROJETO / arquivo)).fetchall()
    finally:
        con.close()


def vendas(tmp_path, pedidos, itens):
    return rodar_mart(tmp_path, "01_vendas_mensais.sql", pedidos, itens)


def entrega(tmp_path, pedidos):
    return rodar_mart(tmp_path, "03_entrega_no_prazo.sql", pedidos)


def test_pedido_com_dois_itens_conta_uma_vez(tmp_path):
    linhas = vendas(
        tmp_path,
        [("p1", "delivered", "2018-01-10 10:00:00", None, None)],
        [
            ("p1", 1, Decimal("10.00"), Decimal("3.00")),  # dois itens no mesmo
            ("p1", 2, Decimal("20.00"), Decimal("3.00")),  # pedido
        ],
    )

    assert linhas == [(date(2018, 1, 1), 1, Decimal("30.00"))]


def test_receita_e_so_preco_sem_frete(tmp_path):
    linhas = vendas(
        tmp_path,
        [("p1", "delivered", "2018-01-10 10:00:00", None, None)],
        [("p1", 1, Decimal("10.00"), Decimal("99.99"))],  # frete alto, fica fora
    )

    assert linhas[0][2] == Decimal("10.00")


def test_cancelado_fica_fora_da_receita(tmp_path):
    linhas = vendas(
        tmp_path,
        [
            ("p1", "delivered", "2018-01-10 10:00:00", None, None),
            ("p2", "canceled", "2018-01-11 10:00:00", None, None),  # fora
            ("p3", "unavailable", "2018-01-12 10:00:00", None, None),  # fora
        ],
        [
            ("p1", 1, Decimal("10.00"), Decimal("0.00")),
            ("p2", 1, Decimal("500.00"), Decimal("0.00")),
            ("p3", 1, Decimal("700.00"), Decimal("0.00")),
        ],
    )

    assert linhas == [(date(2018, 1, 1), 1, Decimal("10.00"))]


def test_pedidos_do_mesmo_mes_viram_uma_linha(tmp_path):
    linhas = vendas(
        tmp_path,
        [
            ("p1", "delivered", "2018-01-01 00:00:00", None, None),  # primeiro instante
            ("p2", "shipped", "2018-01-31 23:59:59", None, None),  # último instante
            ("p3", "delivered", "2018-02-01 00:00:00", None, None),  # mês seguinte
        ],
        [
            ("p1", 1, Decimal("1.00"), Decimal("0.00")),
            ("p2", 1, Decimal("2.00"), Decimal("0.00")),
            ("p3", 1, Decimal("4.00"), Decimal("0.00")),
        ],
    )

    assert linhas == [
        (date(2018, 1, 1), 2, Decimal("3.00")),
        (date(2018, 2, 1), 1, Decimal("4.00")),
    ]


def test_entrega_no_dia_previsto_a_tarde_esta_no_prazo(tmp_path):
    linhas = entrega(
        tmp_path,
        # Chegou às 15h do dia previsto: compara data com data, está no prazo.
        [
            (
                "p1",
                "delivered",
                "2018-01-10 10:00:00",
                "2018-01-20 15:00:00",
                "2018-01-20",
            )
        ],
    )

    assert linhas == [(1, 1, 0, 100.0)]


def test_entrega_no_dia_seguinte_esta_atrasada(tmp_path):
    linhas = entrega(
        tmp_path,
        [
            (
                "p1",
                "delivered",
                "2018-01-10 10:00:00",
                "2018-01-20 15:00:00",
                "2018-01-20",
            ),
            # Um dia depois do previsto, logo depois da meia-noite: atrasado.
            (
                "p2",
                "delivered",
                "2018-01-10 10:00:00",
                "2018-01-21 00:01:00",
                "2018-01-20",
            ),
        ],
    )

    assert linhas == [(2, 1, 1, 50.0)]


def test_so_delivered_com_data_entra_no_denominador(tmp_path):
    linhas = entrega(
        tmp_path,
        [
            (
                "p1",
                "delivered",
                "2018-01-10 10:00:00",
                "2018-01-12 10:00:00",
                "2018-01-20",
            ),
            ("p2", "delivered", "2018-01-10 10:00:00", None, "2018-01-20"),  # sem data
            ("p3", "shipped", "2018-01-10 10:00:00", None, "2018-01-20"),  # a caminho
            ("p4", "canceled", "2018-01-10 10:00:00", None, "2018-01-20"),  # cancelado
        ],
    )

    assert linhas == [(1, 1, 0, 100.0)]
