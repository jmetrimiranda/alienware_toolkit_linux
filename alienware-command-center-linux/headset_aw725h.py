"""Headset Alienware AW725H no Linux: o que dá para fazer SEM o AWCC.

1. Leitor passivo do canal HID do dongle (413c:ab2b, interface 1.3, hidraw).
   Só lê: o arquivo é aberto com O_RDONLY, então este módulo nunca escreve no report 6
   nem manda nada ao dongle. Reports da interface (descritor de 80 bytes):
     - 0x02 (1 byte)   consumer control: volume +/-, mudo, play/pausa, próxima, anterior
     - 0x07 (61 bytes) canal de fabricante, ENTRADA (provável resposta aos comandos do report 6)
     - 0x08 (7 bytes)  canal de fabricante, ENTRADA (provável aviso que o dongle manda sozinho)
     - 0x06 (61 bytes) canal de fabricante, SAÍDA: NÃO usado aqui (protocolo desconhecido)
   No hidraw cada report chega com o byte do ID na frente (report 7 = 62 bytes, report 8 = 8).
   A interface só tem endpoint IN (0x83); o report 6 iria por SET_REPORT no endpoint de controle.
   O que já se sabe dos reports 7 e 8 está em interpretar() e em docs/aw725h-headset-linux.md.

2. Mixer de hardware do dongle via `amixer -c Dongle` (ALSA):
     'PCM Playback Volume' 0–74 (−74 a 0 dB, 1 dB por passo) e 'PCM Playback Switch'
     'Headset Capture Volume' 0–30 (−30 a 0 dB) e 'Headset Capture Switch'
   O PipeWire usa esse mesmo mixer como volume do sink, então mexer aqui também move o
   volume do GNOME (e vice-versa).

3. Monitoramento do microfone por software (o AW725H não tem sidetone de hardware exposto
   no Linux): um pw-loopback do microfone do headset para os fones, com volume próprio.

Sem GTK aqui: a interface fica em ui/abas_headset_extras.py.
"""

import errno
import json
import os
import re
import select
import subprocess
import threading
import time

USB_ID = "413c:ab2b"
CARTAO = "Dongle"  # id do cartão ALSA (o número muda quando o dongle reinicia, o nome não)

# ---------------------------------------------------------------------------
# HID: achar o hidraw e interpretar os reports
# ---------------------------------------------------------------------------

# Report 2 (consumer control): um bit por botão, na ordem do descritor
BOTOES = [(0x01, "volume +"), (0x02, "volume −"), (0x04, "mudo"),
          (0x08, "play/pausa"), (0x10, "próxima faixa"), (0x20, "faixa anterior")]


def achar_hidraw():
    """Caminho /dev/hidrawN da interface 3 (canal de fabricante) do dongle, ou None."""
    base = "/sys/class/hidraw"
    try:
        nomes = sorted(os.listdir(base))
    except OSError:
        return None
    for nome in nomes:
        try:
            with open(f"{base}/{nome}/device/uevent") as f:
                uevent = f.read().upper()
        except OSError:
            continue
        if "0000413C:0000AB2B" in uevent and "INPUT3" in uevent:
            return f"/dev/{nome}"
    return None


def tem_permissao(caminho):
    """True se o usuário pode ler o hidraw (regra udev 70-alienware-toolkit.rules instalada)."""
    return bool(caminho) and os.access(caminho, os.R_OK)


class Evento:
    """Um report recebido, já interpretado."""

    def __init__(self, dados):
        self.hora = time.strftime("%H:%M:%S")
        self.dados = bytes(dados)
        self.report = dados[0] if dados else None
        self.tipo = "desconhecido"   # botao | status | resposta | desconhecido
        self.descricao = ""
        self.valores = {}            # ex.: {"bateria": 80, "carregando": False}

    def hex(self):
        return self.dados.hex(" ")

    def __repr__(self):
        return f"<Evento {self.hora} r{self.report} {self.tipo}: {self.descricao or self.hex()}>"


