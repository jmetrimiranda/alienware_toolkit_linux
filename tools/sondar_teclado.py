#!/usr/bin/env python3
"""Linha de comando para o teclado SINO WEALTH 258a:002a. SÓ LEITURA (GET_FEATURE).

  python3 sondar_teclado.py info                 mostra o aparelho (sysfs, não abre nada)
  python3 sondar_teclado.py ler [rótulo]         lê os reports 5, 9, 10, 11 e 12 e salva em dados/
  python3 sondar_teclado.py backup               igual a 'ler', com o prefixo 'backup'
  python3 sondar_teclado.py comparar A.json B.json   mostra os bytes que mudaram entre duas leituras

Para mapear os bytes sem escrever nada no teclado:
  1) ler antes;  2) mude a luz pelas teclas Fn do próprio teclado;  3) ler depois;  4) comparar.
"""

import os
import sys

# O módulo do teclado fica na pasta do app (alienware-command-center-linux/)
PASTA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alienware-command-center-linux")
sys.path.insert(0, PASTA)

import teclado_sinowealth as tk  # noqa: E402

DADOS = os.path.join(PASTA, "dados")


def info():
    i = tk.achar()
    if i is None:
        print("teclado 258a:002a não encontrado")
        return 1
    for chave, valor in i.items():
        if chave != "descritor":
            print(f"{chave:16s} {valor}")
    return 0


def ler(prefixo="leitura"):
    leitura = tk.ler_config()
    # Segunda leitura logo em seguida: mostra se algum byte muda sozinho (contador, estado volátil)
    segunda = tk.ler_config()
    arquivo = tk.salvar_leitura(leitura, DADOS, prefixo)
    print(f"salvo em {arquivo}")
    for rid, item in tk.interpretar_config(leitura).items():
        if "erro" in item:
            print(f"report {rid:2d}: ERRO {item['erro']}")
            continue
        print(f"report {rid:2d}: {item['tamanho']:4d} bytes (esperado {item['esperado']}), "
              f"zeros {item['zeros']}, ff {item['ff']}, faixas {item['faixas'][:6]}"
              f"{' ...' if len(item['faixas']) > 6 else ''}")
        print(f"           início: {item['inicio']}")
    mudou = tk.comparar(leitura, segunda)
    print("2ª leitura idêntica" if not mudou else f"bytes que mudaram sozinhos: {mudou}")
    return 0


def comparar(a, b):
    mudancas = tk.comparar(tk.carregar_leitura(a), tk.carregar_leitura(b))
    if not mudancas:
        print("nenhuma diferença")
    for rid, lista in mudancas.items():
        print(f"report {rid}: {len(lista)} byte(s) diferentes")
        for pos, x, y in lista[:80]:
            print(f"  [{pos:4d}] {x if x is None else f'{x:02x}'} -> {y if y is None else f'{y:02x}'}")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:] or ["info"]
    try:
        if args[0] == "info":
            sys.exit(info())
        if args[0] in ("ler", "backup"):
            sys.exit(ler(args[1] if len(args) > 1 else args[0].replace("ler", "leitura")))
        if args[0] == "comparar" and len(args) == 3:
            sys.exit(comparar(args[1], args[2]))
    except tk.SemPermissao as erro:
        print(f"{erro}. Instale 70-alienware-toolkit.rules e replugue o teclado (ou udevadm trigger).")
        sys.exit(2)
    except FileNotFoundError as erro:
        print(f"teclado não encontrado ({erro})")
        sys.exit(2)
    print(__doc__)
    sys.exit(1)
