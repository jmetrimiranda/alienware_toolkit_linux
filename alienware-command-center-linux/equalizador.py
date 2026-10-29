"""Equalizador por software para o headset AW725H, no PipeWire (filter-chain).

O AW725H não expõe EQ de hardware no Linux (o EQ do AWCC/Dolby roda no Windows). Aqui o EQ é
um sink virtual "AW725H EQ": os apps tocam nele, ele passa o som por 10 filtros biquad
(+ um pré-ganho negativo para não estourar) e manda o resultado para o sink do AW725H.

    apps ──> [AW725H EQ] (sink, node.name alienware_eq)
                │ pré-ganho → 31 Hz shelf → 62 … 8k peaking → 16 kHz shelf
                ▼
             alienware_eq.saida (stream de saída = sink-input do AW725H)
                ▼
             AW725H Dongle Analog Stereo  ← o protetor move este sink-input como os outros

ATENÇÃO, nome do nó: o protetor (aw725h_guard.py) procura o sink do headset com
"AW725H" in node.name. Por isso o node.name do EQ é "alienware_eq" (sem AW725H): só a
descrição visível ("AW725H EQ") leva o nome do headset.

Dois jeitos de rodar:
  1. Serviço do sistema (padrão do app): grava o fragmento em
     ~/.config/pipewire/filter-chain.conf.d/aw725h-eq.conf e reinicia o filter-chain.service
     do usuário (já vem no Ubuntu 24.04: /usr/lib/systemd/user/filter-chain.service).
  2. Instância própria: `pipewire -c <conf completo>` (gerar_conf(completo=True)); é o que o
     teste usa a partir de ~/lab, sem mexer em nada do usuário.
Mudança de preset com o EQ ligado vai ao vivo (pw-cli set-param), sem cortar o som.
"""

import json
import os
import subprocess
import time

# 10 bandas de oitava, como os EQs gráficos de 10 bandas
BANDAS = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
LIMITE_DB = 12  # cada banda vai de −12 a +12 dB

# Presets (ganho em dB por banda). Pensados para o AW725H, que já tem graves fortes.
PRESETS = {
    "plano": {"nome": "Plano", "ganhos": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
              "dica": "Sem equalização: o som original do headset."},
    "graves": {"nome": "Graves+", "ganhos": [6, 5, 3.5, 1.5, 0, 0, 0, 0, 0.5, 1],
               "dica": "Reforça graves (31–125 Hz) para filmes e música; um toque nos agudos para não abafar."},
    "fps": {"nome": "Passos FPS", "ganhos": [-5, -4, -3, -1, 0, 1, 3, 5, 3, 0],
            "dica": "Abaixa graves (explosões, motores) e realça 2–8 kHz, onde ficam passos, recarga e "
                    "direção do som em jogos de tiro."},
    "voz": {"nome": "Voz", "ganhos": [-6, -5, -3, 0, 1.5, 3, 4, 3, 1, -1],
            "dica": "Realça a faixa da voz (500 Hz–4 kHz) para chamadas, podcasts e vídeos falados."},
    "personalizado": {"nome": "Personalizado", "ganhos": [0] * 10,
                      "dica": "As 10 bandas que você ajustar à mão (guardadas em ~/.config/alienware-toolkit/eq.json)."},
}

NOME_NO = "alienware_eq"                 # node.name do sink virtual (SEM "AW725H": veja o aviso acima)
DESCRICAO = "AW725H EQ"                  # nome que aparece no GNOME
ALVO_PADRAO = "alsa_output.usb-Dell_Inc_AW725H_Dongle_0000000000000000-00.analog-stereo"

PASTA_CONF_D = os.path.expanduser("~/.config/pipewire/filter-chain.conf.d")
ARQUIVO_CONF_D = os.path.join(PASTA_CONF_D, "aw725h-eq.conf")
ARQUIVO_AJUSTES = os.path.expanduser("~/.config/alienware-toolkit/eq.json")
SERVICO = "filter-chain.service"


# ---------------------------------------------------------------------------
# Geração da configuração
# ---------------------------------------------------------------------------

def tipo_da_banda(indice):
    """1ª banda = prateleira de graves, última = prateleira de agudos, o resto = pico."""
    if indice == 0:
        return "bq_lowshelf", 0.707
    if indice == len(BANDAS) - 1:
        return "bq_highshelf", 0.707
    return "bq_peaking", 1.41  # Q ≈ 1,41 cobre uma oitava