def interpretar(dados):
    """Transforma os bytes de um report num Evento.

    Report 2 é padrão HID. Os reports 7 e 8 são de fabricante: aqui entra só o que foi
    observado na escuta passiva (dados/escuta-*.log); o resto é mostrado em hexadecimal.
    """
    ev = Evento(dados)
    if not dados:
        return ev
    if ev.report == 0x02 and len(dados) >= 2:
        apertados = [nome for bit, nome in BOTOES if dados[1] & bit]
        ev.tipo = "botao"
        ev.descricao = ", ".join(apertados) if apertados else "botão solto"
        ev.valores = {"botoes": apertados}
    elif ev.report == 0x08:
        ev.tipo = "status"
        ev.descricao = "aviso do dongle (report 8): " + ev.hex()
        ev.valores = interpretar_status(dados)
        if ev.valores and not checksum_ok(dados):
            ev.valores = {"aviso": ev.valores["aviso"], "carga": ev.valores["carga"], "checksum_ruim": True}
        if ev.valores:
            ev.descricao = descrever_status(ev.valores)
    elif ev.report == 0x07:
        ev.tipo = "resposta"
        ev.descricao = "canal de fabricante (report 7): " + dados[:12].hex(" ") + " …"
    return ev


def interpretar_status(dados):
    """Campos do report 8, no mesmo formato dos avisos do mouse AW720M (APIv7 da Dell):

        08 | c0 | EV | N | 00 | N bytes de dados
        id   aviso evento tamanho

    Ex.: 08 c0 09 03 00 02 1b db = aviso do evento 0x09 com 3 bytes (02 1b db).
    O significado de cada evento vem da escuta passiva (docs/aw725h-headset-linux.md, seção 3).
    """
    if len(dados) < 5 or dados[1] != 0xC0:
        return {}
    evento, tamanho = dados[2], dados[3]
    carga = bytes(dados[5:5 + tamanho])
    valores = {"aviso": evento, "carga": carga.hex(" ")}
    valores.update(EVENTOS.get(evento, lambda _c: {})(carga))
    return valores


def checksum_ok(dados):
    """O último byte do aviso é o XOR de todos os anteriores (com o 08 do ID): o XOR de tudo dá 0.
    Visto em 100% dos avisos c0 09 da escuta de 29/10/2026."""
    x = 0
    for b in dados:
        x ^= b
    return x == 0


def _evento_09(carga):
    """Aviso 0x09: 3 bytes = subtipo, valor e checksum.

    subtipo 01: só dois valores na escuta, 0xdd e depois 0xcc, em pares a 13–30 s de distância
                (duas vezes em 26 min) → evento de dois estados, significado a decifrar (candidatos:
                botão de mudo do microfone, microfone recolhido, estado do rádio)
    subtipo 02: nível da bateria em %. Usando: caiu 27 → 18 em 26 min (o dongle confere a cada ~70 s
                e só avisa quando muda). Carregando: subiu 1 ponto a cada 18 s (18 → 33+ em 3 min).
                Muda rápido demais para 750 mAh, então deve ser uma estimativa pela tensão.
    """
    if len(carga) < 2:
        return {}
    subtipo, valor = carga[0], carga[1]
    if subtipo == 0x01:
        return {"estado_01": valor}
    if subtipo == 0x02:
        return {"bateria": valor}
    return {"subtipo": subtipo, "valor": valor}


# Eventos do report 8 já observados: evento -> função que decifra os dados
EVENTOS = {0x09: _evento_09}


def descrever_status(valores):
    partes = []
    if "bateria" in valores:
        partes.append(f"bateria {valores['bateria']}%")
    if "estado_01" in valores:
        partes.append(f"aviso 01 = 0x{valores['estado_01']:02x} (a decifrar)")
    if valores.get("checksum_ruim"):
        partes.append("checksum não confere")
    if valores.get("carregando"):
        partes.append("carregando")
    if "mic_mudo" in valores:
        partes.append("microfone mudo" if valores["mic_mudo"] else "microfone ligado")
    if "conectado" in valores:
        partes.append("headset conectado" if valores["conectado"] else "headset desligado/fora de alcance")
    if not partes and "aviso" in valores:
        partes.append(f"aviso 0x{valores['aviso']:02x}: {valores['carga']}")
    return ", ".join(partes) or "status"


