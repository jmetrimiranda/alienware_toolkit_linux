"""Conversa com o Alienware AW720M pelo hidraw do Linux.

O mouse (ou o dongle 2.4G) tem 3 interfaces HID:
  0 = mouse, 1 = teclado (botões programáveis), 2 = fabricante (0xFF00, 64 bytes).
Todos os comandos de configuração passam pela interface 2.

Protocolo usado aqui: "APIv7" do alienfx-tools (T-Troll), confirmado no AW610M.
No AW720M ainda é EXPERIMENTAL: as funções de envio estão marcadas como tal.
"""

import glob
import os
import select
import time

VENDOR = 0x413C
PRODUTOS = {0x3029: "dongle 2.4G", 0x3028: "cabo USB-C"}
TAMANHO = 64  # bytes de cada relatório da interface 2

# Comandos APIv7 (alienfx-tools, alienfx-controls.h), já sem o byte de report ID
CMD_STATUS = bytes([0x40, 0x03, 0x01, 0x00, 0x01])
CMD_CONTROLE = bytes([0x40, 0x10, 0x0C, 0x00])  # + efeito, brilho, zona, R, G, B, R2, G2, B2
CMD_ATUALIZAR = bytes([0x40, 0x60, 0x07, 0x00, 0xC0, 0x4E, 0x00, 0x01])

# Efeitos (v7OpCodes do alienfx-tools)
EFEITOS = {"fixo": 1, "respirar": 2, "transição": 3, "espectro": 4, "pulsar": 5, "arco-íris": 6}

# Zonas do AW610M no alienfx-tools: 0 = luz, 1 = logo. No AW720M ainda não foi confirmado.
ZONAS = {"luz (0)": 0, "logo (1)": 1}


class SemPermissao(Exception):
    """O /dev/hidrawN existe, mas o usuário não pode abrir (falta a regra udev)."""


def achar():
    """Procura as interfaces do AW720M.

    Retorna {"caminho", "caminho_mouse", "modo", "pid"} ou None se não estiver conectado.
    caminho = interface de fabricante (comandos); caminho_mouse = interface 0 (movimento).
    """
    achado = {}
    for pasta in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        with open(f"{pasta}/device/uevent") as f:
            uevent = f.read()
        # Exemplo de linha: HID_ID=0003:0000413C:00003029
        linha = [l for l in uevent.splitlines() if l.startswith("HID_ID=")][0]
        _, vid, pid = linha.split("=")[1].split(":")
        vid, pid = int(vid, 16), int(pid, 16)
        if vid != VENDOR or pid not in PRODUTOS:
            continue
        with open(f"{pasta}/device/report_descriptor", "rb") as f:
            descritor = f.read()
        nome = f"/dev/{os.path.basename(pasta)}"
        # Usage Page 0xFF00 (fabricante) começa com 06 00 FF; o mouse começa com 05 01 09 02
        if descritor.startswith(b"\x06\x00\xff"):
            achado.update(caminho=nome, modo=PRODUTOS[pid], pid=pid)
        elif descritor.startswith(b"\x05\x01\x09\x02"):
            achado["caminho_mouse"] = nome
    return achado if "caminho" in achado else None


def hexa(dados):
    """Mostra os bytes em hexadecimal, cortando os zeros do fim."""
    dados = bytes(dados).rstrip(b"\x00")
    return " ".join(f"{b:02x}" for b in dados) or "(só zeros)"


