"""Etapa 2 do pipeline Olist: tipa, renomeia e deduplica raw no schema refined.

Execução:  uv run python -m pipeline.transformacao

SPEC

1. Escopo
   Lê de raw, escreve em refined, nunca escreve em raw. Entram oito tabelas:
   pedidos, itens_pedido, pagamentos, clientes, vendedores, produtos,
   traducao_categorias, avaliacoes. geolocalizacao fica de fora.
   Por quê: raw é "o dado que chegou" e precisa continuar intacto para que
   qualquer decisão daqui possa ser conferida contra a origem. geolocalizacao
   não é lida por nenhum mart do curso, e não se limpa o que ninguém vai ler.

2. Nomes
   Colunas renomeadas para português, snake_case, pelo mapa COLUNAS abaixo,
   completo e literal: nenhuma coluna fora do mapa, nenhuma descartada.
   Por quê: é o vocabulário digitado de memória nos JOINs da aula 3. Coluna
   descartada aqui é coluna que o mart não pode mais pedir.

3. Tipos
   - Datas com hora (data_compra, data_aprovacao, data_envio, data_entrega,
     data_limite_envio, data_resposta): TIMESTAMP, formato declarado
     '%Y-%m-%d %H:%M:%S'.
     Por quê: 19 caracteres, ano-mês-dia, em 100% das linhas não nulas.
     Formato declarado não depende de adivinhação.
   - data_entrega_prevista: DATE.
     Por quê: a hora é 00:00:00 em todas as 99.441 linhas; guardar a hora
     seria inventar precisão.
   - data_criacao: DATE.
     Por quê: a hora é 00:00:00 em 99.139 das 99.224 avaliações; nas outras
     85 é 01:00:00, efeito de horário de verão, não um horário de verdade.
   - Dinheiro (preco, frete, valor): DECIMAL(10,2).
     Por quê: DOUBLE não representa centavos com exatidão, e soma de dinheiro
     tem que fechar. Em raw os valores têm no máximo 2 casas.
   - Contagens e medidas (item_seq, pagamento_seq, parcelas, tamanho_nome,
     tamanho_descricao, qtd_fotos, peso_g, comprimento_cm, altura_cm,
     largura_cm, nota): INTEGER.
   - Todo o resto continua VARCHAR, inclusive cep_prefixo.
     Por quê: 23.995 clientes têm CEP começando com zero. CEP é
     identificador, nunca é somado, e como número perderia o zero.
   - A conversão é feita em SQL pelo DuckDB (strptime, CAST), disparada pelo
     Python.
     Por quê: o dado já está no banco; trazê-lo para a memória só para
     converter tipo é custo sem ganho.

4. Conversão que falha
   Para tudo. Usa strptime e CAST, nunca try_strptime nem TRY_CAST. Antes da
   conversão, cada texto precisa casar com o formato do seu tipo (FORMATOS
   abaixo); fora do formato também é falha. Ao falhar: diz tabela, coluna e
   um exemplo do valor, e sai com sys.exit(1).
   Por quê: um nulo fabricado pela conversão fica indistinguível de um nulo
   verdadeiro do dado, para sempre. O mesmo vale para um valor arredondado:
   no DuckDB 2.0, CAST('1.5' AS INTEGER) dá 2 e CAST('1.005' AS
   DECIMAL(10,2)) dá 1.01, sem erro, e strptime aceita '2018-1-01'. A
   checagem de formato transforma esses casos silenciosos em parada.

5. Duplicatas
   Chave de cada tabela em CHAVES abaixo. avaliacoes usa (avaliacao_id,
   pedido_id) porque avaliacao_id sozinho não é chave: o mesmo id aparece em
   mais de um pedido (99.224 linhas, 98.410 avaliacao_id distintos).
   Linha inteira repetida: mantém uma e conta quantas saíram.
   Chave repetida com conteúdo diferente: para, mostra a chave e as linhas
   conflitantes, sys.exit(1).
   Por quê: escolher uma das linhas em silêncio é decidir sem dizer que
   decidiu. Repetição exata não carrega informação; conflito carrega.

6. Nulos
   Nenhuma linha é apagada por ter nulo, nenhum nulo é preenchido, nenhuma
   anomalia de negócio é corrigida (pedidos delivered sem data_entrega,
   data_envio antes da data_compra, pedidos com mais de uma avaliação).
   Por quê: o nulo é informação (pedido cancelado não tem data de entrega
   porque não foi entregue), e dar rótulo aos 610 produtos sem categoria ou
   tratar anomalia é decisão do mart, que sabe a pergunta. refined não
   corrige fato.

7. Saída na tela
   Uma linha por tabela com linhas de entrada, de saída e duplicatas; abaixo,
   indentadas, as colunas com nulo e a contagem ("nulos mantidos: nenhum"
   quando não há). Linha final com o total. Contagens vindas do banco, milhar
   separado por ponto, stdout em utf-8.
   Por quê: é o instrumento de conferência desta etapa. Mostrar os nulos
   prova que nenhum foi fabricado nem preenchido; "nenhum" explícito
   distingue "não há nulo" de "esqueci de contar". O Prompt de Comando do
   Windows embaralha acento por padrão.

8. Reexecução
   CREATE OR REPLACE TABLE, nunca acrescenta. As oito tabelas são gravadas
   numa única transação: ou todas são substituídas, ou nenhuma.
   Por quê: rodar dez vezes dá o mesmo que rodar uma, então errar e rodar de
   novo não tem custo. E uma falha no meio não deixa refined meio nova, meio
   antiga, combinação que nenhuma execução produziu.

9. Erro
   Antes de transformar, verifica se as oito tabelas existem em raw. Faltando
   alguma: lista quais, diz para rodar "uv run python -m pipeline.ingestao" e
   sai com sys.exit(1). Toda checagem (tabelas, formato, conversão, chave)
   roda antes de qualquer gravação.
   Por quê: transformar sete de oito tabelas em silêncio produz um mart
   errado que parece certo.
"""