class LeitorPassivo(threading.Thread):
    """Thread que lê o hidraw do dongle sem nunca escrever nele.

    ao_evento(evento) é chamado na própria thread (na interface GTK, use GLib.idle_add).
    O estado mais recente fica em self.estado. Se o dongle reiniciar, o leitor espera e reabre.
    arquivo_log (opcional): grava cada report em uma linha 'hora<TAB>hex'.
    arquivo_estado (opcional): guarda a última bateria e o aviso 01 em JSON e lê de volta ao começar,
    porque o dongle só manda a bateria quando ela muda (pode levar vários minutos).
    """

    def __init__(self, ao_evento=None, arquivo_log=None, arquivo_estado=None):
        super().__init__(daemon=True, name="aw725h-leitor")
        self.ao_evento = ao_evento
        self.arquivo_log = arquivo_log
        self.arquivo_estado = arquivo_estado
        self._parar = threading.Event()
        self.estado = {"caminho": None, "permissao": None, "lendo": False, "eventos": 0,
                       "contagem": {}, "ultimo": {}, "bateria": None, "carregando": None,
                       "mic_mudo": None, "conectado": None, "estado_01": None, "hora_bateria": None,
                       "ultimo_botao": None, "erro": None}
        self._ler_estado_salvo()

    def _ler_estado_salvo(self):
        if not self.arquivo_estado:
            return
        try:
            with open(self.arquivo_estado) as f:
                salvo = json.load(f)
        except (OSError, ValueError):
            return
        for chave in ("bateria", "hora_bateria", "estado_01"):
            self.estado[chave] = salvo.get(chave)

    def _salvar_estado(self):
        if not self.arquivo_estado:
            return
        try:
            os.makedirs(os.path.dirname(self.arquivo_estado), exist_ok=True)
            with open(self.arquivo_estado, "w") as f:
                json.dump({c: self.estado[c] for c in ("bateria", "hora_bateria", "estado_01")}, f)
        except OSError:
            pass

    def parar(self):
        self._parar.set()

    def run(self):
        fd = None
        log = open(self.arquivo_log, "a") if self.arquivo_log else None
        try:
            while not self._parar.is_set():
                if fd is None:
                    fd = self._abrir()
                    if fd is None:
                        self._parar.wait(2)
                        continue
                pronto, _, _ = select.select([fd], [], [], 1.0)
                if not pronto:
                    continue
                try:
                    dados = os.read(fd, 64)
                except OSError as erro:
                    if erro.errno in (errno.ENODEV, errno.EIO):  # dongle sumiu (reinício ou desconectado)
                        os.close(fd)
                        fd = None
                        self.estado.update(lendo=False, erro="dongle desconectado")
                        continue
                    raise
                if not dados:
                    continue
                if log:
                    log.write(f"{time.strftime('%H:%M:%S')}\t{dados.hex(' ')}\n")
                    log.flush()
                self._registrar(interpretar(dados))
        finally:
            if fd is not None:
                os.close(fd)
            if log:
                log.close()

    def _abrir(self):
        caminho = achar_hidraw()
        self.estado["caminho"] = caminho
        if caminho is None:
            self.estado.update(lendo=False, erro="dongle não encontrado")
            return None
        try:
            fd = os.open(caminho, os.O_RDONLY | os.O_NONBLOCK)  # SÓ leitura, de propósito
        except PermissionError:
            self.estado.update(permissao=False, lendo=False, erro="sem permissão (instale a regra udev)")
            return None
        except OSError as erro:
            self.estado.update(lendo=False, erro=str(erro))
            return None
        self.estado.update(permissao=True, lendo=True, erro=None)
        return fd

    def _registrar(self, ev):
        e = self.estado
        e["eventos"] += 1
        e["contagem"][ev.report] = e["contagem"].get(ev.report, 0) + 1
        e["ultimo"][ev.report] = (ev.hora, ev.hex())
        for chave in ("bateria", "mic_mudo", "conectado", "estado_01"):
            if chave in ev.valores:
                e[chave] = ev.valores[chave]
        if "bateria" in ev.valores:
            # Não há aviso de carregador decifrado: subir = carregando, descer = usando
            anterior = getattr(self, "_bateria_anterior", None)
            if anterior is not None and ev.valores["bateria"] != anterior:
                e["carregando"] = ev.valores["bateria"] > anterior
            self._bateria_anterior = ev.valores["bateria"]
            e["hora_bateria"] = time.strftime("%d/%m %H:%M")
        if "bateria" in ev.valores or "estado_01" in ev.valores:
            self._salvar_estado()
        if ev.tipo == "botao" and ev.valores.get("botoes"):
            e["ultimo_botao"] = (ev.hora, ev.descricao)
        if self.ao_evento:
            self.ao_evento(ev)