def pre_ganho(ganhos):
    """Ganho negativo que compensa o maior reforço, para não saturar (clipping)."""
    return -max([0.0] + [float(g) for g in ganhos])


def _limitar(ganhos):
    if len(ganhos) != len(BANDAS):
        raise ValueError(f"são {len(BANDAS)} bandas, vieram {len(ganhos)}")
    return [max(-LIMITE_DB, min(LIMITE_DB, round(float(g), 1))) for g in ganhos]


def gerar_conf(ganhos, alvo=ALVO_PADRAO, completo=False, nome_preset=""):
    """Texto da configuração do filter-chain.

    completo=False: só o bloco context.modules (fragmento para filter-chain.conf.d/).
    completo=True:  arquivo inteiro para `pipewire -c arquivo.conf` (instância própria).
    """
    ganhos = _limitar(ganhos)
    nos = ['          { type = builtin name = pre label = bq_highshelf '
           f'control = {{ "Freq" = 0 "Q" = 1.0 "Gain" = {pre_ganho(ganhos):.1f} }} }}']
    links = []
    anterior = "pre"
    for i, (freq, ganho) in enumerate(zip(BANDAS, ganhos), start=1):
        rotulo_bq, q = tipo_da_banda(i - 1)
        nos.append(f'          {{ type = builtin name = b{i} label = {rotulo_bq} '
                   f'control = {{ "Freq" = {freq:.1f} "Q" = {q} "Gain" = {ganho:.1f} }} }}')
        links.append(f'          {{ output = "{anterior}:Out" input = "b{i}:In" }}')
        anterior = f"b{i}"
    modulo = f"""context.modules = [
  {{ name = libpipewire-module-filter-chain
    flags = [ nofail ]
    args = {{
      node.description = "{DESCRICAO}"
      media.name       = "{DESCRICAO}"
      filter.graph = {{
        nodes = [
{chr(10).join(nos)}
        ]
        links = [
{chr(10).join(links)}
        ]
      }}
      # o grafo é mono; o filter-chain cria uma cópia para cada canal (FL e FR)
      audio.channels = 2
      audio.position = [ FL FR ]
      capture.props = {{
        node.name   = "{NOME_NO}"
        media.class = Audio/Sink
      }}
      playback.props = {{
        node.name         = "{NOME_NO}.saida"
        node.description  = "{DESCRICAO} (saída)"
        node.passive      = true
        target.object     = "{alvo}"
        stream.dont-remix = true
      }}
    }}
  }}
]
"""
    cabecalho = (f"# Gerado pelo Painel Alienware: equalizador do AW725H"
                 f"{' (preset ' + nome_preset + ')' if nome_preset else ''}\n"
                 f"# Ganhos (dB) em {', '.join(str(b) for b in BANDAS)} Hz: {ganhos}\n")
    if not completo:
        return cabecalho + modulo
    # Mesmo cabeçalho do /usr/share/pipewire/filter-chain.conf, para rodar sozinho
    return cabecalho + """context.properties = {
  log.level = 0
}
context.spa-libs = {
  audio.convert.* = audioconvert/libspa-audioconvert
  support.*       = support/libspa-support
}
""" + modulo.replace("context.modules = [", """context.modules = [
  { name = libpipewire-module-rt args = { } flags = [ ifexists nofail ] }
  { name = libpipewire-module-protocol-native }
  { name = libpipewire-module-client-node }
  { name = libpipewire-module-adapter }""", 1)


def parametros_ao_vivo(ganhos):
    """Texto Props para `pw-cli set-param <id> Props '<texto>'` (muda os filtros sem reiniciar)."""
    ganhos = _limitar(ganhos)
    pares = [f'"pre:Gain" {pre_ganho(ganhos):.1f}']
    pares += [f'"b{i}:Gain" {g:.1f}' for i, g in enumerate(ganhos, start=1)]
    return "{ params = [ " + " ".join(pares) + " ] }"


# ---------------------------------------------------------------------------
# Ajustes do usuário (~/.config/alienware-toolkit/eq.json)
# ---------------------------------------------------------------------------

