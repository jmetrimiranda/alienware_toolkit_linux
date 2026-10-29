"""Modo de demonstração: o app navega sozinho e grava quadros da janela (para os GIFs e vídeos do README).

Uso (numa sessão gráfica de verdade, porque o 3D precisa de WebGL):
    ALIENWARE_DEMO=tour  ALIENWARE_DEMO_PASTA=/tmp/demo  ./run.sh   # vídeo: quadros JPEG + legendas
    ALIENWARE_DEMO=fotos ALIENWARE_DEMO_PASTA=/tmp/fotos ./run.sh   # uma foto PNG de cada página e aba

Saída do "tour": quadro-00001.jpg, ... e quadros.jsonl com {"i", "t", "legenda", "trecho"} por quadro
(as legendas em inglês são queimadas depois, na hora de montar o GIF/MP4). ALIENWARE_DEMO_FPS = quadros/s.

Segurança: o roteiro só mexe nos controles de PRÉ-VISUALIZAÇÃO (cor, efeito, brilho, abas). Nunca chama
APLICAR, não liga o EQ nem o retorno do microfone e não grava configurações (aparencia.json, estado do headset).
"""

import json
import os
import queue
import threading
import time

from gi.repository import Gdk, GLib, Gtk

# ---------- ações usadas pelos roteiros ----------


def _mouse(j, aba="iluminacao", cor=None, efeito=None, brilho=None):
    j.abrir_dispositivo({"tipo": "mouse", "suportado": True})
    pagina = j.pagina_mouse
    pagina.abas.mostrar(aba)
    if cor is not None:
        pagina._escolher_cor(cor)
    if efeito is not None:
        pagina.combo_efeito.set_selected(["fixo", "respirar", "transição", "espectro", "pulsar", "arco-íris"]
                                         .index(efeito))
    if brilho is not None:
        pagina.brilho.set_value(brilho)


def _teclado(j, aba="iluminacao", efeito=None, brilho=None, atalho=None):
    j.abrir_dispositivo({"tipo": "teclado", "suportado": True})
    pagina = j.pagina_teclado
    pagina.abas.mostrar(aba)
    if efeito is not None:
        pagina.combo_efeito.set_selected(efeito)
    if brilho is not None:
        pagina.brilho.set_value(brilho)
    if atalho is not None:
        pagina.lista_atalhos.select_row(pagina.lista_atalhos.get_row_at_index(atalho))
        pagina.destaque = None
        pagina.destacar_atalho(atalho)


def _headset(j, aba="estado", preset=None, cor=None, efeito=None):
    j.abrir_dispositivo({"tipo": "headset", "suportado": True})
    pagina = j.pagina_headset
    pagina.abas.mostrar(aba)
    if preset is not None:
        pagina.extras.abas["equalizador"].botoes[preset].set_active(True)  # só a escolha; não aplica
    luz = pagina.extras.abas["iluminacao"]
    if cor is not None:
        luz._usar_cor(cor)
    if efeito is not None:
        luz.efeito.set_selected(efeito)


def _corpo(j, aparelho, cor):
    """Troca a cor do corpo só no 3D (sem gravar aparencia.json)."""
    pagina = {"mouse": j.pagina_mouse, "headset": j.pagina_headset, "teclado": j.pagina_teclado}[aparelho]
    if pagina.visualizador:
        pagina.visualizador.set_body_color(cor)


CIANO, VERMELHO, ROXO, VERDE = (0x00, 0xE5, 0xFF), (0xFF, 0x00, 0x00), (0x80, 0x00, 0xFF), (0x00, 0xFF, 0x00)
MAGENTA, LARANJA = (0xFF, 0x00, 0xFF), (0xFF, 0x80, 0x00)

