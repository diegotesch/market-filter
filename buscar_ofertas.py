"""
buscar_ofertas.py

Busca o feed de produtos da Awin para os anunciantes configurados,
filtra por desconto mínimo e/ou palavras-chave, e salva o resultado
em output/ofertas.json.

Como funciona a Awin aqui:
- A Awin disponibiliza um "Product Feed" (feed de produtos) por anunciante,
  atualizado periodicamente pela própria loja (preço, estoque, imagem, link).
- Baixamos esse feed em CSV via URL de datafeed da Awin (autenticada pelo token),
  processamos com pandas, e filtramos o que interessa.
- O link que vem no feed (coluna 'aw_deep_link' ou 'merchant_deep_link') já é
  o link de afiliado -- não precisa gerar nada manualmente.

Variáveis de ambiente necessárias (ver .env.example):
- AWIN_PRODUCTDATA_KEY: a chave do Product Feed (Toolbox > Create-a-Feed).
  Nao confundir com o token da Publisher API de ui.awin.com/awin-api --
  esse nao funciona no productdata.awin.com.
- AWIN_PUBLISHER_ID: seu Publisher ID (aparece no painel Awin)
- AWIN_FEED_IDS: um ou mais **Feed IDs** separados por vírgula. Não confundir
  com o Advertiser ID -- rode `python listar_feeds.py` para descobrir os seus.
"""

import os
import sys
import json
import io
from datetime import datetime, timezone

import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# Chave do Product Feed (Toolbox > Create-a-Feed), que NAO e o token da
# Publisher API. AWIN_TOKEN fica como fallback do secret antigo.
PRODUCTDATA_KEY = os.getenv("AWIN_PRODUCTDATA_KEY") or os.getenv("AWIN_TOKEN")
PUBLISHER_ID = os.getenv("AWIN_PUBLISHER_ID")

# ATENCAO: 'fid' na URL do datafeed e o **Feed ID**, nao o Advertiser ID.
# Passar o advertiser id ali da 404. Rode `python listar_feeds.py` para
# descobrir o Feed ID de cada loja.
# AWIN_ADVERTISER_IDS continua aceito como fallback so para nao quebrar
# quem ja tinha o secret antigo configurado.
FEED_IDS = os.getenv("AWIN_FEED_IDS") or os.getenv("AWIN_ADVERTISER_IDS", "")

# Configuracao de filtro -- ajuste conforme seu nicho.
# Todos podem ser sobrescritos por variavel de ambiente, o que permite
# afrouxar o filtro numa execucao de teste sem mexer no codigo.
DESCONTO_MINIMO_PCT = float(os.getenv("DESCONTO_MINIMO_PCT", "20"))
PALAVRAS_CHAVE = [
    p.strip().lower()
    for p in os.getenv(
        "PALAVRAS_CHAVE",
        "fone,carregador,cabo,mouse,teclado,headset,"
        "smartwatch,power bank,hub usb,ssd,webcam",
    ).split(",")
    if p.strip()
]
MAX_OFERTAS_POR_LOJA = int(os.getenv("MAX_OFERTAS_POR_LOJA", "30"))

# Salva uma amostra do feed cru em output/amostra_<id>.csv para inspecao
# manual quando o filtro nao retorna nada.
SALVAR_AMOSTRA = os.getenv("SALVAR_AMOSTRA", "1") not in ("0", "false", "")
LINHAS_AMOSTRA = 50

# URL base do datafeed da Awin.
# 'fid' = Feed ID. Nao e o Advertiser ID: sao numeros distintos, e passar o
# advertiser id aqui retorna 404 (foi o que quebrou a primeira execucao).
# 'language/pt' tambem faz parte da chave de busca do feed -- se a loja nao
# publicar feed nesse idioma, o retorno tambem e 404.
FEED_URL_TEMPLATE = (
    "https://productdata.awin.com/datafeed/download/apikey/{token}/"
    "language/pt/fid/{fid}/columns/aw_deep_link,product_name,"
    "search_price,merchant_name,merchant_category,description,"
    "aw_image_url,rrp_price/format/csv/delimiter/%2C/compression/gzip/"
)


def validar_config():
    faltando = []
    if not PRODUCTDATA_KEY:
        faltando.append("AWIN_PRODUCTDATA_KEY")
    if not PUBLISHER_ID:
        faltando.append("AWIN_PUBLISHER_ID")
    if not FEED_IDS:
        faltando.append("AWIN_FEED_IDS")
    if faltando:
        print(f"Erro: variaveis faltando no .env: {', '.join(faltando)}")
        sys.exit(1)


