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

- A miniatura usa 'aw_image_url' (proxy da Awin, 200x200) e nao
  'merchant_image_url' (CDN da loja). A URL do proxy e o dobro do tamanho e
  carrega um hash que nao comprime, mas a imagem servida tem ~5,9 KB contra
  ~84 KB do arquivo original da loja. Medido para 100 produtos na tela:
  1,2 MB de trafego total com o proxy, 8,7 MB com a URL da loja. O JSON maior
  se paga com folga.
  O prefixo comum de cada loja ainda e guardado uma vez so, o que corta o
  dataset de 3.355 KB para 2.256 KB antes da compressao.
"""

import collections
import json
import os
import re
import unicodedata

# termos que definem o publico a partir do nome do produto. A ordem importa:
# "Tenis Infantil Masculino" e infantil, nao masculino.
AMOSTRA_PREFIXO = 100  # quantos caracteres definem o "mesmo padrao de URL"

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


def _afiliado(status: str) -> bool:
    """
    A Awin marca o vinculo como 'active' quando o programa foi aceito, e
    'Not Joined' quando nao. Outros estados (pending, rejected) tambem podem
    aparecer, entao a regra e: so 'active' conta como afiliado.
    """
    return status.strip().lower() == "active"


def _prefixos_de_imagem(produtos: list) -> dict:
    """
    Prefixo de imagem mais frequente em cada loja.

    Nao usa o prefixo comum a TODAS as URLs: basta um produto hospedado em
    outro dominio para o prefixo comum encolher para "https://" e a economia
    evaporar. Pegando o diretorio mais frequente, o caso geral fica curto e o
    punhado de excecoes guarda a URL inteira.
    """
    por_loja = {}
    for p in produtos:
        img = p.get("imagem") or ""
        if img:
            por_loja.setdefault(p["loja"], []).append(img)

    prefixos = {}
    for loja, urls in por_loja.items():
        # Agrupa pelo inicio da URL e usa so o maior grupo. O prefixo comum a
        # TODAS as URLs encolheria para "https://" por causa de um punhado de
        # excecoes; olhando so o grupo dominante, o prefixo fica longo e as
        # excecoes guardam a URL inteira.
        grupos = collections.Counter(url[:AMOSTRA_PREFIXO] for url in urls)
        dominante, quantas = grupos.most_common(1)[0]
        if quantas < len(urls) * 0.5:
            prefixos[loja] = ""
            continue

        # nao corta em '/': nas URLs do proxy da Awin as barras vem
        # codificadas como %2F, e exigir '/' literal descartaria a maior parte
        # do prefixo comum
        comum = os.path.commonprefix(
            [u for u in urls if u.startswith(dominante)]
        )
        prefixos[loja] = comum if len(comum) > 16 else ""
    return prefixos


def _sufixo_imagem(url: str, prefixo: str) -> str:
    """O que sobra da URL depois do prefixo da loja. Vazio se nao houver imagem."""
    if not url:
        return ""
    return url[len(prefixo):] if prefixo and url.startswith(prefixo) else url


def gerar(
    produtos: list,
    registros: dict,
    caminho: str,
    publisher: str = "",
    feeds: list = None,
) -> dict:
    """
    Monta o dataset. 'produtos' e a coleta de hoje; 'registros' e o historico,
    de onde vem o minimo/maximo ja observado e a queda atual; 'feeds' traz a
    situacao de afiliacao de cada loja.
    """
    # feed_id -> se o programa foi aceito
    afiliacao = {
        f.get("Feed ID", "").strip(): _afiliado(f.get("Membership Status", ""))
        for f in (feeds or [])
    }

    # As imagens de uma mesma loja compartilham um prefixo longo (dominio do
    # CDN + caminho da loja). Guardar o prefixo uma vez por loja e so o sufixo
    # em cada produto corta a maior parte do custo de incluir thumbnails.
    prefixos = _prefixos_de_imagem(produtos)

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
                "afiliado": afiliacao.get(p["feed_id"], False),
                "img_prefixo": prefixos.get(chave_loja, ""),
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
            _sufixo_imagem(p.get("imagem") or "", prefixos.get(chave_loja, "")),
        ])

    dados = {
        "publisher": publisher,
        "campos": [
            "id", "loja", "marca", "nome",
            "preco", "preco_min", "preco_max", "queda", "genero", "desde",
            "img",
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
