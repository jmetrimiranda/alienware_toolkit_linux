#!/usr/bin/env python3
"""Lê capturas .pcapng do USBPcap (Windows) e lista as transferências de controle HID.

Uso:
  python3 ler_pcap_usbpcap.py captura.pcapng [--todos] [--max N]

Mostra, para cada transferência de controle:
  SET_REPORT (0x21 0x09) e GET_REPORT (0xA1 0x01) com tipo/ID do report e os bytes,
  GET_DESCRIPTOR de relatório HID (0x81 0x06 wValue=0x2200) com o descritor inteiro.
Com --todos, também imprime as transferências de interrupção (teclas, etc.).

Só usa a biblioteca padrão. Não fala com nenhum aparelho: só lê o arquivo.
"""

import struct
import sys

TIPOS_REPORT = {1: "input", 2: "output", 3: "feature"}


def blocos_pcapng(dados):
    """Percorre os blocos do pcapng e devolve (linktype, bytes do pacote)."""
    pos, linktypes, ordem = 0, [], "<"
    while pos + 12 <= len(dados):
        tipo, tam = struct.unpack_from(ordem + "II", dados, pos)
        if tipo == 0x0A0D0D0A:  # Section Header: define a ordem dos bytes
            magia = dados[pos + 8:pos + 12]
            ordem = "<" if magia == b"\x4d\x3c\x2b\x1a" else ">"
            tipo, tam = struct.unpack_from(ordem + "II", dados, pos)
            linktypes = []
        elif tipo == 1:  # Interface Description
            linktypes.append(struct.unpack_from(ordem + "H", dados, pos + 8)[0])
        elif tipo == 6:  # Enhanced Packet
            iface, _, _, cap = struct.unpack_from(ordem + "IIII", dados, pos + 8)
            yield linktypes[iface] if iface < len(linktypes) else None, dados[pos + 28:pos + 28 + cap]
        elif tipo == 3:  # Simple Packet
            cap = struct.unpack_from(ordem + "I", dados, pos + 8)[0]
            yield linktypes[0] if linktypes else None, dados[pos + 12:pos + 12 + min(cap, tam - 16)]
        if tam < 12:
            break
        pos += tam


def ler_usbpcap(pacote):
    """Cabeçalho USBPcap (linktype 249). Devolve um dicionário com os campos e a carga."""
    tam_cab, irp, status, funcao, info, bus, dev, ep, transf, tam_dados = struct.unpack_from("<HQIHBHHBBI", pacote, 0)
    d = {"irp": irp, "status": status, "info": info, "bus": bus, "dev": dev, "ep": ep,
         "transf": transf, "resposta": bool(info & 1), "estagio": None}
    if transf == 2 and tam_cab >= 28:  # controle: tem o byte de estágio
        d["estagio"] = pacote[27]
    d["carga"] = pacote[tam_cab:tam_cab + tam_dados]
    return d


def hexa(b):
    return " ".join(f"{x:02x}" for x in b)


def resumir(arquivo, todos=False, maximo=0):
    dados = open(arquivo, "rb").read()
    pendentes = {}  # irp -> setup (para casar a resposta de um GET)
    n = 0
    for linktype, pacote in blocos_pcapng(dados):
        if linktype != 249 or len(pacote) < 27:
            continue
        p = ler_usbpcap(pacote)
        if p["transf"] == 2:
            if p["estagio"] == 0 and len(p["carga"]) >= 8:  # SETUP (+ dados, se OUT)
                rt, req, valor, indice, comp = struct.unpack_from("<BBHHH", p["carga"], 0)
                p["setup"] = (rt, req, valor, indice, comp)
                resto = p["carga"][8:]
                if rt == 0x21 and req == 0x09:
                    n += 1
                    print(f"[{n:04d}] dev{p['dev']} SET_REPORT {TIPOS_REPORT.get(valor >> 8, valor >> 8)} "
                          f"id=0x{valor & 0xff:02x} if={indice} len={comp}: {hexa(resto)}")
                else:
                    pendentes[p["irp"]] = p["setup"]
            elif p["estagio"] in (2, 3) or (p["estagio"] is None and p["resposta"]):
                setup = pendentes.pop(p["irp"], None)
                if not setup:
                    continue
                rt, req, valor, indice, comp = setup
                if rt == 0xA1 and req == 0x01:
                    n += 1
                    print(f"[{n:04d}] dev{p['dev']} GET_REPORT {TIPOS_REPORT.get(valor >> 8, valor >> 8)} "
                          f"id=0x{valor & 0xff:02x} if={indice} len={comp} -> {hexa(p['carga'])}")
                elif rt == 0x81 and req == 0x06 and (valor >> 8) == 0x22:
                    n += 1
                    print(f"[{n:04d}] dev{p['dev']} DESCRITOR HID if={indice} ({len(p['carga'])} bytes): "
                          f"{p['carga'].hex()}")
                elif todos:
                    print(f"       dev{p['dev']} controle rt={rt:02x} req={req:02x} v={valor:04x} i={indice} "
                          f"-> {hexa(p['carga'][:64])}")
        elif todos and p["transf"] == 1 and p["carga"]:  # interrupção
            print(f"       dev{p['dev']} int ep=0x{p['ep']:02x}: {hexa(p['carga'])}")
        if maximo and n >= maximo:
            break


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    maximo = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 0
    if "--max" in sys.argv:
        args.remove(str(maximo))
    for arq in args:
        print(f"===== {arq}")
        resumir(arq, "--todos" in sys.argv, maximo)
