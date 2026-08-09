"""
historico.py

Mantem o historico de precos entre execucoes.

Por que isso existe: os feeds da Awin usados aqui nao publicam 'rrp_price'
(preco cheio), entao nao ha como calcular desconto olhando so a foto de hoje.
A alternativa e guardar o que ja vimos e comparar -- o workflow roda todo dia,
entao o historico se forma sozinho.

O arquivo e um CSV ordenado por id de produto, um produto por linha.

Nenhum campo registra "visto hoje": se registrasse, toda linha mudaria em toda
execucao e o commit diario viraria 11 mil linhas de ruido. Aqui uma linha so
muda quando o preco muda, entao o diff do git mostra exatamente as variacoes
de preco do dia -- que e a informacao que interessa.
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
    "ultima_alteracao",
]

NUMERICOS = ("preco_atual", "preco_anterior", "preco_min", "preco_max")


def carregar(caminho: str = CAMINHO_PADRAO) -> dict:
    """Le o historico. Devolve {} se ainda nao existe (primeira execucao)."""
    if not os.path.exists(caminho):
        return {}

    registros = {}
    with open(caminho, newline="", encoding="utf-8") as fh:
        for linha in csv.DictReader(fh):
            for campo in NUMERICOS:
                linha[campo] = float(linha[campo] or 0)
            # migracao do formato antigo, que tinha 'ultima_vez'/'observacoes'
            if not linha.get("ultima_alteracao"):
                linha["ultima_alteracao"] = (
                    linha.get("ultima_vez") or linha.get("primeira_vez") or ""
                )
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

        registro = registros.get(pid)

        if registro is None:
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
                "ultima_alteracao": hoje,
            }
            novos += 1
            continue

        if preco == registro["preco_atual"]:
            continue  # nada mudou: a linha fica intacta no CSV

        mudaram += 1
        registro["preco_anterior"] = registro["preco_atual"]
        registro["preco_atual"] = preco
        registro["preco_min"] = min(registro["preco_min"], preco)
        registro["preco_max"] = max(registro["preco_max"], preco)
        registro["ultima_alteracao"] = hoje
        # o nome pode mudar (loja renomeia o anuncio); manter o mais recente
        registro["nome"] = p["nome"]

    return {"novos": novos, "mudaram": mudaram, "total": len(registros)}


def ja_conhecido(registro: dict, hoje: str = None) -> bool:
    """
    Verdadeiro se ja conheciamos o produto antes de hoje.

    Substitui uma contagem de observacoes: serve para nao tratar como promocao
    a estreia de um produto no feed, sem precisar de um contador que mudaria
    toda linha do CSV a cada execucao.
    """
    hoje = hoje or date.today().isoformat()
    return registro.get("primeira_vez", hoje) < hoje


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