# Cada passo: (segundos, trecho, legenda em inglês, ação[, nome da foto PNG tirada no fim do passo])
TOUR = [
    (3.6, "inicio", "Home: every USB device as a card. Supported devices open their own page",
     lambda j: j.abrir("inicio")),
    (2.6, "mouse", "Alienware AW720M: live 3D preview. Nothing is sent to the mouse until APPLY",
     lambda j: _mouse(j, cor=CIANO, efeito="fixo", brilho=100)),
    (1.7, "mouse", "Pick a color: the 3D model updates instantly", lambda j: _mouse(j, cor=VERMELHO)),
    (1.7, "mouse", "Pick a color: the 3D model updates instantly", lambda j: _mouse(j, cor=ROXO)),
    (1.7, "mouse", "Pick a color: the 3D model updates instantly", lambda j: _mouse(j, cor=VERDE)),
    (2.6, "mouse", "Effect preview: breathing", lambda j: _mouse(j, cor=CIANO, efeito="respirar")),
    (2.6, "mouse", "Effect preview: spectrum", lambda j: _mouse(j, efeito="espectro")),
    (2.6, "mouse", "Effect preview: rainbow", lambda j: _mouse(j, cor=MAGENTA, efeito="arco-íris")),
    (2.2, "mouse", "Battery from the mouse's own power reports",
     lambda j: _mouse(j, aba="bateria", efeito="fixo"), "mouse-battery"),
    (3.0, "teclado", "Redragon K617 Fizz Rainbow: factory colors per row (preview only)",
     lambda j: _teclado(j, efeito=0, brilho=5)),
    (2.6, "teclado", "Preview what Fn + Right Alt does: breathing", lambda j: _teclado(j, efeito=1)),
    (3.0, "teclado", "Preview what Fn + Right Alt does: rainbow wave", lambda j: _teclado(j, efeito=3)),
    (2.4, "teclado", "Fn shortcuts: click a row to light the keys (Fn + M = brightness)",
     lambda j: _teclado(j, aba="atalhos", atalho=1)),
    (2.4, "teclado", "Fn + W A S D = arrow keys", lambda j: _teclado(j, aba="atalhos", atalho=7)),
    (3.0, "headset", "Alienware AW725H: dongle status, firmware and the 'sound on one side' fix",
     lambda j: _headset(j, aba="estado")),
    (2.4, "headset", "Dongle reboots per hour, read from the kernel log", lambda j: _headset(j, aba="estabilidade")),
    (2.0, "headset", "Disconnect guard: a user service that keeps the dongle from rebooting",
     lambda j: _headset(j, aba="protecao"), "headset-guard"),
    (2.4, "headset", "Software EQ (PipeWire): presets and 10 bands, APPLY / CANCEL in the bottom bar",
     lambda j: _headset(j, aba="equalizador", preset="fps"), "headset-eq"),
    (2.8, "headset", "Light preview on both alien heads", lambda j: _headset(j, aba="iluminacao", cor=MAGENTA, efeito=1)),
    (2.2, "headset", "One battery for both sides, read passively from the dongle",
     lambda j: _headset(j, aba="bateria")),
    (2.6, "config", "Settings: body color of each device in 3D (black, white or custom)",
     lambda j: j.abrir("config")),
]

# Fotos: (segundos de espera, nome do arquivo, ação)
FOTOS = [
    (3.0, "home-devices", lambda j: j.abrir("inicio")),
    (1.8, "mouse-lighting", lambda j: _mouse(j, cor=CIANO, efeito="fixo", brilho=100)),
    (1.6, "mouse-lighting-lunar-light", lambda j: (_corpo(j, "mouse", "#dcdfe2"), _mouse(j, cor=ROXO))),
    (1.4, "mouse-battery", lambda j: (_corpo(j, "mouse", "#202226"), _mouse(j, aba="bateria", cor=CIANO))),
    (1.4, "mouse-diagnostics", lambda j: _mouse(j, aba="diagnostico")),
    (1.8, "keyboard-lighting", lambda j: _teclado(j, efeito=0, brilho=5)),
    (1.6, "keyboard-fn-shortcuts", lambda j: _teclado(j, aba="atalhos", atalho=1)),
    (1.4, "keyboard-info", lambda j: _teclado(j, aba="informacoes")),
    (1.8, "headset-status", lambda j: _headset(j, aba="estado")),
    (1.4, "headset-stability", lambda j: _headset(j, aba="estabilidade")),
    (1.4, "headset-guard", lambda j: _headset(j, aba="protecao")),
    (1.6, "headset-audio", lambda j: _headset(j, aba="audio")),
    (1.6, "headset-mic", lambda j: _headset(j, aba="microfone")),
    (1.4, "headset-eq", lambda j: _headset(j, aba="equalizador", preset="fps")),
    (1.6, "headset-light", lambda j: _headset(j, aba="iluminacao", cor=CIANO, efeito=0)),
    (1.4, "headset-battery", lambda j: _headset(j, aba="bateria")),
    (1.4, "settings-appearance", lambda j: j.abrir("config")),
    (1.2, "about", lambda j: j.abrir("sobre")),
]


# ---------- captura ----------

def textura_da_janela(janela):
    """Renderiza a janela inteira (com o WebGL do 3D) numa Gdk.Texture. None se o nó vier vazio."""
    largura, altura = janela.get_width(), janela.get_height()
    desenho = Gtk.WidgetPaintable.new(janela)
    snapshot = Gtk.Snapshot.new()
    desenho.snapshot(snapshot, largura, altura)
    no = snapshot.to_node()
    if no is None:
        return None
    return janela.get_renderer().render_texture(no, None)