def baixar_feed(feed_id: str) -> pd.DataFrame:
    url = FEED_URL_TEMPLATE.format(token=PRODUCTDATA_KEY, fid=feed_id)
    print(f"Baixando feed {feed_id}...")
    resp = requests.get(url, timeout=60)

    if resp.status_code == 404:
        raise RuntimeError(
            f"404 no feed {feed_id}. Quase sempre significa que esse id nao e um "
            f"Feed ID valido (o Advertiser ID nao serve aqui). "
            f"Rode `python listar_feeds.py` para ver os Feed IDs disponiveis."
        )
    resp.raise_for_status()

    # o feed vem comprimido em gzip; pandas descomprime automatico pela extensao,
    # entao forcamos via BytesIO + compression explicita
    df = pd.read_csv(io.BytesIO(resp.content), compression="gzip")
    print(f"  -> feed baixado: {len(df)} linhas, colunas: {list(df.columns)}")

    if SALVAR_AMOSTRA and not df.empty:
        os.makedirs("output", exist_ok=True)
        caminho = f"output/amostra_{feed_id}.csv"
        df.head(LINHAS_AMOSTRA).to_csv(caminho, index=False)
        print(f"  -> amostra das {LINHAS_AMOSTRA} primeiras linhas em {caminho}")

    return df


def calcular_desconto_pct(row) -> float:
    try:
        preco = float(row.get("search_price", 0) or 0)
        preco_cheio = float(row.get("rrp_price", 0) or 0)
        if preco_cheio <= 0 or preco <= 0:
            return 0.0
        return round((1 - preco / preco_cheio) * 100, 1)
    except (ValueError, TypeError):
        return 0.0


def filtrar_ofertas(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        print("  -> feed veio vazio, nada a filtrar")
        return df

    faltando = [c for c in ("product_name", "search_price") if c not in df.columns]
    if faltando:
        print(f"  -> feed sem as colunas esperadas: {faltando} -- filtro abortado")
        return df.iloc[0:0]

    if "rrp_price" not in df.columns:
        print("  -> feed nao traz 'rrp_price'; sem preco 'de' o desconto fica 0")
        df["rrp_price"] = 0

    df["desconto_pct"] = df.apply(calcular_desconto_pct, axis=1)

    nome_lower = df["product_name"].fillna("").str.lower()
    tem_palavra_chave = nome_lower.apply(
        lambda nome: any(p in nome for p in PALAVRAS_CHAVE)
    )
    tem_desconto = df["desconto_pct"] >= DESCONTO_MINIMO_PCT

    # diagnostico por etapa: mostra qual dos dois filtros esta zerando o resultado
    com_rrp = (pd.to_numeric(df["rrp_price"], errors="coerce").fillna(0) > 0).sum()
    print(
        f"  -> diagnostico: {com_rrp}/{len(df)} linhas tem rrp_price preenchido | "
        f"{int(tem_desconto.sum())} passam no desconto >= {DESCONTO_MINIMO_PCT}% | "
        f"{int(tem_palavra_chave.sum())} batem alguma palavra-chave | "
        f"{int((tem_desconto & tem_palavra_chave).sum())} passam nos dois"
    )

    filtrado = df[tem_desconto & tem_palavra_chave].copy()

    filtrado = filtrado.sort_values("desconto_pct", ascending=False)
    return filtrado.head(MAX_OFERTAS_POR_LOJA)


def montar_saida(df: pd.DataFrame) -> list:
    ofertas = []
    for _, row in df.iterrows():
        ofertas.append({
            "nome": row.get("product_name"),
            "loja": row.get("merchant_name"),
            "categoria": row.get("merchant_category"),
            "preco": row.get("search_price"),
            "preco_original": row.get("rrp_price"),
            "desconto_pct": row.get("desconto_pct"),
            "link_afiliado": row.get("aw_deep_link"),
            "imagem": row.get("aw_image_url"),
        })
    return ofertas


def main():
    validar_config()
    feed_ids = [f.strip() for f in FEED_IDS.split(",") if f.strip()]

    todas_ofertas = []
    falhas = 0
    for feed_id in feed_ids:
        try:
            df = baixar_feed(feed_id)
            filtrado = filtrar_ofertas(df)
            ofertas = montar_saida(filtrado)
            print(f"  -> {len(ofertas)} ofertas encontradas (feed {feed_id})")
            todas_ofertas.extend(ofertas)
        except Exception as e:
            falhas += 1
            print(f"  -> ERRO ao processar feed {feed_id}: {type(e).__name__}: {e}")

    resultado = {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "total_ofertas": len(todas_ofertas),
        "ofertas": todas_ofertas,
    }

    os.makedirs("output", exist_ok=True)
    caminho_saida = "output/ofertas.json"
    with open(caminho_saida, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    print(f"\nConcluido: {len(todas_ofertas)} ofertas salvas em {caminho_saida}")

    # falha o job se nenhuma loja foi baixada com sucesso -- assim um token
    # invalido aparece como run vermelho, e nao como "0 ofertas" silencioso
    if falhas == len(feed_ids):
        print(
            "Todos os feeds falharam no download. Verifique se AWIN_PRODUCTDATA_KEY\n"
            "e a chave do Product Feed (nao o token da Publisher API) e se os\n"
            "Feed IDs estao corretos -- rode `python listar_feeds.py`."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
