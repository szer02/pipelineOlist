"""Abre o olist.duckdb no navegador pela extensão ui do DuckDB.

Execução:  uv run python ui.py

SPEC

U1. O que faz
    Abre o olist.duckdb da raiz do projeto, instala e carrega a extensão ui
    (INSTALL ui; LOAD ui;) e chama CALL start_ui(), que sobe o servidor em
    http://localhost:4213 e abre o navegador.
    Por quê: explorar as tabelas pelo navegador em vez de lê-las no terminal.

U2. Fica de pé até Ctrl+C
    Mantém o processo rodando, imprime a URL e "Ctrl+C para encerrar". No
    Ctrl+C fecha a conexão e sai limpo, sem traceback.
    Por quê: a extensão só serve enquanto a conexão estiver viva. E o arquivo
    .duckdb aceita um único processo escrevendo: com o ui.py de pé, a
    ingestão falha com "Could not set lock on file" (no Windows a mensagem é
    "Cannot open file ... já está sendo usado por outro processo", seguida do
    PID que segura o arquivo). Saber exatamente como
    desligar o servidor faz parte da ferramenta.

U3. Não cria banco
    Se olist.duckdb não existir, diz que é preciso rodar a ingestão antes e
    sai com sys.exit(1). Por isso não usa conectar() de pipeline/db.py, que
    cria o arquivo quando ele falta.
    Por quê: um banco vazio aberto no navegador parece ingestão quebrada.

U4. Separação
    Não importa pipeline/ingestao.py, e a ingestão não importa este arquivo.
    Por quê: a ingestão roda sem servidor, sem navegador e sem depender da
    extensão ui.

U5. Saída na tela
    stdout reconfigurado para utf-8.
    Por quê: o Prompt de Comando do Windows embaralha acento por padrão.
"""

import sys
import time
from pathlib import Path

import duckdb

ARQUIVO_BANCO = Path(__file__).resolve().parent / "olist.duckdb"
URL = "http://localhost:4213"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    # Checagem explícita: duckdb.connect criaria um arquivo vazio no lugar.
    if not ARQUIVO_BANCO.is_file():
        print(f"Banco não encontrado: {ARQUIVO_BANCO}")
        print("Rode a ingestão antes: uv run python -m pipeline.ingestao")
        sys.exit(1)

    con = duckdb.connect(str(ARQUIVO_BANCO))
    try:
        # .complete(): o DuckDB 2.0 exige consumir cada resultado antes do próximo.
        con.execute("INSTALL ui").complete()
        con.execute("LOAD ui").complete()
        con.execute("CALL start_ui()").complete()
        print(f"DuckDB UI em {URL}")
        print("Ctrl+C para encerrar")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        con.close()
    print("Servidor encerrado.")


if __name__ == "__main__":
    main()
