"""
historico.py

Mantem o historico de precos entre execucoes.

Por que isso existe: os feeds da Awin usados aqui nao publicam 'rrp_price'
(preco cheio), entao nao ha como calcular desconto olhando so a foto de hoje.
A alternativa e guardar o que ja vimos e comparar -- o workflow roda todo dia,
entao o historico se forma sozinho.

O arquivo e um CSV ordenado por id de produto, um produto por linha. Formato
escolhido para o diff do git ficar legivel: quando um preco muda, muda uma
linha so.
"""

import csv
import os
from datetime import date

CAMINHO_PADRAO = "historico/precos.csv"

CAMPOS = [
    "produto_id",
    "feed_id",
    "loja",
    "nome",
    "preco_atual",
    "preco_anterior",
    "preco_min",
    "preco_max",
    "primeira_vez",
    "ultima_vez",
    "observacoes",
]


def carregar(caminho: str = CAMINHO_PADRAO) -> dict:
    """Le o historico. Devolve {} se ainda nao existe (primeira execucao)."""
    if not os.path.exists(caminho):
        return {}

    with open(caminho, newline="", encoding="utf-8") as fh:
        registros = {}
        for linha in csv.DictReader(fh):
            for campo in ("preco_atual", "preco_anterior", "preco_min", "preco_max"):
                linha[campo] = float(linha[campo] or 0)
            linha["observacoes"] = int(linha["observacoes"] or 0)
            registros[linha["produto_id"]] = linha
    return registros


def salvar(registros: dict, caminho: str = CAMINHO_PADRAO) -> None:
    os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
    with open(caminho, "w", newline="", encoding="utf-8") as fh:
        escritor = csv.DictWriter(fh, fieldnames=CAMPOS)
        escritor.writeheader()
        for pid in sorted(registros):
            escritor.writerow({c: registros[pid].get(c, "") for c in CAMPOS})


def atualizar(registros: dict, produtos: list[dict], hoje: str = None) -> dict:
    """
    Aplica a observacao de hoje sobre o historico, no lugar.

    Devolve um resumo com quantos produtos sao novos e quantos mudaram de preco.
    """
    hoje = hoje or date.today().isoformat()
    novos = mudaram = 0

    for p in produtos:
        pid = p["produto_id"]
        preco = p["preco"]
        if preco <= 0:
            continue

        anterior = registros.get(pid)
        if anterior is None:
            registros[pid] = {
                "produto_id": pid,
                "feed_id": p["feed_id"],
                "loja": p["loja"],
                "nome": p["nome"],
                "preco_atual": preco,
                "preco_anterior": preco,
                "preco_min": preco,
                "preco_max": preco,
                "primeira_vez": hoje,
                "ultima_vez": hoje,
                "observacoes": 1,
            }
            novos += 1
            continue

        if preco != anterior["preco_atual"]:
            mudaram += 1
            anterior["preco_anterior"] = anterior["preco_atual"]

        anterior["preco_atual"] = preco
        anterior["preco_min"] = min(anterior["preco_min"], preco)
        anterior["preco_max"] = max(anterior["preco_max"], preco)
        anterior["ultima_vez"] = hoje
        anterior["observacoes"] += 1
        # o nome pode mudar (loja renomeia o anuncio); manter o mais recente
        anterior["nome"] = p["nome"]

    return {"novos": novos, "mudaram": mudaram, "total": len(registros)}


def queda_pct(registro: dict) -> float:
    """
    Queda percentual do preco atual em relacao ao maior preco ja observado.

    Usar o maximo historico como referencia (em vez do preco da execucao
    anterior) faz uma promocao continuar sendo detectada enquanto durar, em
    vez de sumir no dia seguinte por "nao ter mudado desde ontem".
    """
    ref = registro["preco_max"]
    atual = registro["preco_atual"]
    if ref <= 0 or atual <= 0 or atual >= ref:
        return 0.0
    return round((1 - atual / ref) * 100, 1)
