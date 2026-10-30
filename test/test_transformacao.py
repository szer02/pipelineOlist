"""Testes de pipeline/transformacao.py: raw inventado em tmp_path -> refined."""

from decimal import Decimal

import duckdb
import pytest

from pipeline import db, transformacao


def pedido(
    pedido_id,
    status="delivered",
    compra="2018-01-10 10:00:00",
    entrega="2018-01-15 15:00:00",
    prevista="2018-01-20 00:00:00",
):
    # Ordem das colunas de raw.pedidos: id, cliente, status, compra, aprovação,
    # envio, entrega, entrega prevista.
    return (pedido_id, "c1", status, compra, compra, compra, entrega, prevista)


def item(pedido_id, seq="1", preco="10.50", frete="2.00"):
    return (pedido_id, seq, "prod1", "vend1", "2018-01-12 00:00:00", preco, frete)


def preparar(tmp_path, monkeypatch, linhas=None, sem=()):
    """Cria as oito tabelas de raw (tudo VARCHAR, como a ingestão grava),
    vazias, menos as linhas pedidas. `sem` deixa tabelas de fora."""
    arquivo = tmp_path / "olist.duckdb"
    monkeypatch.setattr(db, "ARQUIVO_BANCO", arquivo)
    con = duckdb.connect(str(arquivo))
    con.execute("CREATE SCHEMA raw").complete()
    for tabela, colunas in transformacao.COLUNAS.items():
        if tabela in sem:
            continue
        definicao = ", ".join(f"{origem} VARCHAR" for origem, _, _ in colunas)
        con.execute(f"CREATE TABLE raw.{tabela} ({definicao})").complete()
    con.close()
    acrescentar(tmp_path, linhas or {})


def acrescentar(tmp_path, linhas):
    con = duckdb.connect(str(tmp_path / "olist.duckdb"))
    for tabela, valores in linhas.items():
        for linha in valores:
            marcas = ", ".join("?" for _ in linha)
            con.execute(f"INSERT INTO raw.{tabela} VALUES ({marcas})", linha).complete()
    con.close()