import re
import sys

import duckdb

from pipeline.db import conectar, criar_schema
from pipeline.ingestao import formatar

ORIGEM = "raw"
DESTINO = "refined"

FORMATO_DATA = "%Y-%m-%d %H:%M:%S"

# (coluna em raw, coluna em refined, tipo). None = continua VARCHAR.
COLUNAS = {
    "pedidos": [
        ("order_id", "pedido_id", None),
        ("customer_id", "cliente_id", None),
        ("order_status", "status", None),
        ("order_purchase_timestamp", "data_compra", "TIMESTAMP"),
        ("order_approved_at", "data_aprovacao", "TIMESTAMP"),
        ("order_delivered_carrier_date", "data_envio", "TIMESTAMP"),
        ("order_delivered_customer_date", "data_entrega", "TIMESTAMP"),
        ("order_estimated_delivery_date", "data_entrega_prevista", "DATE"),
    ],
    "itens_pedido": [
        ("order_id", "pedido_id", None),
        ("order_item_id", "item_seq", "INTEGER"),
        ("product_id", "produto_id", None),
        ("seller_id", "vendedor_id", None),
        ("shipping_limit_date", "data_limite_envio", "TIMESTAMP"),
        ("price", "preco", "DECIMAL(10,2)"),
        ("freight_value", "frete", "DECIMAL(10,2)"),
    ],
    "pagamentos": [
        ("order_id", "pedido_id", None),
        ("payment_sequential", "pagamento_seq", "INTEGER"),
        ("payment_type", "tipo", None),
        ("payment_installments", "parcelas", "INTEGER"),
        ("payment_value", "valor", "DECIMAL(10,2)"),
    ],
    "clientes": [
        ("customer_id", "cliente_id", None),
        ("customer_unique_id", "cliente_unico_id", None),
        ("customer_zip_code_prefix", "cep_prefixo", None),
        ("customer_city", "cidade", None),
        ("customer_state", "uf", None),
    ],
    "vendedores": [
        ("seller_id", "vendedor_id", None),
        ("seller_zip_code_prefix", "cep_prefixo", None),
        ("seller_city", "cidade", None),
        ("seller_state", "uf", None),
    ],
    "produtos": [
        ("product_id", "produto_id", None),
        ("product_category_name", "categoria", None),
        ("product_name_lenght", "tamanho_nome", "INTEGER"),
        ("product_description_lenght", "tamanho_descricao", "INTEGER"),
        ("product_photos_qty", "qtd_fotos", "INTEGER"),
        ("product_weight_g", "peso_g", "INTEGER"),
        ("product_length_cm", "comprimento_cm", "INTEGER"),
        ("product_height_cm", "altura_cm", "INTEGER"),
        ("product_width_cm", "largura_cm", "INTEGER"),
    ],
    "traducao_categorias": [
        ("product_category_name", "categoria", None),
        ("product_category_name_english", "categoria_en", None),
    ],
    "avaliacoes": [
        ("review_id", "avaliacao_id", None),
        ("order_id", "pedido_id", None),
        ("review_score", "nota", "INTEGER"),
        ("review_comment_title", "titulo", None),
        ("review_comment_message", "comentario", None),
        ("review_creation_date", "data_criacao", "DATE"),
        ("review_answer_timestamp", "data_resposta", "TIMESTAMP"),
    ],
}