def ler_ajustes():
    ajustes = {"ligado": False, "preset": "plano", "personalizado": [0] * 10, "padrao": True}
    try:
        with open(ARQUIVO_AJUSTES) as f:
            ajustes.update(json.load(f))
    except (OSError, ValueError):
        pass
    return ajustes


def salvar_ajustes(ajustes):
    os.makedirs(os.path.dirname(ARQUIVO_AJUSTES), exist_ok=True)
    with open(ARQUIVO_AJUSTES, "w") as f:
        json.dump(ajustes, f, indent=2)


def ganhos_do_preset(preset, ajustes=None):
    if preset == "personalizado":
        return list((ajustes or ler_ajustes())["personalizado"])
    return list(PRESETS[preset]["ganhos"])


# ---------------------------------------------------------------------------
# PipeWire: achar o nó, ligar, desligar, mudar ao vivo
# ---------------------------------------------------------------------------

def _pw_dump():
    try:
        saida = subprocess.run(["pw-dump"], capture_output=True, text=True, timeout=5).stdout
        return json.loads(saida)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []


def achar_no(nome=NOME_NO):
    """id do nó com esse node.name no PipeWire, ou None."""
    for obj in _pw_dump():
        props = (obj.get("info") or {}).get("props") or {}
        if obj.get("type", "").endswith(":Node") and props.get("node.name") == nome:
            return obj["id"]
    return None


def estado():
    """{'ativo': bool, 'id': int|None, 'saida_ligada_em': nome do sink de destino|None, 'instalado': bool}."""
    objetos = _pw_dump()
    nos = {}
    for obj in objetos:
        props = (obj.get("info") or {}).get("props") or {}
        if obj.get("type", "").endswith(":Node"):
            nos[obj["id"]] = props.get("node.name")
    id_eq = next((i for i, n in nos.items() if n == NOME_NO), None)
    id_saida = next((i for i, n in nos.items() if n == NOME_NO + ".saida"), None)
    destino = None
    for obj in objetos:
        if obj.get("type", "").endswith(":Link"):
            info = obj.get("info") or {}
            if info.get("output-node-id") == id_saida:
                destino = nos.get(info.get("input-node-id"))
    return {"ativo": id_eq is not None, "id": id_eq, "saida_ligada_em": destino,
            "instalado": os.path.exists(ARQUIVO_CONF_D)}


def aplicar_ao_vivo(ganhos, no=None):
    """Muda os ganhos do EQ que já está rodando. Devolve (ok, mensagem)."""
    no = no if no is not None else achar_no()
    if no is None:
        return False, "EQ não está rodando"
    r = subprocess.run(["pw-cli", "set-param", str(no), "Props", parametros_ao_vivo(ganhos)],
                       capture_output=True, text=True, timeout=5)
    return r.returncode == 0, (r.stderr.strip() or "ok")


def _systemctl(*args):
    r = subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, timeout=20)
    return r.returncode == 0, (r.stderr.strip() or r.stdout.strip() or "ok")


def gravar_fragmento(ganhos, nome_preset="", alvo=ALVO_PADRAO):
    """Grava ~/.config/pipewire/filter-chain.conf.d/aw725h-eq.conf (vale a partir do próximo início)."""
    os.makedirs(PASTA_CONF_D, exist_ok=True)
    with open(ARQUIVO_CONF_D, "w") as f:
        f.write(gerar_conf(ganhos, alvo=alvo, nome_preset=nome_preset))


def ligar(ganhos, nome_preset="", alvo=ALVO_PADRAO, como_padrao=True):
    """Liga o EQ pelo filter-chain.service do usuário (modo do app).

    Grava ~/.config/pipewire/filter-chain.conf.d/aw725h-eq.conf, reinicia SÓ o filter-chain.service
    (o pipewire principal e o protetor continuam) e, se como_padrao, faz do "AW725H EQ" a saída padrão.
    """
    gravar_fragmento(ganhos, nome_preset, alvo)
    ok, msg = _systemctl("restart", SERVICO)
    if not ok:
        return False, f"não consegui reiniciar o {SERVICO}: {msg}"
    no = None
    for _ in range(20):  # o nó aparece em menos de 1 s
        no = achar_no()
        if no is not None:
            break
        time.sleep(0.2)
    if no is None:
        return False, "o filter-chain reiniciou, mas o sink AW725H EQ não apareceu"
    if como_padrao:
        subprocess.run(["wpctl", "set-default", str(no)], capture_output=True)
    return True, f"EQ ligado (nó {no})"