def consultar(tmp_path, sql):
    con = duckdb.connect(str(tmp_path / "olist.duckdb"), read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def tabelas_em_refined(tmp_path):
    return consultar(
        tmp_path,
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'refined'",
    )[0][0]


def tipos(tmp_path, tabela):
    return dict(
        consultar(
            tmp_path,
            "SELECT column_name, data_type FROM information_schema.columns "
            f"WHERE table_schema = 'refined' AND table_name = '{tabela}'",
        )
    )


# --- caminho feliz -----------------------------------------------------------


def test_duplicata_exata_sai_e_as_outras_linhas_ficam(tmp_path, monkeypatch):
    preparar(
        tmp_path,
        monkeypatch,
        {
            "pedidos": [
                pedido("p1"),
                pedido("p1"),  # cópia exata da linha acima: sai
                pedido("p2"),  # outro pedido: fica
            ]
        },
    )

    transformacao.main()

    assert consultar(tmp_path, "SELECT pedido_id FROM refined.pedidos ORDER BY 1") == [
        ("p1",),
        ("p2",),
    ]


def test_colunas_saem_renomeadas_pelo_mapa(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)

    transformacao.main()

    for tabela, colunas in transformacao.COLUNAS.items():
        assert list(tipos(tmp_path, tabela)) == [destino for _, destino, _ in colunas]


def test_datas_viram_timestamp_e_data_prevista_vira_date(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, {"pedidos": [pedido("p1")]})

    transformacao.main()

    colunas = tipos(tmp_path, "pedidos")
    assert colunas["data_compra"] == "TIMESTAMP"
    assert colunas["data_entrega"] == "TIMESTAMP"
    assert colunas["data_entrega_prevista"] == "DATE"


def test_dinheiro_vira_decimal_com_centavos_exatos(tmp_path, monkeypatch):
    # 10.5 sem a segunda casa: tem que virar 10.50 exato, não 10.4999...
    preparar(tmp_path, monkeypatch, {"itens_pedido": [item("p1", preco="10.5")]})

    transformacao.main()

    assert tipos(tmp_path, "itens_pedido")["preco"] == "DECIMAL(10,2)"
    assert consultar(tmp_path, "SELECT preco, frete FROM refined.itens_pedido") == [
        (Decimal("10.50"), Decimal("2.00"))
    ]


def test_data_criacao_perde_a_hora_do_horario_de_verao(tmp_path, monkeypatch):
    avaliacao = (
        "a1",
        "p1",
        "5",
        None,
        None,
        "2018-02-18 01:00:00",  # 01:00 de horário de verão: vira só a data
        "2018-02-19 10:00:00",
    )
    preparar(tmp_path, monkeypatch, {"avaliacoes": [avaliacao]})

    transformacao.main()

    linha = consultar(tmp_path, "SELECT data_criacao::VARCHAR FROM refined.avaliacoes")
    assert linha == [("2018-02-18",)]


def test_cep_continua_texto_com_zero_a_esquerda(tmp_path, monkeypatch):
    # CEP começando com zero: como número perderia o zero.
    preparar(
        tmp_path, monkeypatch, {"clientes": [("c1", "u1", "01310", "sao paulo", "SP")]}
    )

    transformacao.main()

    assert tipos(tmp_path, "clientes")["cep_prefixo"] == "VARCHAR"
    assert consultar(tmp_path, "SELECT cep_prefixo FROM refined.clientes") == [
        ("01310",)
    ]


def test_nulo_e_mantido_e_a_linha_nao_sai(tmp_path, monkeypatch):
    preparar(
        tmp_path,
        monkeypatch,
        {
            "pedidos": [
                pedido("p1", status="canceled", entrega=None),  # sem data: não entregue
                pedido("p2"),
            ]
        },
    )

    transformacao.main()

    assert consultar(
        tmp_path, "SELECT pedido_id, data_entrega FROM refined.pedidos ORDER BY 1"
    )[0] == ("p1", None)
    assert consultar(tmp_path, "SELECT count(*) FROM refined.pedidos") == [(2,)]


def test_mesma_avaliacao_em_dois_pedidos_nao_e_conflito(tmp_path, monkeypatch):
    def avaliacao(pedido_id):
        return ("a1", pedido_id, "4", None, None, "2018-02-18 00:00:00", None)

    # Mesmo avaliacao_id em dois pedidos: a chave é (avaliacao_id, pedido_id).
    preparar(tmp_path, monkeypatch, {"avaliacoes": [avaliacao("p1"), avaliacao("p2")]})

    transformacao.main()

    assert consultar(tmp_path, "SELECT count(*) FROM refined.avaliacoes") == [(2,)]


def test_reexecutar_da_o_mesmo_resultado(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, {"pedidos": [pedido("p1"), pedido("p2")]})

    transformacao.main()
    transformacao.main()

    assert consultar(tmp_path, "SELECT count(*) FROM refined.pedidos") == [(2,)]


# --- conversão que falha -----------------------------------------------------


def test_preco_que_nao_e_numero_encerra_sem_virar_nulo(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, {"itens_pedido": [item("p1", preco="abc")]})

    with pytest.raises(SystemExit) as saida:
        transformacao.main()

    assert saida.value.code == 1
    assert tabelas_em_refined(tmp_path) == 0


def test_inteiro_com_casa_decimal_encerra_em_vez_de_arredondar(tmp_path, monkeypatch):
    # CAST('1.5' AS INTEGER) dá 2 em silêncio no DuckDB; o formato barra antes.
    preparar(tmp_path, monkeypatch, {"itens_pedido": [item("p1", seq="1.5")]})

    with pytest.raises(SystemExit):
        transformacao.main()

    assert tabelas_em_refined(tmp_path) == 0


def test_dinheiro_com_tres_casas_encerra_em_vez_de_arredondar(tmp_path, monkeypatch):
    # CAST('1.005' AS DECIMAL(10,2)) dá 1.01 em silêncio.
    preparar(tmp_path, monkeypatch, {"itens_pedido": [item("p1", preco="1.005")]})

    with pytest.raises(SystemExit):
        transformacao.main()

    assert tabelas_em_refined(tmp_path) == 0


def test_data_no_formato_mas_impossivel_encerra(tmp_path, monkeypatch):
    # Mês 13 casa com a regex e só falha no strptime.
    preparar(
        tmp_path,
        monkeypatch,
        {"pedidos": [pedido("p1", compra="2018-13-01 10:00:00")]},
    )

    with pytest.raises(SystemExit):
        transformacao.main()

    assert tabelas_em_refined(tmp_path) == 0


def test_falha_de_conversao_nao_mexe_no_refined_anterior(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, {"pedidos": [pedido("p1")]})
    transformacao.main()
    acrescentar(tmp_path, {"pedidos": [pedido("p2", prevista="20/01/2018")]})

    with pytest.raises(SystemExit):
        transformacao.main()

    # A checagem roda antes da gravação: refined continua com o p1 só.
    assert consultar(tmp_path, "SELECT pedido_id FROM refined.pedidos") == [("p1",)]


def test_valor_da_mensagem_tira_o_valor_citado_pelo_duckdb():
    erro = duckdb.Error("Conversion Error: Could not parse string '2018-13-01' x")

    assert transformacao.valor_da_mensagem(erro) == "'2018-13-01'"
    assert transformacao.valor_da_mensagem(duckdb.Error("outra\nlinha")) == "outra"


# --- chave e tabelas ---------------------------------------------------------


def test_chave_repetida_com_conteudo_diferente_encerra(tmp_path, monkeypatch):
    preparar(
        tmp_path,
        monkeypatch,
        {
            "pedidos": [
                pedido("p1", status="delivered"),
                pedido("p1", status="canceled"),  # mesma chave, outro status
            ]
        },
    )

    with pytest.raises(SystemExit) as saida:
        transformacao.main()

    assert saida.value.code == 1
    assert tabelas_em_refined(tmp_path) == 0


def test_tabela_faltando_em_raw_encerra(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, sem=("vendedores",))

    with pytest.raises(SystemExit) as saida:
        transformacao.main()

    assert saida.value.code == 1
    assert tabelas_em_refined(tmp_path) == 0
