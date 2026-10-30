"""Testes de pipeline/db.py: conectar, criar_schema e gravar num DuckDB em tmp_path."""

import pandas as pd

from pipeline import db


def test_conectar_cria_o_banco_no_caminho_configurado(tmp_path, monkeypatch):
    arquivo = tmp_path / "teste.duckdb"
    monkeypatch.setattr(db, "ARQUIVO_BANCO", arquivo)

    con = db.conectar()
    con.close()

    assert arquivo.is_file()


def test_criar_schema_duas_vezes_nao_falha(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "ARQUIVO_BANCO", tmp_path / "teste.duckdb")
    con = db.conectar()

    db.criar_schema(con, "raw")
    db.criar_schema(con, "raw")  # IF NOT EXISTS: a segunda chamada não pode quebrar
    schemas = con.execute(
        "SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'raw'"
    ).fetchall()[0][0]
    con.close()

    assert schemas == 1


def test_gravar_devolve_a_contagem_do_banco(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "ARQUIVO_BANCO", tmp_path / "teste.duckdb")
    con = db.conectar()
    db.criar_schema(con, "raw")
    df = pd.DataFrame({"a": ["1", "2", "3"]})  # três linhas quaisquer

    contagem = db.gravar(con, df, "raw", "t")
    no_banco = con.execute("SELECT count(*) FROM raw.t").fetchall()[0][0]
    con.close()

    assert contagem == 3
    assert no_banco == 3


def test_gravar_de_novo_substitui_em_vez_de_acrescentar(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "ARQUIVO_BANCO", tmp_path / "teste.duckdb")
    con = db.conectar()
    db.criar_schema(con, "raw")

    db.gravar(con, pd.DataFrame({"a": ["1", "2", "3"]}), "raw", "t")
    # Segunda gravação com duas linhas: CREATE OR REPLACE deixa só estas duas.
    contagem = db.gravar(con, pd.DataFrame({"a": ["x", "y"]}), "raw", "t")
    valores = con.execute("SELECT a FROM raw.t ORDER BY a").fetchall()
    con.close()

    assert contagem == 2
    assert valores == [("x",), ("y",)]
