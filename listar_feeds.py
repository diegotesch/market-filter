"""
listar_feeds.py

Lista os feeds de produto acessiveis pela conta, mostrando Advertiser ID e
Feed ID lado a lado -- sao numeros diferentes, e a URL de download usa o
Feed ID. Passar o Advertiser ID retorna 404.

Uso:
    python listar_feeds.py           # feeds da regiao BR
    REGIAO=todas python listar_feeds.py
"""

import os
import sys

import awin

REGIAO = os.getenv("REGIAO", "BR").strip().upper()


def numero(feed: dict) -> int:
    try:
        return int(feed.get("No of products") or 0)
    except ValueError:
        return 0


def main():
    try:
        feeds = awin.listar_feeds()
    except awin.AwinError as e:
        print(f"ERRO: {e}")
        sys.exit(1)

    print(f"{len(feeds)} feed(s) na conta.")

    if REGIAO != "TODAS":
        feeds = [f for f in feeds if f.get("Primary Region", "").strip().upper() == REGIAO]
        print(f"{len(feeds)} na regiao {REGIAO} (use REGIAO=todas para ver todos).")

    if not feeds:
        print(
            "\nNenhum feed nessa regiao. Se a conta e nova, pode ser que ainda "
            "nao haja programa com feed de produto disponivel."
        )
        return

    print()
    cab = f"{'Adv ID':>8} | {'Feed ID':>8} | {'Loja':38} | {'Reg':3} | {'Idioma':10} | {'Produtos':>9} | Status"
    print(cab)
    print("-" * len(cab))
    for f in sorted(feeds, key=numero, reverse=True):
        print(
            f"{f.get('Advertiser ID',''):>8} | {f.get('Feed ID',''):>8} | "
            f"{f.get('Advertiser Name','')[:38]:38} | "
            f"{f.get('Primary Region',''):3} | {f.get('Language','')[:10]:10} | "
            f"{numero(f):>9,} | {f.get('Membership Status','')}"
        )

    print(
        "\nUse a coluna 'Feed ID' em AWIN_FEED_IDS (separado por virgula). "
        "Deixando AWIN_FEED_IDS vazio, buscar_ofertas.py pega sozinho todos os "
        f"feeds da regiao {REGIAO}."
    )


if __name__ == "__main__":
    main()
