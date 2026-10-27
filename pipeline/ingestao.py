"""Etapa 1 do pipeline Olist: copia os nove .csv.gz para o schema raw do DuckDB.

Execução:  uv run python -m pipeline.ingestao

SPEC

1. Escopo e nomes
   Schema de destino: raw. Cada arquivo vira uma tabela com nome em português
   (mapa ARQUIVOS abaixo, completo e literal).
   Por quê: é o vocabulário que vai ser digitado de memória nos JOINs das
   próximas etapas.

2. Proibições
   Nenhuma conversão de tipo, nenhuma linha descartada ou deduplicada, nenhum
   nome de coluna alterado, nenhum valor corrigido, preenchido ou normalizado.
   Data continua texto, nulo continua nulo.
   Por quê: a fronteira entre "o dado que chegou" e "o dado que eu decidi"
   precisa existir em algum lugar, e esse lugar é a passagem de raw para
   refined (etapa 2). Corrigir aqui apaga a fronteira.

3. Reexecução
   Cada tabela é recriada (CREATE OR REPLACE), nunca acrescentada.
   Por quê: rodar dez vezes dá o mesmo resultado que rodar uma, então errar e
   rodar de novo não tem custo.

4. Leitura do arquivo
   encoding utf-8 declarado, nunca adivinhado. Os .csv.gz são lidos direto,
   sem descompactar. Campo vazio vira nulo, não string vazia.
   Por quê: encoding adivinhado muda de máquina para máquina e embaralha
   acento sem erro. Nulo e string vazia são coisas diferentes, e a etapa 2
   precisa saber qual chegou.

5. Tipagem
   Toda coluna entra como texto (dtype=str), inferência desligada.
   Por quê: a inferência lê CEP com zero à esquerda como número e o zero some
   sem aviso. Converter tipo é decisão da etapa 2, onde fica registrada.

6. Saída na tela
   Uma linha por tabela, com nome qualificado e contagem vinda do banco (não
   do DataFrame), milhar separado por ponto, e uma linha final com o total.
   stdout reconfigurado para utf-8.
   Por quê: essa saída é o único instrumento de conferência desta etapa, e a
   contagem do banco é a que prova que o dado foi gravado. O Prompt de Comando
   do Windows embaralha acento por padrão.

7. Erro
   Antes de abrir o banco, verifica se os nove arquivos existem. Faltando
   algum: lista os que faltam, diz em que pasta procurou e sai com
   sys.exit(1), sem ingerir nada.
   Por quê: ingerir oito de nove tabelas em silêncio produz um dashboard
   errado que parece certo.

Este módulo não importa ui.py: a ingestão não sobe servidor, não abre
navegador e não depende da extensão ui do DuckDB.
"""

import sys

import pandas as pd

from pipeline.db import PASTA_RAW, conectar, criar_schema, gravar

SCHEMA = "raw"

ARQUIVOS = {
    "olist_orders_dataset.csv.gz": "pedidos",
    "olist_order_items_dataset.csv.gz": "itens_pedido",
    "olist_order_payments_dataset.csv.gz": "pagamentos",
    "olist_order_reviews_dataset.csv.gz": "avaliacoes",
    "olist_customers_dataset.csv.gz": "clientes",
    "olist_sellers_dataset.csv.gz": "vendedores",
    "olist_products_dataset.csv.gz": "produtos",
    "product_category_name_translation.csv.gz": "traducao_categorias",
    "olist_geolocation_dataset.csv.gz": "geolocalizacao",
}


def formatar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def ler(arquivo: str) -> pd.DataFrame:
    return pd.read_csv(
        PASTA_RAW / arquivo,
        dtype=str,
        encoding="utf-8",
        compression="gzip",
        # Só o campo vazio vira nulo. O padrão do pandas também anula textos
        # como "NA", "null" e "nan", o que seria corrigir valor.
        keep_default_na=False,
        na_values=[""],
    )


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    faltando = [a for a in ARQUIVOS if not (PASTA_RAW / a).is_file()]
    if faltando:
        print(f"Arquivos não encontrados em {PASTA_RAW}:")
        for arquivo in faltando:
            print(f"  {arquivo}")
        print("Nenhuma tabela foi gravada.")
        sys.exit(1)

    con = conectar()
    try:
        criar_schema(con, SCHEMA)
        total = 0
        for arquivo, tabela in ARQUIVOS.items():
            contagem = gravar(con, ler(arquivo), SCHEMA, tabela)
            total += contagem
            print(f"{SCHEMA}.{tabela:<22}{formatar(contagem):>12}")
        print(f"{'total':<26}{formatar(total):>12}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
