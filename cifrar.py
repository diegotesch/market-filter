"""
cifrar.py

Cifra o dataset da pagina com uma senha.

Por que cifrar em vez de fazer uma tela de login: o GitHub Pages serve
arquivos estaticos, sem servidor. Qualquer verificacao de senha em JavaScript
e decorativa -- o visitante le o codigo-fonte ou baixa /dados.json direto,
ignorando a tela. Cifrando, o arquivo servido e inutil sem a senha.

Formato do arquivo (binario, nesta ordem):

    magic    8 bytes   b"MKTFLT01"
    salt    16 bytes   aleatorio por execucao
    iv      12 bytes   aleatorio por execucao
    ct       n bytes   AES-256-GCM(JSON comprimido com gzip), tag incluida

A compressao vem ANTES da cifra de proposito: dado cifrado e indistinguivel
de ruido e nao comprime, entao o gzip do servidor nao ajudaria em nada. Sem
isso, o download voltaria de ~210 KB para ~1,3 MB.

Derivacao da chave: PBKDF2-HMAC-SHA256, que o navegador faz nativo pela
WebCrypto -- nao precisa de biblioteca no cliente.
"""

import gzip
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

MAGIC = b"MKTFLT01"
TAMANHO_SALT = 16
TAMANHO_IV = 12

# custo da derivacao. Alto o bastante para encarecer ataque offline, baixo o
# bastante para o navegador resolver em menos de um segundo. Fica gravado no
# arquivo? Nao: e constante dos dois lados, entao mudar aqui exige mudar no
# index.html tambem.
ITERACOES = 600_000


def derivar_chave(senha: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=ITERACOES,
    )
    return kdf.derive(senha.encode("utf-8"))


def cifrar_arquivo(origem: str, destino: str, senha: str) -> dict:
    with open(origem, "rb") as fh:
        bruto = fh.read()

    comprimido = gzip.compress(bruto, compresslevel=9)

    salt = os.urandom(TAMANHO_SALT)
    iv = os.urandom(TAMANHO_IV)
    ct = AESGCM(derivar_chave(senha, salt)).encrypt(iv, comprimido, None)

    with open(destino, "wb") as fh:
        fh.write(MAGIC + salt + iv + ct)

    return {
        "original": len(bruto),
        "comprimido": len(comprimido),
        "final": os.path.getsize(destino),
    }
