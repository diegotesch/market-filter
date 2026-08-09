"""
exportar.py

Gera o dataset consumido pela pagina estatica (GitHub Pages).

O formato e propositalmente compacto: sao ~11,5 mil produtos e o navegador
baixa tudo de uma vez para filtrar no cliente. Duas escolhas fazem a maior
diferenca no peso:

- Loja e marca viram indices para listas separadas, em vez de repetir a
  string em todo produto.
- O link de afiliado nao e armazenado. Todo link do feed segue o mesmo
  padrao (awin1.com/pclick.php?p=<produto>&a=<publisher>&m=<merchant>),
  entao a pagina remonta a URL a partir do id do produto e do merchant da
  loja. Isso sozinho economiza uns 700 KB.

A URL da imagem ficou de fora: tem ~280 caracteres com um hash nao derivavel,
o que somaria mais de 3 MB. A pagina e ferramenta de filtro, nao vitrine.
"""

import json
import os
import re
import unicodedata

# termos que definem o publico a partir do nome do produto. A ordem importa:
# "Tenis Infantil Masculino" e infantil, nao masculino.
GENEROS = [
    ("i", ("infantil", "menino", "menina", "bebe", "juvenil", "kids", "baby")),
    ("m", ("masculin",)),
    ("f", ("feminin",)),
]


def _sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto.lower())
        if unicodedata.category(c) != "Mn"
    )


def genero(nome: str) -> str:
    limpo = _sem_acento(nome)
    for codigo, termos in GENEROS:
        if any(t in limpo for t in termos):
            return codigo
    return "u"  # indefinido / unissex


def _merchant(produto: dict) -> str:
    """Merchant id, do campo proprio ou extraido do link de afiliado."""
    if produto.get("merchant_id"):
        return produto["merchant_id"]
    achado = re.search(r"[?&]m=(\d+)", produto.get("link_afiliado") or "")
    return achado.group(1) if achado else ""


def gerar(produtos: list, registros: dict, caminho: str, publisher: str = "") -> dict:
    """
    Monta o dataset. 'produtos' e a coleta de hoje; 'registros' e o historico,
    de onde vem o minimo/maximo ja observado e a queda atual.
    """
    lojas, indice_loja = [], {}
    marcas, indice_marca = [], {}
    linhas = []

    for p in produtos:
        if p["preco"] <= 0:
            continue

        chave_loja = p["loja"]
        if chave_loja not in indice_loja:
            indice_loja[chave_loja] = len(lojas)
            lojas.append({
                "nome": chave_loja,
                "merchant": _merchant(p),
                "feed": p["feed_id"],
            })

        marca = p.get("marca") or ""
        if marca not in indice_marca:
            indice_marca[marca] = len(marcas)
            marcas.append(marca)

        reg = registros.get(p["produto_id"], {})
        preco_min = reg.get("preco_min", p["preco"])
        preco_max = reg.get("preco_max", p["preco"])
        queda = 0.0
        if preco_max > 0 and p["preco"] < preco_max:
            queda = round((1 - p["preco"] / preco_max) * 100, 1)

        linhas.append([
            p["produto_id"],
            indice_loja[chave_loja],
            indice_marca[marca],
            p["nome"],
            round(p["preco"], 2),
            round(preco_min, 2),
            round(preco_max, 2),
            queda,
            genero(p["nome"]),
            reg.get("primeira_vez", ""),
        ])

    dados = {
        "publisher": publisher,
        "campos": [
            "id", "loja", "marca", "nome",
            "preco", "preco_min", "preco_max", "queda", "genero", "desde",
        ],
        "lojas": lojas,
        "marcas": marcas,
        "produtos": linhas,
    }

    os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as fh:
        json.dump(dados, fh, ensure_ascii=False, separators=(",", ":"))

    return {
        "produtos": len(linhas),
        "lojas": len(lojas),
        "marcas": len(marcas),
        "bytes": os.path.getsize(caminho),
    }
