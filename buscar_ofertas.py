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
- AWIN_TOKEN: seu API token da Awin
- AWIN_PUBLISHER_ID: seu Publisher ID (aparece no painel Awin)
- AWIN_ADVERTISER_IDS: um ou mais Advertiser IDs separados por vírgula (ex: 128601)
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

AWIN_TOKEN = os.getenv("AWIN_TOKEN")
PUBLISHER_ID = os.getenv("AWIN_PUBLISHER_ID")
ADVERTISER_IDS = os.getenv("AWIN_ADVERTISER_IDS", "")

# Configuracao de filtro -- ajuste conforme seu nicho
DESCONTO_MINIMO_PCT = 20  # so entra oferta com desconto >= 20%
PALAVRAS_CHAVE = [
    "fone", "carregador", "cabo", "mouse", "teclado", "headset",
    "smartwatch", "power bank", "hub usb", "ssd", "webcam",
]
MAX_OFERTAS_POR_LOJA = 30

# URL base do datafeed da Awin.
# 'fid' = feed id / advertiser id. A Awin as vezes usa 'fid' como o proprio
# advertiser id quando a loja so tem 1 feed publicado -- confirme no painel
# em Anunciante > Ferramentas > Feed de produtos, se o fid for diferente do
# advertiser id, ajuste aqui.
FEED_URL_TEMPLATE = (
    "https://productdata.awin.com/datafeed/download/apikey/{token}/"
    "language/pt/fid/{fid}/columns/aw_deep_link,product_name,"
    "search_price,merchant_name,merchant_category,description,"
    "aw_image_url,rrp_price/format/csv/delimiter/%2C/compression/gzip/"
)


def validar_config():
    faltando = []
    if not AWIN_TOKEN:
        faltando.append("AWIN_TOKEN")
    if not PUBLISHER_ID:
        faltando.append("AWIN_PUBLISHER_ID")
    if not ADVERTISER_IDS:
        faltando.append("AWIN_ADVERTISER_IDS")
    if faltando:
        print(f"Erro: variaveis faltando no .env: {', '.join(faltando)}")
        sys.exit(1)


def baixar_feed(advertiser_id: str) -> pd.DataFrame:
    url = FEED_URL_TEMPLATE.format(token=AWIN_TOKEN, fid=advertiser_id)
    print(f"Baixando feed do anunciante {advertiser_id}...")
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()

    # o feed vem comprimido em gzip; pandas descomprime automatico pela extensao,
    # entao forcamos via BytesIO + compression explicita
    df = pd.read_csv(io.BytesIO(resp.content), compression="gzip")
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
        return df

    df["desconto_pct"] = df.apply(calcular_desconto_pct, axis=1)

    nome_lower = df["product_name"].fillna("").str.lower()
    tem_palavra_chave = nome_lower.apply(
        lambda nome: any(p in nome for p in PALAVRAS_CHAVE)
    )

    filtrado = df[
        (df["desconto_pct"] >= DESCONTO_MINIMO_PCT) & tem_palavra_chave
    ].copy()

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
    advertiser_ids = [a.strip() for a in ADVERTISER_IDS.split(",") if a.strip()]

    todas_ofertas = []
    for adv_id in advertiser_ids:
        try:
            df = baixar_feed(adv_id)
            filtrado = filtrar_ofertas(df)
            ofertas = montar_saida(filtrado)
            print(f"  -> {len(ofertas)} ofertas encontradas (loja {adv_id})")
            todas_ofertas.extend(ofertas)
        except Exception as e:
            print(f"  -> erro ao processar loja {adv_id}: {e}")

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


if __name__ == "__main__":
    main()
