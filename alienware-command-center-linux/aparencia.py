"""Cor do aparelho (corpo) de cada dispositivo, usada no visualizador 3D.

Guardada em ~/.config/alienware-toolkit/aparencia.json, por exemplo:
    {"mouse": "preto", "headset": "preto", "teclado": "#3a0ca3"}
Valores: "preto" (Dark Side of the Moon), "branco" (Lunar Light) ou uma cor "#rrggbb" (personalizada).
Padrão: preto para todos (o AW725H "Dark Side of the Moon" e o K617-R-B, "B" de black, são pretos).
"""

import json
import os

ARQUIVO = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
                       "alienware-toolkit", "aparencia.json")

# Nomes oficiais da Dell para as duas cores dos periféricos Alienware
OPCOES = {"preto": ("Dark Side of the Moon", "#202226"), "branco": ("Lunar Light", "#dcdfe2")}
APARELHOS = {"mouse": "Mouse AW720M", "headset": "Headset AW725H", "teclado": "Teclado K617 Fizz"}
PADRAO = "preto"

# Quem quiser saber quando a cor muda (as páginas com 3D) se registra aqui: funcao(aparelho, hex)
ouvintes = []


def ler():
    """Dicionário {aparelho: valor} com todos os aparelhos (faltando = padrão)."""
    try:
        with open(ARQUIVO) as f:
            dados = json.load(f)
    except (OSError, ValueError):
        dados = {}
    return {a: dados.get(a, PADRAO) for a in APARELHOS}


def cor_hex(aparelho):
    """Cor do corpo em '#rrggbb' para o 3D."""
    valor = ler()[aparelho]
    return OPCOES[valor][1] if valor in OPCOES else valor


def definir(aparelho, valor):
    """Grava 'preto', 'branco' ou '#rrggbb' e avisa as páginas abertas."""
    dados = ler()
    dados[aparelho] = valor
    os.makedirs(os.path.dirname(ARQUIVO), exist_ok=True)
    with open(ARQUIVO, "w") as f:
        json.dump(dados, f, indent=2)
    for funcao in ouvintes:
        funcao(aparelho, cor_hex(aparelho))