# ---------------------------------------------------------------------------
# Mixer ALSA do dongle (amixer -c Dongle)
# ---------------------------------------------------------------------------

CONTROLES = {
    "volume": "PCM Playback Volume",        # 0–74 → −74 a 0 dB
    "som": "PCM Playback Switch",           # on/off (mudo de hardware dos fones)
    "mic": "Headset Capture Volume",        # 0–30 → −30 a 0 dB
    "mic_ligado": "Headset Capture Switch",  # on/off (mudo de hardware do microfone)
}


def _amixer(*args, tempo=3):
    try:
        r = subprocess.run(["amixer", "-c", CARTAO, *args], capture_output=True, text=True, timeout=tempo)
    except (OSError, subprocess.TimeoutExpired) as erro:
        return None, str(erro)
    if r.returncode != 0:
        return None, (r.stderr.strip() or f"amixer saiu com {r.returncode}")
    return r.stdout, None


def ler_mixer():
    """{'volume': 54, 'volume_max': 74, 'som': True, 'mic': 30, 'mic_max': 30, 'mic_ligado': True, 'erro': None}.

    Os valores ficam None se o dongle não estiver conectado.
    """
    saida, erro = _amixer("contents")
    resultado = {"volume": None, "volume_max": 74, "som": None, "mic": None, "mic_max": 30,
                 "mic_ligado": None, "erro": erro}
    if saida is None:
        return resultado
    # Cada controle: "numid=..,name='X'" seguido de "; type=..,max=N" e ": values=a,b"
    blocos = re.split(r"\n(?=numid=)", saida)
    for chave, nome in CONTROLES.items():
        for bloco in blocos:
            if f"name='{nome}'" not in bloco:
                continue
            valores = re.search(r": values=([^\n]+)", bloco)
            maximo = re.search(r"max=(\d+)", bloco)
            if not valores:
                continue
            primeiro = valores.group(1).split(",")[0].strip()
            if primeiro in ("on", "off"):
                resultado[chave] = primeiro == "on"
            else:
                resultado[chave] = int(primeiro)
                if maximo:
                    resultado[f"{chave}_max"] = int(maximo.group(1))
    return resultado


def definir(chave, valor):
    """Muda um controle do mixer. chave: 'volume' | 'som' | 'mic' | 'mic_ligado'. Devolve (ok, mensagem)."""
    nome = CONTROLES[chave]
    if isinstance(valor, bool):
        texto = "on" if valor else "off"
    else:
        texto = str(int(valor))
    _saida, erro = _amixer("cset", f"name={nome}", texto)
    return erro is None, erro or "ok"


def passo_para_db(passo, maximo):
    """O dongle usa 1 dB por passo e o máximo é 0 dB: 54 de 74 → −20 dB."""
    return passo - maximo


# ---------------------------------------------------------------------------
# Monitoramento do microfone por software (pw-loopback)
# ---------------------------------------------------------------------------

def nos_pipewire_aw725h():
    """Nomes (node.name) do sink e da source do dongle no PipeWire, ou None."""
    try:
        saida = subprocess.run(["pactl", "list", "short", "sinks"], capture_output=True, text=True, timeout=3).stdout
        fontes = subprocess.run(["pactl", "list", "short", "sources"], capture_output=True, text=True,
                                timeout=3).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    sink = next((l.split("\t")[1] for l in saida.splitlines()
                 if "AW725H" in l and "alsa_output" in l), None)
    source = next((l.split("\t")[1] for l in fontes.splitlines()
                   if "AW725H" in l and "alsa_input" in l), None)
    return sink, source