class Gravador:
    """Grava quadros JPEG da janela a N quadros/s.

    A captura acontece no sinal "after-paint" do relógio de quadros: logo depois de pintar, a árvore da
    janela está válida (no meio de um relayout o WidgetPaintable devolve um nó vazio). Em páginas paradas,
    um timer pede um redesenho para a gravação continuar. A compressão roda numa thread.
    """

    def __init__(self, janela, pasta, fps):
        from PIL import Image  # só o modo demo precisa do Pillow
        self.Image = Image
        self.janela, self.pasta = janela, pasta
        self.intervalo = 1 / fps
        self.fila = queue.Queue(maxsize=64)
        self.n = 0
        self.legenda, self.trecho = "", ""
        self.foto = None  # nome da próxima foto PNG a salvar (passos com foto)
        self.inicio = self.ultimo = time.monotonic()
        self.ativo = True
        self.manifesto = open(os.path.join(pasta, "quadros.jsonl"), "w")
        self.thread = threading.Thread(target=self._salvar, daemon=True)
        self.thread.start()
        GLib.timeout_add(50, self._ligar_relogio)

    def _ligar_relogio(self):
        relogio = self.janela.get_frame_clock()
        if relogio is None:
            return True  # janela ainda sem relógio: tenta de novo
        relogio.connect("after-paint", self._depois_de_pintar)
        GLib.timeout_add(int(self.intervalo * 1000), self._cutucar)
        return False

    def _cutucar(self):
        """Página parada (sem animação): pede um redesenho para não ficar sem quadros."""
        if not self.ativo:
            return False
        if time.monotonic() - self.ultimo > self.intervalo:
            self.janela.queue_draw()
        return True

    def _depois_de_pintar(self, _relogio):
        agora = time.monotonic()
        if not self.ativo or agora - self.ultimo < self.intervalo * 0.85:
            return
        textura = textura_da_janela(self.janela)
        if textura is None:
            return
        self.ultimo = agora
        if self.foto:
            textura.save_to_png(os.path.join(self.pasta, f"{self.foto}.png"))
            print(f"foto: {self.foto}.png")
            self.foto = None
        baixador = Gdk.TextureDownloader.new(textura)
        baixador.set_format(Gdk.MemoryFormat.R8G8B8A8)
        dados, passo = baixador.download_bytes()
        self.n += 1
        self.manifesto.write(json.dumps({"i": self.n, "t": round(agora - self.inicio, 3), "legenda": self.legenda,
                                         "trecho": self.trecho}) + "\n")
        try:
            self.fila.put_nowait((self.n, textura.get_width(), textura.get_height(), dados.get_data(), passo))
        except queue.Full:
            pass  # disco lento: perde o quadro em vez de travar a animação

    def _salvar(self):
        while True:
            item = self.fila.get()
            if item is None:
                return
            n, largura, altura, dados, passo = item
            imagem = self.Image.frombuffer("RGBA", (largura, altura), dados, "raw", "RGBA", passo, 1)
            imagem.convert("RGB").save(os.path.join(self.pasta, f"quadro-{n:05d}.jpg"), quality=93)

    def parar(self):
        self.ativo = False
        self.manifesto.close()
        self.fila.put(None)
        self.thread.join(timeout=30)


def iniciar(app, janela, roteiro):
    """Chamado pelo app.py com ALIENWARE_DEMO=<roteiro> ('tour' ou 'fotos')."""
    pasta = os.environ.get("ALIENWARE_DEMO_PASTA") or os.path.join(os.getcwd(), f"demo-{roteiro}")
    os.makedirs(pasta, exist_ok=True)
    limite = float(os.environ.get("ALIENWARE_DEMO_LIMITE", "62"))  # trava de segurança (segundos)
    GLib.timeout_add(int(limite * 1000), lambda: app.quit() or False)
    if roteiro == "fotos":
        _rodar_fotos(app, janela, pasta)
    else:
        _rodar_tour(app, janela, pasta, TOUR)


def _rodar_tour(app, janela, pasta, passos):
    gravador = Gravador(janela, pasta, float(os.environ.get("ALIENWARE_DEMO_FPS", "10")))
    restantes = list(passos)

    def proximo():
        if not restantes:
            gravador.parar()
            print(f"demo: {gravador.n} quadros em {pasta}")
            app.quit()
            return False
        segundos, trecho, legenda, acao, *foto = restantes.pop(0)
        gravador.legenda, gravador.trecho = legenda, trecho
        acao(janela)
        if foto:  # foto PNG perto do fim do passo (a tela já assentou)
            GLib.timeout_add(int(max(segundos - 0.5, 0.6) * 1000), lambda: setattr(gravador, "foto", foto[0]) or False)
        GLib.timeout_add(int(segundos * 1000), proximo)
        return False

    proximo()


def _rodar_fotos(app, janela, pasta):
    # Fotos sem transição: a troca de página/aba aparece inteira na hora
    Gtk.Settings.get_default().set_property("gtk-enable-animations", False)
    restantes = list(FOTOS)
    pendente = []  # nome da foto esperando o próximo "after-paint"

    def depois_de_pintar(_relogio):
        if not pendente:
            return
        textura = textura_da_janela(janela)
        if textura is None:
            janela.queue_draw()  # nó vazio (relayout no meio): tenta no próximo quadro
            return
        nome = pendente.pop()
        textura.save_to_png(os.path.join(pasta, f"{nome}.png"))
        print(f"foto: {nome}.png ({textura.get_width()}x{textura.get_height()})")
        GLib.idle_add(proximo)

    def fotografar(nome):
        pendente.append(nome)
        janela.queue_draw()
        return False

    def proximo():
        if not restantes:
            app.quit()
            return False
        segundos, nome, acao = restantes.pop(0)
        acao(janela)
        GLib.timeout_add(int(segundos * 1000), fotografar, nome)
        return False

    janela.get_frame_clock().connect("after-paint", depois_de_pintar)
    proximo()
