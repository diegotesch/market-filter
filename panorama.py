"""
panorama.py

Gera um resumo em markdown do que existe no catalogo coletado: lojas, faixas
de preco, marcas e categorias mais comuns, com exemplos de nomes de produto.

Serve para escolher nicho olhando o inventario real, em vez de partir de uma
lista de palavras-chave e descobrir depois que nao casa com nada.
"""

import collections
from datetime import datetime, timezone

FAIXAS = [
    (0, 50, "ate R$ 50"),
    (50, 100, "R$ 50 a 100"),
    (100, 250, "R$ 100 a 250"),
    (250, 500, "R$ 250 a 500"),
    (500, 1000, "R$ 500 a 1.000"),
    (1000, float("inf"), "acima de R$ 1.000"),
]


def _faixa(preco: float) -> str:
    for minimo, maximo, rotulo in FAIXAS:
        if minimo <= preco < maximo:
            return rotulo
    return "sem preco"


def _tabela(titulo: str, contagem: collections.Counter, total: int, limite=12) -> list:
    linhas = [f"## {titulo}", "", "| | Produtos | % |", "|---|---:|---:|"]
    for chave, n in contagem.most_common(limite):
        rotulo = (chave or "(vazio)")[:44]
        linhas.append(f"| {rotulo} | {n:,} | {100 * n / total:.1f}% |")
    linhas.append("")
    return linhas


def gerar(produtos: list, feeds: list, caminho: str) -> None:
    total = len(produtos)
    linhas = [
        "# Panorama do catalogo",
        "",
        f"Gerado em {datetime.now(timezone.utc).isoformat()}",
        "",
        f"- **{total:,}** produtos coletados",
        f"- **{len(feeds)}** feed(s)",
        "",
    ]

    if not total:
        linhas.append("Nenhum produto coletado.")
        with open(caminho, "w", encoding="utf-8") as fh:
            fh.write("\n".join(linhas))
        return

    com_preco = [p for p in produtos if p["preco"] > 0]
    if com_preco:
        precos = sorted(p["preco"] for p in com_preco)
        mediana = precos[len(precos) // 2]
        linhas += [
            f"- **{len(com_preco):,}** com preco valido "
            f"(mediana R$ {mediana:,.2f}, min R$ {precos[0]:,.2f}, "
            f"max R$ {precos[-1]:,.2f})",
            "",
        ]

    linhas += _tabela("Lojas", collections.Counter(p["loja"] for p in produtos), total)
    linhas += _tabela(
        "Faixas de preco",
        collections.Counter(_faixa(p["preco"]) for p in produtos),
        total,
    )

    marcas = collections.Counter(p["marca"] for p in produtos if p["marca"])
    if marcas:
        linhas += _tabela("Marcas", marcas, total)

    categorias = collections.Counter(p["categoria"] for p in produtos if p["categoria"])
    if categorias:
        linhas += _tabela("Categorias", categorias, total)

    linhas += ["## Exemplos de produto", ""]
    por_loja = collections.defaultdict(list)
    for p in produtos:
        por_loja[p["loja"]].append(p)
    for loja, itens in sorted(por_loja.items(), key=lambda kv: -len(kv[1]))[:6]:
        linhas.append(f"**{loja}**")
        linhas.append("")
        for p in itens[:5]:
            linhas.append(f"- {p['nome'][:70]} — R$ {p['preco']:,.2f}")
        linhas.append("")

    with open(caminho, "w", encoding="utf-8") as fh:
        fh.write("\n".join(linhas))
