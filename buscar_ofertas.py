"""
buscar_ofertas.py

Baixa os feeds de produto da Awin, atualiza o historico de precos e gera:

- historico/precos.csv  -> memoria de precos entre execucoes (commitado)
- output/ofertas.json   -> produtos cujo preco caiu em relacao ao historico
- output/panorama.md    -> visao do que existe no catalogo (lojas, faixas de
                           preco, marcas), para decidir nicho com dado na mao

Sobre a deteccao de oferta: estes feeds nao publicam 'rrp_price' (preco
cheio), entao nao existe desconto no dado bruto. O sinal e a queda em relacao
ao maior preco ja observado -- ver historico.py. Na primeira execucao nao ha
historico, logo nao ha ofertas: isso e esperado, nao e falha.

Variaveis de ambiente (ver .env.example):
- AWIN_PRODUCTDATA_KEY: chave do Product Feed (nao o token da Publisher API)
- AWIN_FEED_IDS: opcional. Se vazio, descobre sozinho os feeds da regiao
  definida em AWIN_REGIAO.
- AWIN_REGIAO: regiao usada na descoberta automatica (padrao BR)
"""

import json
import os
import sys
from datetime import datetime, timezone

import awin
import exportar
import historico
import panorama

# usado na pagina estatica para remontar os links de afiliado
PUBLISHER_ID = os.getenv("AWIN_PUBLISHER_ID", "").strip()

FEED_IDS = os.getenv("AWIN_FEED_IDS", "").strip()
REGIAO = os.getenv("AWIN_REGIAO", "BR").strip().upper()
IDIOMA = os.getenv("AWIN_IDIOMA", "pt").strip()

# queda minima em relacao ao maior preco ja visto para virar "oferta"
QUEDA_MINIMA_PCT = float(os.getenv("QUEDA_MINIMA_PCT", "10"))

# produtos vistos pela primeira vez hoje nao viram oferta: nao ha com o que
# comparar, e a estreia no feed viraria "promocao" sem base nenhuma

MAX_OFERTAS = int(os.getenv("MAX_OFERTAS", "100"))

# Filtro opcional por nome do produto. Vazio (padrao) = nao filtra nada.
# PALAVRAS_CHAVE inclui, PALAVRAS_EXCLUIR remove -- exclusao vence.
# Os dois sao necessarios juntos porque so incluir nao basta: "masculino"
# tambem casa "Infantil Masculino", que e outro publico.
PALAVRAS_CHAVE = [
    p.strip().lower() for p in os.getenv("PALAVRAS_CHAVE", "").split(",") if p.strip()
]
PALAVRAS_EXCLUIR = [
    p.strip().lower() for p in os.getenv("PALAVRAS_EXCLUIR", "").split(",") if p.strip()
]

# faixa de preco opcional (0 = sem limite)
PRECO_MIN = float(os.getenv("PRECO_MIN", "0"))
PRECO_MAX = float(os.getenv("PRECO_MAX", "0"))


def descobrir_feeds() -> list[dict]:
    """Escolhe quais feeds baixar: os de AWIN_FEED_IDS, ou os da regiao."""
    todos = awin.listar_feeds()
    print(f"Lista de feeds: {len(todos)} disponiveis na conta")

    if FEED_IDS:
        desejados = {f.strip() for f in FEED_IDS.split(",") if f.strip()}
        escolhidos = [f for f in todos if f.get("Feed ID", "").strip() in desejados]
        nao_achados = desejados - {f.get("Feed ID", "").strip() for f in escolhidos}
        if nao_achados:
            print(f"  AVISO: Feed IDs nao encontrados na lista: {sorted(nao_achados)}")
        return escolhidos

    escolhidos = [
        f for f in todos if f.get("Primary Region", "").strip().upper() == REGIAO
    ]
    print(f"  {len(escolhidos)} feed(s) da regiao {REGIAO} (descoberta automatica)")
    return escolhidos


def normalizar(linhas: list[dict], feed: dict) -> list[dict]:
    """Converte linhas cruas do feed no formato interno."""
    feed_id = feed.get("Feed ID", "").strip()
    produtos = []
    for linha in linhas:
        pid = (linha.get("aw_product_id") or "").strip()
        if not pid:
            continue
        produtos.append({
            "produto_id": pid,
            "feed_id": feed_id,
            "merchant_id": (linha.get("merchant_id") or "").strip(),
            "loja": (linha.get("merchant_name") or feed.get("Advertiser Name", "")).strip(),
            "nome": (linha.get("product_name") or "").strip(),
            "marca": (linha.get("brand_name") or "").strip(),
            "categoria": (linha.get("category_name") or linha.get("merchant_category") or "").strip(),
            "preco": awin.preco(linha),
            "em_estoque": (linha.get("in_stock") or "").strip(),
            "link_afiliado": (linha.get("aw_deep_link") or "").strip(),
            "imagem": (linha.get("aw_image_url") or "").strip(),
        })
    return produtos


