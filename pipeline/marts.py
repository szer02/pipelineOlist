"""Etapa 3 do pipeline Olist: executa sql/marts/*.sql e grava o schema marts.

Execução:  uv run python -m pipeline.marts

SPEC

1. Escopo
   Lê de refined, escreve no schema marts. Nunca escreve em raw nem em
   refined. O schema marts é apagado e recriado a cada execução (DROP SCHEMA
   IF EXISTS marts CASCADE).
   Por quê: um mart cujo arquivo foi apagado não pode continuar existindo no
   banco. Recriar do zero garante que marts é exatamente o que está na pasta.

2. Um arquivo, uma tabela
   Lê todos os sql/marts/*.sql em ordem alfabética. Nome da tabela = nome do
   arquivo sem a extensão e sem o prefixo numérico:
     sql/marts/01_vendas_mensais.sql -> marts.vendas_mensais
   Executa: CREATE TABLE marts.<nome> AS <conteúdo do arquivo>
   Tira espaços e um ponto e vírgula do final do conteúdo, e nada mais. O
   Python não altera, não monta e não completa a SQL.
   Por quê: a regra de negócio mora inteira no arquivo .sql. Quem lê o
   arquivo lê o mart; não há metade da regra escondida no Python.

3. Saída na tela
   Uma linha por mart, com a contagem vinda do banco, milhar com ponto:
     ✓ marts.vendas_mensais        24 linhas
   Linha final com o número de marts e o total de linhas. stdout em utf-8.
   Por quê: é o instrumento de conferência desta etapa (os números de
   referência da aula batem contra ela). A contagem vem do banco porque é o
   que foi gravado de fato. O Prompt de Comando do Windows embaralha acento
   (e o ✓) por padrão.

4. Erro
   - Antes de tudo: faltando qualquer uma das oito tabelas em refined, lista
     quais, diz para rodar "uv run python -m pipeline.transformacao" e sai
     com sys.exit(1).
     Por quê: mart sobre refined incompleto dá erro confuso ou, pior, número
     errado que parece certo.
   - sql/marts/ sem nenhum arquivo: avisa e sys.exit(1).
     Por quê: recriar marts vazio apagaria todos os marts em silêncio.
   - Antes de executar qualquer SQL: arquivo sem prefixo NN_ ou dois arquivos
     que dão o mesmo nome de tabela -> lista quais e sys.exit(1).
     Por quê: sem prefixo a ordem de execução fica indefinida; nome repetido
     faria um mart sobrescrever outro.
   - Um .sql que falha: mostra o nome do arquivo e a mensagem do DuckDB, não
     executa os seguintes, sys.exit(1).
     Por quê: o nome do arquivo é onde o erro se corrige.
   - Mart com zero linhas: mostra o nome e sys.exit(1).
     Por quê: mart vazio é quase sempre um JOIN que não casou, e um dashboard
     vazio parece um negócio parado.
   - Tudo roda numa transação só: se qualquer passo falhar (inclusive o mart
     vazio), o schema marts volta a ser o da última execução que deu certo.
     Por quê: um schema pela metade quebra o dashboard sem avisar.

CRITÉRIOS DE ACEITE
- sql/marts/00_teste.sql com "SELECT 1 AS x" cria marts.teste com 1 linha.
- Apagar o arquivo e rodar de novo faz marts.teste desaparecer.
- Um arquivo com erro de sintaxe para tudo, com o nome do arquivo na tela, e
  marts continua exatamente como estava antes da execução.
- Um arquivo teste.sql, sem prefixo, para antes de executar qualquer SQL.
- Rodar duas vezes seguidas imprime exatamente a mesma coisa.
"""

import re
import sys
from pathlib import Path

import duckdb

from pipeline.db import PASTA_PROJETO, conectar, criar_schema
from pipeline.ingestao import formatar
from pipeline.transformacao import COLUNAS

ORIGEM = "refined"
DESTINO = "marts"
PASTA_SQL = PASTA_PROJETO / "sql" / "marts"

# NN_ = dois dígitos e sublinhado; o resto, sem o .sql, é o nome da tabela.
PADRAO_ARQUIVO = re.compile(r"(\d{2})_(.+)\.sql")


class FalhaMart(Exception):
    """Falha durante a gravação; a mensagem já está pronta para a tela."""


def contar(con: duckdb.DuckDBPyConnection, sql: str) -> int:
    return con.execute(sql).fetchall()[0][0]


