"""Acesso ao olist.duckdb, compartilhado pelas etapas do pipeline.

PASTA_RAW                          Path da pasta com os nove .csv.gz
conectar()                         abre o olist.duckdb, criando se faltar
criar_schema(con, nome)            CREATE SCHEMA IF NOT EXISTS
gravar(con, df, schema, tabela)    grava e devolve a contagem lida do banco
"""

from pathlib import Path

import duckdb
import pandas as pd

PASTA_PROJETO = Path(__file__).resolve().parent.parent
PASTA_RAW = PASTA_PROJETO / "raw"
ARQUIVO_BANCO = PASTA_PROJETO / "olist.duckdb"


def conectar() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(ARQUIVO_BANCO))


def criar_schema(con: duckdb.DuckDBPyConnection, nome: str) -> None:
    # DuckDB 2.0 exige consumir o resultado antes do próximo comando na conexão.
    con.execute(f'CREATE SCHEMA IF NOT EXISTS "{nome}"').complete()


def gravar(
    con: duckdb.DuckDBPyConnection, df: pd.DataFrame, schema: str, tabela: str
) -> int:
    # CREATE OR REPLACE: reexecutar recria a tabela em vez de acrescentar linhas.
    con.register("_df_gravar", df)
    try:
        con.execute(
            f'CREATE OR REPLACE TABLE "{schema}"."{tabela}" AS SELECT * FROM _df_gravar'
        ).complete()
    finally:
        con.unregister("_df_gravar")
    # A contagem vem do banco, não do DataFrame: confere o que foi gravado de fato.
    # fetchall e não fetchone, que deixaria o resultado aberto na conexão.
    return con.execute(f'SELECT count(*) FROM "{schema}"."{tabela}"').fetchall()[0][0]
