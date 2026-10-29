#!/usr/bin/env python3
"""Analisa um log da escuta passiva (dados/escuta-*.log) com o parser de headset_aw725h.py.

Gera uma tabela Markdown com cada report decifrado, a contagem por tipo, a validação do checksum
e a sequência de valores por subtipo do aviso 0x09, cruzando com o contexto (contexto-*.jsonl).

Uso: analisar_escuta.py dados/escuta-AAAAMMDD-HHMMSS.log [saida.md]
"""

import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "alienware-command-center-linux"))
import headset_aw725h as hs  # noqa: E402


def ler_log(caminho):
    linhas, comentarios = [], []
    with open(caminho) as f:
        for linha in f:
            if linha.startswith("#"):
                comentarios.append(linha.strip())
                continue
            partes = linha.rstrip("\n").split("\t")
            if len(partes) >= 4:
                linhas.append((partes[0], float(partes[1]), int(partes[2]), bytes.fromhex(partes[3].replace(" ", ""))))
    return linhas, comentarios


def ler_contexto(caminho_log):
    caminho = caminho_log.replace("escuta-", "contexto-").replace(".log", ".jsonl")
    try:
        with open(caminho) as f:
            return [json.loads(l) for l in f if l.strip()]
    except OSError:
        return []


def main():
    log = sys.argv[1]
    saida = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(log), "analise-escuta.md")
    reports, comentarios = ler_log(log)
    contexto = ler_contexto(log)
    duracao = contexto[-1]["t"] if contexto else (reports[-1][1] if reports else 0)

    out = [f"# Análise da escuta passiva ({os.path.basename(log)})", ""]
    out += [f"- {c.lstrip('# ')}" for c in comentarios]
    out.append(f"- Duração coberta pelo contexto: {duracao / 60:.1f} min; reports recebidos: {len(reports)}")
    contagem = {}
    for _, _, rid, _ in reports:
        contagem[rid] = contagem.get(rid, 0) + 1
    out.append(f"- Por report id: {contagem or 'nenhum'}")
    ok = sum(1 for *_, d in reports if d[0] == 8 and hs.checksum_ok(d))
    total8 = contagem.get(8, 0)
    out.append(f"- Report 8 com checksum XOR válido: {ok} de {total8}")
    out.append("")
    out.append("| Hora | t (s) | Bytes | Decifrado |")
    out.append("|---|---|---|---|")
    series = {}
    anterior = {}
    for hora, t, rid, dados in reports:
        ev = hs.interpretar(dados)
        out.append(f"| {hora} | {t:.1f} | `{dados.hex(' ')}` | {ev.descricao} |")
        if rid == 8 and len(dados) >= 7 and dados[2] == 0x09:
            sub, valor = dados[5], dados[6]
            intervalo = t - anterior[sub] if sub in anterior else None
            anterior[sub] = t
            series.setdefault(sub, []).append((hora, valor, intervalo))
    out.append("")
    for sub, valores in sorted(series.items()):
        nome = {1: "subtipo 01 (dois estados, a decifrar)", 2: "subtipo 02 (bateria %)"}.get(sub, f"subtipo {sub:02x}")
        texto = ", ".join(f"{h[:8]}={f'0x{v:02x}' if sub == 1 else v}"
                          + (f" (+{i:.1f} s)" if i else "") for h, v, i in valores)
        out.append(f"- **{nome}**: {texto}")
    if contexto:
        pcm = sorted({c.get("pcm0p") for c in contexto})
        mic = sorted({c.get("pcm0c") for c in contexto})
        vol = sorted({c.get("PCM Playback Volume") for c in contexto})
        out.append(f"- Contexto: PCM de saída {pcm}, captura {mic}, volume do mixer {vol}")
    with open(saida, "w") as f:
        f.write("\n".join(out) + "\n")
    print("\n".join(out))
    print("salvo em", saida)


if __name__ == "__main__":
    main()