def desligar(alvo=ALVO_PADRAO):
    """Apaga o fragmento, reinicia o filter-chain.service e devolve a saída padrão ao AW725H."""
    if os.path.exists(ARQUIVO_CONF_D):
        os.remove(ARQUIVO_CONF_D)
    ok, msg = _systemctl("restart", SERVICO)
    id_alvo = achar_no(alvo)
    if id_alvo is not None:
        subprocess.run(["wpctl", "set-default", str(id_alvo)], capture_output=True)
    return ok, "EQ desligado" if ok else msg


class InstanciaTemporaria:
    """`pipewire -c <conf>` próprio, para testar sem tocar em ~/.config (usado pelos testes)."""

    def __init__(self, arquivo_conf):
        self.arquivo = arquivo_conf
        self.processo = None

    def iniciar(self, ganhos, alvo=ALVO_PADRAO, nome_preset="teste"):
        with open(self.arquivo, "w") as f:
            f.write(gerar_conf(ganhos, alvo=alvo, completo=True, nome_preset=nome_preset))
        self.processo = subprocess.Popen(["pipewire", "-c", os.path.abspath(self.arquivo)],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        for _ in range(25):
            if achar_no() is not None:
                return True
            if self.processo.poll() is not None:
                return False
            time.sleep(0.2)
        return False

    def parar(self):
        if self.processo and self.processo.poll() is None:
            self.processo.terminate()
            try:
                self.processo.wait(3)
            except subprocess.TimeoutExpired:
                self.processo.kill()


def resposta_em_frequencia(ganhos, freqs=None, taxa=48000, com_pre_ganho=True):
    """Curva (freq, dB) do EQ calculada com as mesmas fórmulas biquad do PipeWire (RBJ),
    para desenhar o gráfico na interface. com_pre_ganho=False dá só o formato da curva."""
    import cmath
    import math
    ganhos = _limitar(ganhos)
    if freqs is None:
        freqs = [20 * (1000 ** (i / 199)) for i in range(200)]  # 20 Hz a 20 kHz, escala log
    secoes = []
    for i, (f0, g) in enumerate(zip(BANDAS, ganhos)):
        tipo, q = tipo_da_banda(i)
        a = 10 ** (g / 40)
        w0 = 2 * math.pi * f0 / taxa
        alfa = math.sin(w0) / (2 * q)
        c = math.cos(w0)
        if tipo == "bq_peaking":
            b = [1 + alfa * a, -2 * c, 1 - alfa * a]
            d = [1 + alfa / a, -2 * c, 1 - alfa / a]
        else:
            raiz = 2 * math.sqrt(a) * alfa
            if tipo == "bq_lowshelf":
                b = [a * ((a + 1) - (a - 1) * c + raiz), 2 * a * ((a - 1) - (a + 1) * c),
                     a * ((a + 1) - (a - 1) * c - raiz)]
                d = [(a + 1) + (a - 1) * c + raiz, -2 * ((a - 1) + (a + 1) * c), (a + 1) + (a - 1) * c - raiz]
            else:
                b = [a * ((a + 1) + (a - 1) * c + raiz), -2 * a * ((a - 1) + (a + 1) * c),
                     a * ((a + 1) + (a - 1) * c - raiz)]
                d = [(a + 1) - (a - 1) * c + raiz, 2 * ((a - 1) - (a + 1) * c), (a + 1) - (a - 1) * c - raiz]
        secoes.append((b, d))
    curva = []
    for f in freqs:
        z = cmath.exp(-1j * 2 * math.pi * f / taxa)
        h = 1
        for b, d in secoes:
            h *= (b[0] + b[1] * z + b[2] * z * z) / (d[0] + d[1] * z + d[2] * z * z)
        curva.append((f, 20 * math.log10(max(abs(h), 1e-9)) + (pre_ganho(ganhos) if com_pre_ganho else 0)))
    return curva


if __name__ == "__main__":
    import sys
    preset = sys.argv[1] if len(sys.argv) > 1 else "fps"
    print(gerar_conf(ganhos_do_preset(preset), nome_preset=PRESETS[preset]["nome"]))