def falhar(linhas: list[str]) -> None:
    for linha in linhas:
        print(linha)
    print(f"Nada foi alterado em {DESTINO}.")
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
    # As oito tabelas de refined são as do mapa da transformação.
    return [t for t in COLUNAS if t not in existentes]


def arquivos_dos_marts() -> list[tuple[Path, str]]:
    """Valida a pasta inteira antes de qualquer SQL; devolve (arquivo, tabela)."""
    rotulo = PASTA_SQL.relative_to(PASTA_PROJETO).as_posix()
    arquivos = sorted(PASTA_SQL.glob("*.sql"), key=lambda a: a.name)
    if not arquivos:
        falhar([f"Nenhum arquivo .sql em {rotulo}/."])

    sem_prefixo = [a.name for a in arquivos if not PADRAO_ARQUIVO.fullmatch(a.name)]
    if sem_prefixo:
        falhar(
            [f"Arquivos sem prefixo NN_ em {rotulo}/:"]
            + [f"  {nome}" for nome in sem_prefixo]
        )

    por_tabela: dict[str, list[str]] = {}
    for arquivo in arquivos:
        tabela = PADRAO_ARQUIVO.fullmatch(arquivo.name).group(2)
        # Identificador no DuckDB não diferencia maiúscula: "Vendas" = "vendas".
        por_tabela.setdefault(tabela.lower(), []).append(arquivo.name)
    repetidas = {t: nomes for t, nomes in por_tabela.items() if len(nomes) > 1}
    if repetidas:
        mensagem = ["Arquivos que dão o mesmo nome de tabela:"]
        for tabela, nomes in repetidas.items():
            mensagem.append(f"  {DESTINO}.{tabela}: {', '.join(nomes)}")
        falhar(mensagem)

    return [(a, PADRAO_ARQUIVO.fullmatch(a.name).group(2)) for a in arquivos]


def conteudo(arquivo: Path) -> str:
    # Só espaços e um ";" do final (regra 2); o resto da SQL vai como está.
    # utf-8-sig descarta o BOM que editores do Windows gravam no início.
    texto = arquivo.read_text(encoding="utf-8-sig").strip()
    if texto.endswith(";"):
        texto = texto[:-1].rstrip()
    return texto


def gravar_tudo(
    con: duckdb.DuckDBPyConnection, marts: list[tuple[Path, str]]
) -> list[tuple[str, int]]:
    rotulo = PASTA_SQL.relative_to(PASTA_PROJETO).as_posix()
    contagens = []
    con.execute("BEGIN TRANSACTION").complete()
    try:
        con.execute(f"DROP SCHEMA IF EXISTS {DESTINO} CASCADE").complete()
        criar_schema(con, DESTINO)
        for arquivo, tabela in marts:
            try:
                con.execute(
                    f'CREATE TABLE {DESTINO}."{tabela}" AS {conteudo(arquivo)}'
                ).complete()
            except duckdb.Error as erro:
                raise FalhaMart(f"Falha em {rotulo}/{arquivo.name}:\n  {erro}")
            linhas = contar(con, f'SELECT count(*) FROM {DESTINO}."{tabela}"')
            if linhas == 0:
                raise FalhaMart(
                    f"Mart vazio: {DESTINO}.{tabela} ({rotulo}/{arquivo.name})"
                )
            contagens.append((tabela, linhas))
        con.execute("COMMIT").complete()
    except BaseException:
        con.execute("ROLLBACK").complete()
        raise
    return contagens


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    con = conectar()
    try:
        faltando = tabelas_faltando(con)
        if faltando:
            print(f"Tabelas não encontradas no schema {ORIGEM}:")
            for tabela in faltando:
                print(f"  {ORIGEM}.{tabela}")
            print('Rode antes: "uv run python -m pipeline.transformacao"')
            sys.exit(1)

        marts = arquivos_dos_marts()

        try:
            contagens = gravar_tudo(con, marts)
        except FalhaMart as falha:
            falhar(str(falha).splitlines())

        # Só imprime depois do COMMIT: um ✓ antes de uma falha seria de uma
        # tabela que o ROLLBACK desfez.
        largura = max(len(f"{DESTINO}.{tabela}") for tabela, _ in contagens) + 2
        for tabela, linhas in contagens:
            print(f"✓ {f'{DESTINO}.{tabela}':<{largura}}{formatar(linhas):>9} linhas")
        total = sum(linhas for _, linhas in contagens)
        print(f"{formatar(len(contagens))} marts, {formatar(total)} linhas")
    finally:
        con.close()


if __name__ == "__main__":
    main()