def aplicar_filtros(produtos: list[dict]) -> list[dict]:
    """Aplica inclusao por palavra-chave, exclusao e faixa de preco."""
    if not (PALAVRAS_CHAVE or PALAVRAS_EXCLUIR or PRECO_MIN or PRECO_MAX):
        return produtos

    antes = len(produtos)
    passo = produtos

    if PALAVRAS_CHAVE:
        passo = [
            p for p in passo
            if any(chave in p["nome"].lower() for chave in PALAVRAS_CHAVE)
        ]
        print(f"Filtro incluir: {len(passo)}/{antes} produtos")

    if PALAVRAS_EXCLUIR:
        depois = [
            p for p in passo
            if not any(termo in p["nome"].lower() for termo in PALAVRAS_EXCLUIR)
        ]
        print(f"Filtro excluir: removeu {len(passo) - len(depois)} produtos")
        passo = depois

    if PRECO_MIN or PRECO_MAX:
        depois = [
            p for p in passo
            if p["preco"] >= PRECO_MIN and (not PRECO_MAX or p["preco"] <= PRECO_MAX)
        ]
        print(f"Filtro de preco: {len(depois)}/{len(passo)} produtos na faixa")
        passo = depois

    return passo


def montar_ofertas(registros: dict, produtos: list[dict]) -> list[dict]:
    """Cruza o historico com os produtos de hoje e devolve as quedas de preco."""
    por_id = {p["produto_id"]: p for p in produtos}
    ofertas = []

    for pid, reg in registros.items():
        atual = por_id.get(pid)
        if atual is None:  # produto nao veio no feed de hoje
            continue
        if not historico.ja_conhecido(reg):
            continue

        queda = historico.queda_pct(reg)
        if queda < QUEDA_MINIMA_PCT:
            continue

        ofertas.append({
            "nome": atual["nome"],
            "loja": atual["loja"],
            "marca": atual["marca"],
            "categoria": atual["categoria"],
            "preco": reg["preco_atual"],
            "preco_maximo_visto": reg["preco_max"],
            "preco_minimo_visto": reg["preco_min"],
            "queda_pct": queda,
            "acompanhado_desde": reg["primeira_vez"],
            "preco_mudou_em": reg["ultima_alteracao"],
            "link_afiliado": atual["link_afiliado"],
            "imagem": atual["imagem"],
        })

    ofertas.sort(key=lambda o: o["queda_pct"], reverse=True)
    return ofertas[:MAX_OFERTAS]


def main():
    try:
        feeds = descobrir_feeds()
    except awin.AwinError as e:
        print(f"ERRO: {e}")
        sys.exit(1)

    if not feeds:
        print("Nenhum feed selecionado. Ajuste AWIN_FEED_IDS ou AWIN_REGIAO.")
        sys.exit(1)

    todos_produtos = []
    falhas = 0
    for feed in feeds:
        fid = feed.get("Feed ID", "").strip()
        nome = feed.get("Advertiser Name", "?")
        try:
            linhas = awin.baixar_feed(fid, idioma=IDIOMA)
            produtos = normalizar(linhas, feed)
            print(f"  feed {fid:>7} | {nome[:34]:34} | {len(produtos):>7} produtos")
            todos_produtos.extend(produtos)
        except Exception as e:
            falhas += 1
            print(f"  feed {fid:>7} | {nome[:34]:34} | ERRO {type(e).__name__}: {e}")

    if falhas == len(feeds):
        print("\nTodos os feeds falharam. Verifique AWIN_PRODUCTDATA_KEY.")
        sys.exit(1)

    print(f"\nTotal coletado: {len(todos_produtos)} produtos")

    # O historico guarda TUDO, de proposito: os filtros de nicho sao aplicados
    # so na hora de montar as ofertas. Assim, mudar de nicho depois nao joga
    # fora os precos ja acumulados -- e o historico e o unico ativo do projeto
    # que nao da para reconstruir.
    registros = historico.carregar()
    primeira_execucao = not registros
    resumo = historico.atualizar(registros, todos_produtos)
    historico.salvar(registros)
    print(
        f"Historico: {resumo['total']} produtos acompanhados "
        f"({resumo['novos']} novos, {resumo['mudaram']} mudaram de preco)"
    )

    do_nicho = aplicar_filtros(todos_produtos)
    ofertas = montar_ofertas(registros, do_nicho)

    os.makedirs("output", exist_ok=True)
    with open("output/ofertas.json", "w", encoding="utf-8") as fh:
        json.dump({
            "gerado_em": datetime.now(timezone.utc).isoformat(),
            "criterio": (
                f"queda >= {QUEDA_MINIMA_PCT}% em relacao ao maior preco ja "
                f"observado, para produtos conhecidos antes de hoje"
            ),
            "produtos_acompanhados": resumo["total"],
            "produtos_no_nicho": len(do_nicho),
            "total_ofertas": len(ofertas),
            "ofertas": ofertas,
        }, fh, ensure_ascii=False, indent=2)

    panorama.gerar(todos_produtos, feeds, "output/panorama.md")

    # dataset da pagina estatica: sempre o catalogo inteiro, porque os filtros
    # de nicho la sao interativos
    resumo_site = exportar.gerar(
        todos_produtos, registros, "output/dados.json", publisher=PUBLISHER_ID
    )
    print(
        f"Dataset da pagina: {resumo_site['produtos']} produtos, "
        f"{resumo_site['lojas']} lojas, {resumo_site['marcas']} marcas "
        f"({resumo_site['bytes'] / 1024:.0f} KB)"
    )

    print(f"\n{len(ofertas)} oferta(s) em output/ofertas.json")
    print("Panorama do catalogo em output/panorama.md")

    if primeira_execucao:
        print(
            "\nEsta foi a primeira execucao: o historico acabou de ser criado, "
            "entao ainda nao ha com o que comparar precos. As ofertas comecam "
            "a aparecer a partir da proxima rodada."
        )


if __name__ == "__main__":
    main()