class MonitorMicrofone:
    """Ouvir a própria voz nos fones (sidetone por software).

    Liga um pw-loopback da entrada do headset para a saída do headset. A latência total
    (PipeWire + rádio do headset) fica em torno de 40–80 ms: serve para controlar o tom de voz,
    não é instantâneo como um sidetone de hardware. O stream de saída do loopback é um
    sink-input do AW725H, então o protetor (aw725h_guard) o move junto com os outros.
    """

    NOME = "aw725h_monitor_mic"

    def __init__(self):
        self.processo = None

    @property
    def ativo(self):
        return self.processo is not None and self.processo.poll() is None

    def iniciar(self, volume=0.5, latencia_ms=20, sink=None, source=None):
        """volume de 0 a 1 (aplicado ao stream de saída do loopback). Devolve (ok, mensagem)."""
        if self.ativo:
            return True, "já ligado"
        if sink is None or source is None:
            sink, source = nos_pipewire_aw725h()
        if not sink or not source:
            return False, "AW725H não encontrado no PipeWire"
        comando = ["pw-loopback", "-n", self.NOME, "-c", "1", "-m", "[ MONO ]",
                   "-l", str(latencia_ms), "-C", source, "-P", sink,
                   "--capture-props", "node.description='Monitor do microfone (captura)' node.passive=true",
                   "--playback-props", f"node.description='Monitor do microfone' channelmix.upmix=true "
                                       f"audio.position=[ MONO ] node.dont-reconnect=true"]
        try:
            self.processo = subprocess.Popen(comando, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except OSError as erro:
            return False, str(erro)
        time.sleep(0.4)
        if not self.ativo:
            return False, (self.processo.stderr.read() or b"pw-loopback saiu").decode(errors="replace").strip()
        self.definir_volume(volume)
        return True, "ligado"

    def definir_volume(self, volume):
        """Volume do retorno (0–1), aplicado com wpctl no nó de saída do loopback."""
        no = self._id_saida()
        if no is None:
            return False
        r = subprocess.run(["wpctl", "set-volume", str(no), f"{max(0.0, min(1.0, volume)):.2f}"],
                           capture_output=True, text=True)
        return r.returncode == 0

    def _id_saida(self):
        """id do nó de saída (playback) do pw-loopback, procurado no pw-dump."""
        try:
            saida = subprocess.run(["pw-dump"], capture_output=True, text=True, timeout=5).stdout
            objetos = json.loads(saida)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return None
        for obj in objetos:
            props = obj.get("info", {}).get("props", {}) or {}
            # o pw-loopback cria "input.<nome>" (captura) e "output.<nome>" (saída para os fones)
            if obj.get("type", "").endswith("Node") and props.get("node.name") == f"output.{self.NOME}":
                return obj["id"]
        return None

    def parar(self):
        if self.processo is not None:
            self.processo.terminate()
            try:
                self.processo.wait(2)
            except subprocess.TimeoutExpired:
                self.processo.kill()
        self.processo = None


# ---------------------------------------------------------------------------
# Linha de comando: python headset_aw725h.py [escutar [segundos] | mixer]
# ---------------------------------------------------------------------------

def _principal():
    import sys
    acao = sys.argv[1] if len(sys.argv) > 1 else "mixer"
    if acao == "mixer":
        m = ler_mixer()
        if m["erro"]:
            print("erro:", m["erro"])
            return 1
        print(f"fones: {m['volume']}/{m['volume_max']} ({passo_para_db(m['volume'], m['volume_max'])} dB), "
              f"{'ligado' if m['som'] else 'MUDO'}")
        print(f"microfone: {m['mic']}/{m['mic_max']} ({passo_para_db(m['mic'], m['mic_max'])} dB), "
              f"{'ligado' if m['mic_ligado'] else 'MUDO'}")
        return 0
    if acao == "escutar":
        segundos = float(sys.argv[2]) if len(sys.argv) > 2 else 60
        leitor = LeitorPassivo(ao_evento=print)
        leitor.start()
        time.sleep(segundos)
        leitor.parar()
        print("estado:", leitor.estado)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(_principal())
