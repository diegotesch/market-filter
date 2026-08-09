"""
listar_feeds.py

Lista todos os feeds de produto a que sua conta Awin tem acesso, mostrando
lado a lado o Advertiser ID e o Feed ID (fid).

Por que isso existe: a URL de download do datafeed usa 'fid', que e o
**Feed ID**, e nao o Advertiser ID. Passar o advertiser id no lugar do fid
retorna 404 -- foi exatamente o que aconteceu na primeira execucao.

Uso:
    python listar_feeds.py

So precisa de AWIN_TOKEN no ambiente (ou no .env).
"""

import os
import io
import sys

import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

AWIN_TOKEN = os.getenv("AWIN_TOKEN")

LISTA_URL = "https://productdata.awin.com/datafeed/list/apikey/{token}/"

# colunas que interessam, na ordem em que queremos exibir.
# a Awin as vezes muda o nome exato, entao casamos de forma tolerante.
COLUNAS_DESEJADAS = [
    "Advertiser ID",
    "Advertiser Name",
    "Feed ID",
    "Feed Name",
    "Language",
    "Membership Status",
    "No of products",
    "Last Imported",
]


def main():
    if not AWIN_TOKEN:
        print("Erro: AWIN_TOKEN nao definido (use .env ou variavel de ambiente)")
        sys.exit(1)

    url = LISTA_URL.format(token=AWIN_TOKEN)
    print("Baixando lista de feeds da Awin...")
    resp = requests.get(url, timeout=60)

    if resp.status_code == 401:
        print("401: token invalido ou sem permissao de acesso ao product data.")
        sys.exit(1)
    resp.raise_for_status()

    df = pd.read_csv(io.BytesIO(resp.content))
    if df.empty:
        print(
            "Nenhum feed retornado. Isso normalmente significa que voce ainda "
            "nao foi aprovado em nenhum programa que publique feed de produtos."
        )
        sys.exit(0)

    print(f"\n{len(df)} feed(s) disponivel(is).\n")
    print(f"Colunas retornadas pela Awin: {list(df.columns)}\n")

    presentes = [c for c in COLUNAS_DESEJADAS if c in df.columns]
    exibir = df[presentes] if presentes else df

    with pd.option_context("display.max_rows", None, "display.width", 200):
        print(exibir.to_string(index=False))

    print(
        "\nPegue o valor da coluna 'Feed ID' da loja que voce quer e use ele "
        "em AWIN_FEED_IDS (separado por virgula se for mais de um)."
    )


if __name__ == "__main__":
    main()
