"""
listar_feeds.py

Lista todos os feeds de produto a que sua conta Awin tem acesso, mostrando
lado a lado o Advertiser ID e o Feed ID (fid).

Por que isso existe: a URL de download do datafeed usa 'fid', que e o
**Feed ID**, e nao o Advertiser ID. Passar o advertiser id no lugar do fid
retorna 404 -- foi exatamente o que aconteceu na primeira execucao.

Uso:
    python listar_feeds.py

Precisa de AWIN_PRODUCTDATA_KEY no ambiente (ou no .env).

IMPORTANTE -- sao DUAS credenciais diferentes na Awin:
  - Publisher API token: pego em ui.awin.com/awin-api. Serve para api.awin.com.
    NAO funciona aqui (o productdata responde 500 ou 404 com ele).
  - Product Feed API key: pega em Toolbox > Create-a-Feed, embutida no link
    "Download list". E essa que este script usa.
"""

import os
import io
import sys

import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# A chave do productdata NAO e a mesma coisa que o token da Publisher API.
# Ver docstring do modulo. AWIN_TOKEN e aceito como fallback legado.
PRODUCTDATA_KEY = os.getenv("AWIN_PRODUCTDATA_KEY") or os.getenv("AWIN_TOKEN")

LISTA_URL = "https://productdata.awin.com/datafeed/list/apikey/{token}/"

ERRO_CHAVE_ERRADA = (
    "A chave usada nao foi aceita pelo productdata.awin.com.\n"
    "Causa mais comum: estar usando o token da Publisher API (o de\n"
    "ui.awin.com/awin-api) no lugar da chave do Product Feed -- sao\n"
    "credenciais diferentes.\n\n"
    "Onde achar a chave certa: no painel Awin, Toolbox > Create-a-Feed.\n"
    "O link 'Download list' de la tem o formato\n"
    "  https://productdata.awin.com/datafeed/list/apikey/SUA_CHAVE/\n"
    "Copie o trecho logo depois de /apikey/ e use em AWIN_PRODUCTDATA_KEY."
)

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
    if not PRODUCTDATA_KEY:
        print("Erro: AWIN_PRODUCTDATA_KEY nao definido (use .env ou variavel de ambiente)")
        sys.exit(1)

    url = LISTA_URL.format(token=PRODUCTDATA_KEY)
    print("Baixando lista de feeds da Awin...")
    resp = requests.get(url, timeout=60)

    # a Awin responde 500 (nao 401) quando a chave nao vale para o productdata
    if resp.status_code in (401, 403, 500):
        print(f"\nHTTP {resp.status_code} ao consultar a lista de feeds.\n")
        print(ERRO_CHAVE_ERRADA)
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