CHAVES = {
    "pedidos": ["pedido_id"],
    "itens_pedido": ["pedido_id", "item_seq"],
    "pagamentos": ["pedido_id", "pagamento_seq"],
    "clientes": ["cliente_id"],
    "vendedores": ["vendedor_id"],
    "produtos": ["produto_id"],
    "traducao_categorias": ["categoria"],
    "avaliacoes": ["avaliacao_id", "pedido_id"],
}

# Texto aceito por tipo, conferido antes do CAST/strptime, que sozinhos
# arredondam ou aceitam variações (ver regra 4).
FORMATOS = {
    "TIMESTAMP": r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",
    "DATE": r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",
    "INTEGER": r"-?\d+",
    "DECIMAL(10,2)": r"-?\d+(\.\d{1,2})?",
}


def expressao(origem: str, tipo: str | None) -> str:
    if tipo is None:
        return origem
    if tipo == "TIMESTAMP":
        return f"strptime({origem}, '{FORMATO_DATA}')"
    if tipo == "DATE":
        # Descarta a hora de propósito: ver regra 3.
        return f"CAST(strptime({origem}, '{FORMATO_DATA}') AS DATE)"
    return f"CAST({origem} AS {tipo})"


def selecao(tabela: str) -> str:
    colunas = ", ".join(
        f"{expressao(origem, tipo)} AS {destino}"
        for origem, destino, tipo in COLUNAS[tabela]
    )
    # DISTINCT sobre a linha já convertida remove só repetição exata.
    return f"SELECT DISTINCT {colunas} FROM {ORIGEM}.{tabela}"


def contar(con: duckdb.DuckDBPyConnection, sql: str) -> int:
    return con.execute(sql).fetchall()[0][0]


def falhar(linhas: list[str]) -> None:
    for linha in linhas:
        print(linha)
    print(f"Nada foi gravado em {DESTINO}.")
    sys.exit(1)


def tabelas_faltando(con: duckdb.DuckDBPyConnection) -> list[str]:
    existentes = {
        nome
        for (nome,) in con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_catalog = current_database() AND table_schema = ?",
            [ORIGEM],
        ).fetchall()
    }
    return [t for t in COLUNAS if t not in existentes]


def valor_da_mensagem(erro: duckdb.Error) -> str:
    # O DuckDB cita o valor que não converteu: string 'abc' ou string "abc".
    achado = re.search(r"string (['\"])(.*?)\1", str(erro))
    return repr(achado.group(2)) if achado else str(erro).splitlines()[0]


def checar_conversoes(con: duckdb.DuckDBPyConnection, tabela: str) -> None:
    for origem, destino, tipo in COLUNAS[tabela]:
        if tipo is None:
            continue
        local = f"{ORIGEM}.{tabela}.{origem} -> {destino} ({tipo})"

        fora_do_formato = con.execute(
            f"SELECT {origem} FROM {ORIGEM}.{tabela} "
            f"WHERE {origem} IS NOT NULL "
            f"AND NOT regexp_full_match({origem}, '{FORMATOS[tipo]}') LIMIT 1"
        ).fetchall()
        if fora_do_formato:
            falhar(
                [
                    f"Conversão falhou em {local}:",
                    f"  valor fora do formato: {fora_do_formato[0][0]!r}",
                ]
            )

        # Pega o que passa no formato e mesmo assim não converte
        # (mês 13, inteiro maior que INTEGER, dinheiro maior que DECIMAL(10,2)).
        try:
            con.execute(
                f"SELECT min({expressao(origem, tipo)}) FROM {ORIGEM}.{tabela}"
            ).fetchall()
        except duckdb.Error as erro:
            falhar(
                [
                    f"Conversão falhou em {local}:",
                    f"  valor que não converteu: {valor_da_mensagem(erro)}",
                ]
            )


