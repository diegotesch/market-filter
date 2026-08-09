"""
awin.py

Cliente minimo do Product Feed da Awin.

Duas credenciais existem na Awin e nao sao intercambiaveis:
- Product Feed API key (Toolbox > Create-a-Feed, embutida no link
  "Download list"): e a que este modulo usa.
- Publisher API token (ui.awin.com/awin-api): serve para api.awin.com e
  responde 500/404 aqui.
"""

import csv
import gzip
import io
import os
import urllib.parse

import requests

# carregado aqui porque este e o primeiro modulo importado por todos os
# scripts -- garante que o .env valha antes de qualquer leitura de ambiente.
# python-dotenv e so conveniencia para rodar local: quem passa as variaveis
# direto no ambiente (GitHub Actions, por exemplo) nao precisa dele.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

PRODUCTDATA_KEY = os.getenv("AWIN_PRODUCTDATA_KEY") or os.getenv("AWIN_TOKEN")

LISTA_URL = "https://productdata.awin.com/datafeed/list/apikey/{key}/"

BASE_DOWNLOAD = "https://productdata.awin.com/datafeed/download/apikey/{key}/"

# Colunas pedidas no download. Este conjunto foi tirado da propria URL que a
# Awin gera para os feeds BR, entao e seguro para eles. Feeds de outras
# regioes podem nao publicar todas -- por isso baixar_feed() tem fallback.
COLUNAS = [
    "aw_product_id",
    "product_name",
    "merchant_id",
    "merchant_name",
    "brand_name",
    "category_name",
    "merchant_category",
    "search_price",
    "in_stock",
    "aw_deep_link",
    "aw_image_url",
    "description",
]

# Conjunto minimo, usado se o feed rejeitar a lista completa.
COLUNAS_MINIMAS = [
    "aw_product_id",
    "product_name",
    "merchant_name",
    "search_price",
    "aw_deep_link",
]

ERRO_CHAVE = (
    "A chave nao foi aceita pelo productdata.awin.com.\n"
    "Causa mais comum: usar o token da Publisher API (ui.awin.com/awin-api)\n"
    "no lugar da chave do Product Feed.\n"
    "A chave certa esta no painel Awin em Toolbox > Create-a-Feed, dentro da\n"
    "URL da caixa 'Feed List Download' -- e o trecho depois de /apikey/."
)


class AwinError(RuntimeError):
    pass


def _exigir_chave():
    if not PRODUCTDATA_KEY:
        raise AwinError("AWIN_PRODUCTDATA_KEY nao definido (use .env ou secret)")


def listar_feeds() -> list[dict]:
    """Retorna a lista de feeds acessiveis, uma dict por feed."""
    _exigir_chave()
    resp = requests.get(LISTA_URL.format(key=PRODUCTDATA_KEY), timeout=60)

    # a Awin responde 500 (nao 401) quando a chave nao vale para o productdata
    if resp.status_code in (401, 403, 500):
        raise AwinError(f"HTTP {resp.status_code} na lista de feeds.\n\n{ERRO_CHAVE}")
    resp.raise_for_status()

    texto = resp.content.decode("utf-8", errors="replace")
    return list(csv.DictReader(io.StringIO(texto)))


def _url_download(feed_id: str, colunas: list[str], idioma: str) -> str:
    return (
        BASE_DOWNLOAD.format(key=PRODUCTDATA_KEY)
        + f"language/{idioma}/fid/{feed_id}/"
        + f"columns/{','.join(colunas)}/"
        + "format/csv/delimiter/"
        + urllib.parse.quote(",", safe="")
        + "/compression/gzip/"
    )


def baixar_feed(feed_id: str, idioma: str = "pt") -> list[dict]:
    """
    Baixa um feed e devolve as linhas como lista de dicts.

    Se o feed rejeitar o conjunto completo de colunas, tenta de novo com o
    conjunto minimo antes de desistir -- feeds de regioes diferentes publicam
    conjuntos de colunas diferentes.
    """
    _exigir_chave()

    for colunas in (COLUNAS, COLUNAS_MINIMAS):
        url = _url_download(feed_id, colunas, idioma)
        resp = requests.get(url, timeout=120)

        if resp.status_code == 200:
            bruto = gzip.decompress(resp.content).decode("utf-8", errors="replace")
            return list(csv.DictReader(io.StringIO(bruto)))

        if resp.status_code == 404 and colunas is COLUNAS:
            # pode ser coluna nao suportada -- vale tentar o conjunto minimo
            continue

        if resp.status_code == 404:
            raise AwinError(
                f"404 no feed {feed_id}. Confira se e um Feed ID valido "
                f"(o Advertiser ID nao serve) e se o idioma '{idioma}' existe "
                f"para essa loja. Rode `python listar_feeds.py`."
            )
        if resp.status_code in (401, 403, 500):
            raise AwinError(f"HTTP {resp.status_code} no feed {feed_id}.\n\n{ERRO_CHAVE}")
        resp.raise_for_status()

    raise AwinError(f"Nao foi possivel baixar o feed {feed_id}.")


def preco(linha: dict) -> float:
    """Le search_price de forma tolerante; devolve 0.0 se nao der."""
    try:
        valor = (linha.get("search_price") or "").strip()
        return float(valor) if valor else 0.0
    except (TypeError, ValueError):
        return 0.0
