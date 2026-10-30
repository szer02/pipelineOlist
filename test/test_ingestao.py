"""Testes de pipeline/ingestao.py com .csv.gz pequenos escritos em tmp_path."""

import gzip

import duckdb
import pytest

from pipeline import db, ingestao


def escrever_csv(pasta, nome, texto):
    with gzip.open(pasta / nome, "wt", encoding="utf-8", newline="") as f:
        f.write(texto)


def preparar(tmp_path, monkeypatch):
    """Pasta raw com os nove arquivos (cabeçalho e uma linha) e banco em tmp_path."""
    pasta = tmp_path / "raw"
    pasta.mkdir()
    for arquivo in ingestao.ARQUIVOS:
        escrever_csv(pasta, arquivo, "id\nqualquer\n")
    monkeypatch.setattr(ingestao, "PASTA_RAW", pasta)
    monkeypatch.setattr(db, "ARQUIVO_BANCO", tmp_path / "olist.duckdb")
    return pasta


def consultar(tmp_path, sql):
    con = duckdb.connect(str(tmp_path / "olist.duckdb"), read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_formatar_separa_milhar_com_ponto():
    assert ingestao.formatar(1234567) == "1.234.567"
    assert ingestao.formatar(12) == "12"


def test_csv_vira_tabela_com_as_mesmas_linhas(tmp_path, monkeypatch):
    pasta = preparar(tmp_path, monkeypatch)
    escrever_csv(
        pasta,
        "olist_orders_dataset.csv.gz",
        "order_id,order_status\n"
        "p1,delivered\n"  # pedido comum
        "p2,canceled\n"  # outro status, para ver que nada é filtrado
        "p2,canceled\n",  # linha repetida: raw não deduplica
    )

    ingestao.main()

    linhas = consultar(tmp_path, "SELECT * FROM raw.pedidos ORDER BY ALL")
    assert linhas == [("p1", "delivered"), ("p2", "canceled"), ("p2", "canceled")]


def test_cada_arquivo_vira_a_tabela_do_mapa(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)

    ingestao.main()

    tabelas = consultar(
        tmp_path,
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'raw' ORDER BY 1",
    )
    assert [t for (t,) in tabelas] == sorted(ingestao.ARQUIVOS.values())


def test_toda_coluna_entra_como_texto_e_cep_mantem_zero(tmp_path, monkeypatch):
    pasta = preparar(tmp_path, monkeypatch)
    escrever_csv(
        pasta,
        "olist_customers_dataset.csv.gz",
        "customer_zip_code_prefix,valor\n"
        "01310,10.50\n",  # CEP com zero à esquerda e um número com casas
    )

    ingestao.main()

    tipos = consultar(
        tmp_path,
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_schema = 'raw' AND table_name = 'clientes'",
    )
    linhas = consultar(tmp_path, "SELECT * FROM raw.clientes")
    assert {t for (t,) in tipos} == {"VARCHAR"}
    assert linhas == [("01310", "10.50")]


def test_campo_vazio_vira_nulo_e_texto_na_continua_texto(tmp_path, monkeypatch):
    pasta = preparar(tmp_path, monkeypatch)
    escrever_csv(
        pasta,
        "olist_products_dataset.csv.gz",
        "product_id,categoria\n"
        "a,\n"  # categoria vazia: tem que virar nulo
        "b,NA\n",  # o texto "NA" não é nulo, é o que chegou
    )

    ingestao.main()

    linhas = consultar(tmp_path, "SELECT * FROM raw.produtos ORDER BY product_id")
    assert linhas == [("a", None), ("b", "NA")]


def test_reexecutar_nao_acrescenta_linhas(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)

    ingestao.main()
    ingestao.main()

    assert consultar(tmp_path, "SELECT count(*) FROM raw.pedidos") == [(1,)]


def test_arquivo_faltando_encerra_sem_criar_o_banco(tmp_path, monkeypatch):
    pasta = preparar(tmp_path, monkeypatch)
    (pasta / "olist_sellers_dataset.csv.gz").unlink()

    with pytest.raises(SystemExit) as saida:
        ingestao.main()

    assert saida.value.code == 1
    # A checagem vem antes de abrir o banco: nada foi ingerido.
    assert not (tmp_path / "olist.duckdb").exists()