def checar_chave(con: duckdb.DuckDBPyConnection, tabela: str) -> None:
    chave = ", ".join(CHAVES[tabela])
    junta = " AND ".join(f"c.{k} IS NOT DISTINCT FROM p.{k}" for k in CHAVES[tabela])
    base = (
        f"WITH convertido AS ({selecao(tabela)}), "
        f"conflito AS (SELECT {chave} FROM convertido "
        f"GROUP BY {chave} HAVING count(*) > 1) "
    )
    chaves_em_conflito = contar(con, base + "SELECT count(*) FROM conflito")
    if chaves_em_conflito == 0:
        return

    # Mostra a primeira chave em conflito, em ordem, para a mensagem ser
    # a mesma a cada execução.
    resultado = con.execute(
        base + f"SELECT c.* FROM convertido c "
        f"JOIN (SELECT * FROM conflito ORDER BY ALL LIMIT 1) p ON {junta} "
        f"ORDER BY ALL"
    )
    nomes = [d[0] for d in resultado.description]
    linhas = resultado.fetchall()
    valores_chave = ", ".join(
        f"{k}={linhas[0][nomes.index(k)]!r}" for k in CHAVES[tabela]
    )
    mensagem = [
        f"Chave repetida com conteúdo diferente em {DESTINO}.{tabela} "
        f"({formatar(chaves_em_conflito)} chave(s) em conflito).",
        f"  chave: {valores_chave}",
    ]
    for linha in linhas:
        mensagem.append(
            "    " + ", ".join(f"{n}={v!r}" for n, v in zip(nomes, linha))
        )
    falhar(mensagem)


def gravar_tudo(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("BEGIN TRANSACTION").complete()
    try:
        criar_schema(con, DESTINO)
        for tabela in COLUNAS:
            con.execute(
                f"CREATE OR REPLACE TABLE {DESTINO}.{tabela} AS {selecao(tabela)}"
            ).complete()
        con.execute("COMMIT").complete()
    except BaseException:
        con.execute("ROLLBACK").complete()
        raise


def nulos(con: duckdb.DuckDBPyConnection, tabela: str) -> list[tuple[str, int]]:
    destinos = [destino for _, destino, _ in COLUNAS[tabela]]
    contagens = con.execute(
        "SELECT "
        + ", ".join(f"count(*) FILTER ({d} IS NULL)" for d in destinos)
        + f" FROM {DESTINO}.{tabela}"
    ).fetchall()[0]
    return [(d, n) for d, n in zip(destinos, contagens) if n > 0]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    con = conectar()
    try:
        faltando = tabelas_faltando(con)
        if faltando:
            print(f"Tabelas não encontradas no schema {ORIGEM}:")
            for tabela in faltando:
                print(f"  {ORIGEM}.{tabela}")
            print('Rode antes: "uv run python -m pipeline.ingestao"')
            sys.exit(1)

        for tabela in COLUNAS:
            checar_conversoes(con, tabela)
            checar_chave(con, tabela)

        gravar_tudo(con)

        total_entrada = total_saida = 0
        for tabela in COLUNAS:
            entrada = contar(con, f"SELECT count(*) FROM {ORIGEM}.{tabela}")
            saida = contar(con, f"SELECT count(*) FROM {DESTINO}.{tabela}")
            total_entrada += entrada
            total_saida += saida
            print(
                f"{DESTINO}.{tabela:<22}{formatar(entrada):>8} -> "
                f"{formatar(saida):>7} linhas  "
                f"({formatar(entrada - saida)} duplicatas)"
            )
            com_nulo = nulos(con, tabela)
            descricao = (
                ", ".join(f"{d} {formatar(n)}" for d, n in com_nulo)
                if com_nulo
                else "nenhum"
            )
            print(f"    nulos mantidos: {descricao}")
        print(
            f"{'total':<30}{formatar(total_entrada):>8} -> "
            f"{formatar(total_saida):>7} linhas  "
            f"({formatar(total_entrada - total_saida)} duplicatas)"
        )
    finally:
        con.close()


if __name__ == "__main__":
    main()