class Mouse:
    def __init__(self, caminho):
        self.caminho = caminho
        try:
            self.fd = os.open(caminho, os.O_RDWR | os.O_NONBLOCK)
        except PermissionError:
            raise SemPermissao(caminho)

    def fechar(self):
        os.close(self.fd)

    def ler(self, espera=0.3):
        """Lê um relatório de 64 bytes. Retorna None se nada chegar no tempo."""
        pronto, _, _ = select.select([self.fd], [], [], espera)
        if not pronto:
            return None
        return os.read(self.fd, TAMANHO)

    def esvaziar(self):
        """Descarta relatórios antigos que ficaram na fila."""
        while self.ler(0) is not None:
            pass

    def escrever(self, dados):
        """Envia um relatório. O 0x00 da frente é o report ID (o kernel tira antes de mandar)."""
        os.write(self.fd, b"\x00" + bytes(dados).ljust(TAMANHO, b"\x00"))

    def comando(self, dados, espera=0.3):
        """Envia um comando e devolve as respostas que chegarem."""
        self.esvaziar()
        self.escrever(dados)
        respostas = []
        resposta = self.ler(espera)
        while resposta is not None:
            respostas.append(resposta)
            resposta = self.ler(0.05)
        return respostas

    def escutar(self, segundos):
        """Só escuta (não envia nada). Seguro: serve para ver se o mouse manda a bateria sozinho."""
        quadros = []
        fim = time.time() + segundos
        while time.time() < fim:
            quadro = self.ler(fim - time.time())
            if quadro is not None:
                quadros.append((time.time(), quadro))
        return quadros

    # ---- EXPERIMENTAL: comandos do AW610M que ainda não foram confirmados no AW720M ----

    def status(self):
        return self.comando(CMD_STATUS)

    def definir_cor(self, r, g, b, zona=0, brilho=100, efeito="fixo", r2=0, g2=0, b2=0):
        """Brilho de 0 a 100. 'transição' usa a segunda cor (r2, g2, b2)."""
        dados = CMD_CONTROLE + bytes([EFEITOS[efeito], brilho, zona, r, g, b, r2, g2, b2])
        return self.comando(dados)


def escutar_extras_do_mouse(caminho_mouse, segundos):
    """Lê a interface 0 e junta os 5 bytes de fabricante (6 a 10) de cada movimento.

    Só leitura. Retorna {bytes_extras: quantas vezes apareceu}. Mexa o mouse enquanto roda.
    """
    try:
        fd = os.open(caminho_mouse, os.O_RDONLY | os.O_NONBLOCK)
    except PermissionError:
        raise SemPermissao(caminho_mouse)
    contagem = {}
    fim = time.time() + segundos
    while time.time() < fim:
        pronto, _, _ = select.select([fd], [], [], max(0, fim - time.time()))
        if pronto:
            relatorio = os.read(fd, 11)
            extras = relatorio[6:11]
            contagem[extras] = contagem.get(extras, 0) + 1
    os.close(fd)
    return contagem


def corrigir_cor(r, g, b, gama=2.2):
    """Deixa a cor "viva" no LED, aplicando uma curva tipo sRGB (gama) a cada canal.

    A tela mostra as cores com gama ~2.2, mas o LED do mouse é linear: um canal em 50%
    na tela (128) acende o LED a 50% de corrente, o que fica bem mais claro que na tela.
    Por isso cores pastel (#c061cb, com os 3 canais acesos) ficam esbranquiçadas no mouse.
    Com c' = 255 * (c/255) ** gama, os canais fracos caem bastante e a cor satura:
      #c061cb -> #891e9a (roxo de verdade), #00e5ff -> #00c9ff, 255 continua 255 e 0 continua 0.
    """
    return tuple(round(255 * (c / 255) ** gama) for c in (r, g, b))


def ler_energia(quadro):
    """Interpreta o aviso de energia que o mouse manda sozinho (c0 0a ...).

    Visto em 29/10/2026 ao encostar e tirar o carregador magnético:
      c0 0a 09 00 01 14 01 00 f7 02 13 02   (carregando)
      c0 0a 09 00 01 14 00 00 f8 02 13      (sem carregador)
    Byte 5 = bateria em % (0x14 = 20, a confirmar), byte 6 = 1 com o carregador conectado.
    Retorna {"bateria", "carregando", "bruto"} ou None se o quadro for outra coisa.
    """
    if len(quadro) < 7 or quadro[0] != 0xC0 or quadro[1] != 0x0A:
        return None
    return {"bateria": quadro[5], "carregando": quadro[6] == 1, "bruto": hexa(quadro)}


def bateria(respostas):
    """Procura o aviso de energia numa lista de quadros e devolve a bateria em %, ou None."""
    for quadro in respostas:
        energia = ler_energia(quadro)
        if energia:
            return energia["bateria"]
    return None
