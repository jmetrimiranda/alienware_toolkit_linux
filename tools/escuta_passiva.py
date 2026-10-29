#!/usr/bin/env python3
"""Escuta PASSIVA do canal de fabricante do dongle Alienware AW725H (413c:ab2b, interface 1.3).

Só lê: o hidraw é aberto com O_RDONLY, então é impossível escrever no report 6
ou mandar qualquer coisa ao dongle por aqui.

Grava em <saida>/:
  escuta-AAAAMMDD-HHMMSS.log    uma linha por report: horário, segundos desde o início, id, hex
  contexto-AAAAMMDD-HHMMSS.jsonl a cada 15 s: estado do PCM, mixer ALSA e reconexões (para cruzar)

Uso: escuta_passiva.py [--minutos 25] [--espera-permissao 30] [--saida dados]
"""

import argparse
import errno
import json
import os
import select
import subprocess
import time

USB_ID = ("413C", "AB2B")


def achar_hidraw():
    """Devolve /dev/hidrawN da interface 3 (canal de fabricante) do dongle, ou None."""
    base = "/sys/class/hidraw"
    for nome in sorted(os.listdir(base)):
        try:
            with open(f"{base}/{nome}/device/uevent") as f:
                uevent = f.read()
        except OSError:
            continue
        if f"0000{USB_ID[0]}:0000{USB_ID[1]}" in uevent.upper() and "input3" in uevent:
            return f"/dev/{nome}"
    return None


def abrir_somente_leitura(caminho):
    return os.open(caminho, os.O_RDONLY | os.O_NONBLOCK)


def contexto():
    """Fotografia só-leitura do estado do áudio do dongle (para cruzar com os reports)."""
    ctx = {"hora": time.strftime("%H:%M:%S")}
    for card in sorted(os.listdir("/proc/asound")):
        usbid = f"/proc/asound/{card}/usbid"
        if card.startswith("card") and os.path.exists(usbid):
            with open(usbid) as f:
                if f.read().strip() != "413c:ab2b":
                    continue
            for pcm in ("pcm0p", "pcm0c"):
                try:
                    with open(f"/proc/asound/{card}/{pcm}/sub0/status") as f:
                        linha = f.readline().strip()
                    ctx[pcm] = linha.replace("state: ", "")
                except OSError:
                    ctx[pcm] = "?"
    saida = subprocess.run(["amixer", "-c", "Dongle", "contents"], capture_output=True, text=True).stdout
    nome = None
    for linha in saida.splitlines():
        if "name='" in linha:
            nome = linha.split("name='")[1].split("'")[0]
        elif linha.strip().startswith(": values=") and nome:
            ctx[nome] = linha.strip()[len(": values="):]
    return ctx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutos", type=float, default=25)
    ap.add_argument("--espera-permissao", type=float, default=30, help="minutos esperando a regra udev")
    ap.add_argument("--saida", default=os.path.join(os.path.dirname(__file__), "..", "alienware-command-center-linux", "dados"))
    args = ap.parse_args()
    os.makedirs(args.saida, exist_ok=True)

    # 1) espera a permissão (regra udev uaccess), checando a cada 60 s
    limite = time.time() + args.espera_permissao * 60
    fd = None
    while fd is None:
        caminho = achar_hidraw()
        try:
            if caminho:
                fd = abrir_somente_leitura(caminho)
                break
            print(time.strftime("%H:%M:%S"), "dongle não encontrado", flush=True)
        except PermissionError:
            print(time.strftime("%H:%M:%S"), f"sem permissão em {caminho}; nova tentativa em 60 s", flush=True)
        if time.time() > limite:
            print("desisti: sem permissão no tempo limite", flush=True)
            return 2
        time.sleep(60)

    carimbo = time.strftime("%Y%m%d-%H%M%S")
    log_path = os.path.join(args.saida, f"escuta-{carimbo}.log")
    ctx_path = os.path.join(args.saida, f"contexto-{carimbo}.jsonl")
    inicio = time.monotonic()
    fim = inicio + args.minutos * 60
    contagem = {}
    proximo_ctx = 0
    with open(log_path, "w") as log, open(ctx_path, "w") as ctxf:
        log.write(f"# escuta passiva {caminho} (O_RDONLY) início {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log.write("# hora\t\tt(s)\tid\tbytes (hex, inclui o report id)\n")
        log.flush()
        while time.monotonic() < fim:
            agora = time.monotonic()
            if agora >= proximo_ctx:
                ctxf.write(json.dumps({"t": round(agora - inicio, 1), **contexto()}) + "\n")
                ctxf.flush()
                proximo_ctx = agora + 15
            if fd is None:  # dongle reiniciou: procura de novo
                caminho = achar_hidraw()
                if caminho:
                    try:
                        fd = abrir_somente_leitura(caminho)
                        log.write(f"# {time.strftime('%H:%M:%S')} reaberto {caminho}\n")
                    except OSError:
                        fd = None
                time.sleep(1)
                continue
            pronto, _, _ = select.select([fd], [], [], 1.0)
            if not pronto:
                continue
            try:
                dados = os.read(fd, 64)
            except OSError as e:
                if e.errno in (errno.ENODEV, errno.EIO):
                    log.write(f"# {time.strftime('%H:%M:%S')} dongle sumiu ({e.strerror})\n")
                    log.flush()
                    os.close(fd)
                    fd = None
                    continue
                raise
            if not dados:
                continue
            t = time.monotonic() - inicio
            hora = time.strftime("%H:%M:%S") + f".{int((time.time() % 1) * 1000):03d}"
            rid = dados[0]
            contagem[rid] = contagem.get(rid, 0) + 1
            log.write(f"{hora}\t{t:8.2f}\t{rid}\t{dados.hex(' ')}\n")
            log.flush()
        log.write(f"# fim {time.strftime('%Y-%m-%d %H:%M:%S')} contagem por report id: {contagem}\n")
    print("ok", log_path, contagem, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
