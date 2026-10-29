"""Visualizador 3D giratório dos aparelhos (mouse AW720M, headset AW725H, teclado genérico).

Embrulha um WebKit.WebView (WebKit 6.0) que carrega assets/3d/visualizador.html (three.js vendorizado,
tudo local, sem internet). O Python conversa com a página assim:

  Python -> JS: evaluate_javascript("window.aw3d.definirX(...)"). Chamadas feitas antes de a página
                avisar que está pronta ficam numa fila e são enviadas na ordem depois.
  JS -> Python: window.webkit.messageHandlers.aw3d.postMessage(json) -> _mensagem():
                {tipo:'pronto'}, {tipo:'clique', zona:'logo'} e {tipo:'erro', mensagem}.

Se o WebKit não existir, a página falhar ou o WebGL não funcionar, mostra o SVG estático do aparelho
(assets/mouse.svg, headset.svg, teclado.svg), sem quebrar a página do painel.

Uso:
    vis = Visualizador3D("mouse", ao_clicar_zona=lambda zona: print(zona))
    vis.set_body_color("#dcdfe2")            # Lunar Light
    vis.set_effect("respirar", "#00c8d7", None, 50)
"""

import base64
import json
import os

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

try:
    gi.require_version("WebKit", "6.0")
    from gi.repository import WebKit  # noqa: E402
except (ImportError, ValueError):  # sem o pacote gir1.2-webkit-6.0
    WebKit = None

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(PASTA, "assets")
PAGINA = os.path.join(ASSETS, "3d", "visualizador.html")

MODELOS = ("mouse", "headset", "teclado")
SVG_DO_MODELO = {"mouse": "mouse.svg", "headset": "headset.svg", "teclado": "teclado.svg"}
# cores oficiais do corpo (nomes da Dell)
CORES_CORPO = {"Dark Side of the Moon": "#202226", "Lunar Light": "#dcdfe2"}
# efeitos de pré-visualização (nome interno -> texto para a interface)
EFEITOS = {"fixo": "Fixo", "respirar": "Respirar", "transicao": "Transição", "espectro": "Espectro",
           "pulsar": "Pulsar", "arco-iris": "Arco-íris", "onda": "Onda (teclado)"}
LAYOUTS = {"104": "Completo (104)", "87": "TKL (87)", "75": "75% (84)", "60": "60% (61)"}
# zonas de luz de cada aparelho (o teclado também aceita 'tecla:<id>', ex.: 'tecla:Esc')
ZONAS = {"mouse": ("logo",), "headset": ("logo", "logo_esq", "logo_dir"),
         "teclado": ("todas", "zona1", "zona2", "zona3", "zona4")}

DICA = ("Visualizador 3D: arraste para girar, use a roda do mouse para o zoom e dê duplo clique "
        "para voltar à vista inicial. Clique numa zona de luz (logo, tecla) para escolher a cor dela.")


class Visualizador3D(Gtk.Box):
    """Modelo 3D giratório de um aparelho, com cor do corpo, luzes e efeitos de pré-visualização."""

    def __init__(self, modelo="mouse", ao_clicar_zona=None, girar=True):
        super().__init__(hexpand=True, vexpand=True)
        self.set_tooltip_text(DICA)
        self.ao_clicar_zona = ao_clicar_zona  # função(nome_da_zona), chamada ao clicar numa zona de luz
        self.ao_ficar_pronto = None           # função() opcional, chamada quando a cena carrega
        self.pronto = False                   # a página já carregou e a API existe?
        self.fila = []                        # chamadas feitas antes de a página ficar pronta
        self.modelo = modelo
        self.motivo_reserva = None            # por que o SVG de reserva está na tela (ou None)

        self.pilha = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hexpand=True, vexpand=True)
        self.append(self.pilha)
        # reserva: SVG estático do aparelho
        self.reserva = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, can_shrink=True,
                                   margin_top=24, margin_bottom=24, margin_start=24, margin_end=24)
        self.reserva.set_tooltip_text("Ilustração estática (o modo 3D não está disponível neste sistema)")
        self.pilha.add_named(self.reserva, "svg")

        self.web = None
        self._atualizar_svg()
        if WebKit is None:
            self._usar_reserva("WebKit 6.0 não está instalado (pacote gir1.2-webkit-6.0)")
        else:
            try:
                self._criar_webview(girar)
            except GLib.Error as erro:
                self._usar_reserva(f"falha ao criar o WebView: {erro.message}")

    # ---------- montagem do WebView ----------

    def _criar_webview(self, girar):
        conteudo = WebKit.UserContentManager()
        conteudo.register_script_message_handler("aw3d", None)
        conteudo.connect("script-message-received::aw3d", self._mensagem)
        self.web = WebKit.WebView(user_content_manager=conteudo, hexpand=True, vexpand=True)
        ajustes = self.web.get_settings()
        ajustes.set_allow_file_access_from_file_urls(True)        # módulos JS e three.js via file://
        ajustes.set_allow_universal_access_from_file_urls(True)
        ajustes.set_enable_webgl(True)
        ajustes.set_enable_developer_extras(os.environ.get("AW3D_DEPURAR") == "1")  # inspetor (F12)
        try:
            ajustes.set_hardware_acceleration_policy(WebKit.HardwareAccelerationPolicy.ALWAYS)
        except AttributeError:
            pass
        # mesma cor do fundo do painel enquanto a página carrega (sem clarão branco)
        fundo = Gdk.RGBA()
        fundo.parse("#1b1d21")
        self.web.set_background_color(fundo)
        self.web.connect("context-menu", lambda *_a: True)   # sem menu "Recarregar/Inspecionar"
        self.web.connect("load-failed", self._falhou_carregar)
        self.web.connect("web-process-terminated", self._processo_caiu)
        self.pilha.add_named(self.web, "web")
        self.pilha.set_visible_child_name("web")
        # o modelo inicial vai na URL, para a cena não ser montada duas vezes
        self.web.load_uri(f"{GLib.filename_to_uri(PAGINA)}?modelo={self.modelo}&girar={int(bool(girar))}")

    def _falhou_carregar(self, _web, _evento, uri, erro):
        self._usar_reserva(f"não carregou {uri}: {erro.message}")
        return True

    def _processo_caiu(self, _web, motivo):
        self.pronto = False
        self._usar_reserva(f"o processo do WebKit terminou ({motivo.value_nick})")

    def _usar_reserva(self, motivo):
        """Troca o 3D pelo SVG estático do aparelho atual."""
        self.motivo_reserva = motivo
        print(f"visualizador 3D: usando o SVG de reserva ({motivo})")
        self._atualizar_svg()
        self.pilha.set_visible_child_name("svg")

    def _atualizar_svg(self):
        self.reserva.set_filename(os.path.join(ASSETS, SVG_DO_MODELO.get(self.modelo, "mouse.svg")))

    # ---------- ponte JS <-> Python ----------

    def _mensagem(self, _conteudo, valor):
        try:
            msg = json.loads(valor.to_string())
        except (ValueError, TypeError):
            return
        tipo = msg.get("tipo")
        if tipo == "pronto":
            self.pronto = True
            fila, self.fila = self.fila, []
            for script, ao_terminar in fila:
                self._rodar(script, ao_terminar)
            if self.ao_ficar_pronto:
                self.ao_ficar_pronto()
        elif tipo == "clique" and self.ao_clicar_zona:
            self.ao_clicar_zona(msg.get("zona", ""))
        elif tipo == "erro":
            # erro de JS antes de a cena existir (ex.: sem WebGL) -> SVG; depois disso, só registra
            if not self.pronto:
                self._usar_reserva(msg.get("mensagem", "erro na página"))
            else:
                print(f"visualizador 3D: {msg.get('mensagem')}")

    def _js(self, funcao, *args, ao_terminar=None):
        """Chama window.aw3d.<funcao>(args) na página (ou guarda na fila se ela ainda não carregou)."""
        if self.web is None:
            return
        script = f"window.aw3d.{funcao}({', '.join(json.dumps(a) for a in args)})"
        if self.pronto:
            self._rodar(script, ao_terminar)
        else:
            self.fila.append((script, ao_terminar))

    def _rodar(self, script, ao_terminar=None):
        def terminou(web, resultado, _dados):
            try:
                valor = web.evaluate_javascript_finish(resultado)
                texto = valor.to_string() if valor is not None else None
            except GLib.Error as erro:
                print(f"visualizador 3D: erro em {script[:60]}: {erro.message}")
                texto = None
            if ao_terminar:
                ao_terminar(texto)

        self.web.evaluate_javascript(script, -1, None, None, None, terminou, None)

    # ---------- API pública ----------

    def set_model(self, modelo):
        """'mouse', 'headset' ou 'teclado'."""
        if modelo not in MODELOS:
            raise ValueError(f"modelo desconhecido: {modelo}")
        if modelo == self.modelo and not self.pronto:
            return  # a página já vai abrir com este modelo
        self.modelo = modelo
        self._atualizar_svg()
        self._js("definirModelo", modelo)

    def set_body_color(self, cor_hex):
        """Cor do corpo, ex.: CORES_CORPO['Lunar Light']."""
        self._js("definirCorCorpo", cor_hex)

    def set_light(self, zona, cor_hex):
        """Cor de uma zona de luz: 'todas', 'logo', 'logo_esq', 'zona1'..'zona4', 'tecla:Esc'..."""
        self._js("definirLuz", zona, cor_hex)

    def set_effect(self, nome, cor1=None, cor2=None, velocidade=50):
        """Efeito: fixo, respirar, transicao, espectro, pulsar, arco-iris, onda. Velocidade 0–100.
        cor1 (se vier) vira a cor de todas as zonas; cor2 é a 2ª cor de transição e onda."""
        self._js("definirEfeito", nome, cor1, cor2, velocidade)

    def set_brightness(self, valor):
        """Brilho das luzes, 0–100."""
        self._js("definirBrilho", max(0, min(100, int(valor))))

    def set_layout(self, layout):
        """Layout do teclado: '104', '87', '75' ou '60'."""
        self._js("definirLayout", str(layout))

    def auto_rotate(self, ligado):
        """Liga/desliga o giro automático (arrastar continua funcionando)."""
        self._js("girarSozinho", bool(ligado))

    def reset_view(self):
        """Volta suavemente à vista inicial (o mesmo que o duplo clique)."""
        self._js("resetarVista")

    # ---------- capturas (testes, documentação) ----------

    def capturar_png(self, arquivo, ao_terminar=None):
        """Salva a área visível do WebView num PNG (WebView.get_snapshot)."""
        if self.web is None:
            return

        def pronto(web, resultado, _dados):
            ok = False
            try:
                textura = web.get_snapshot_finish(resultado)
                ok = textura.save_to_png(arquivo)
            except GLib.Error as erro:
                print(f"visualizador 3D: captura falhou: {erro.message}")
            if ao_terminar:
                ao_terminar(ok)

        self.web.get_snapshot(WebKit.SnapshotRegion.VISIBLE, WebKit.SnapshotOptions.NONE, None, pronto, None)

    def quadro_png(self, arquivo, angulo=0, largura=960, altura=720, tempo=None, ao_terminar=None):
        """Desenha um quadro fixo (giro em graus a partir da vista inicial) e salva no arquivo.
        A extensão escolhe o formato: .png (mais lento no WebKit, ~250 ms) ou .jpg (rápido, q=0,92).
        Pausa a animação até fim_captura(); serve para gravar giros de 360° quadro a quadro."""
        formato = "image/jpeg" if arquivo.lower().endswith((".jpg", ".jpeg")) else "image/png"

        def salvar(texto):
            ok = bool(texto and texto.startswith("data:image/"))
            if ok:
                with open(arquivo, "wb") as saida:
                    saida.write(base64.b64decode(texto.split(",", 1)[1]))
            if ao_terminar:
                ao_terminar(ok)

        self._js("quadro", angulo, largura, altura, tempo, formato, ao_terminar=salvar)

    def fim_captura(self):
        """Volta à animação normal depois de quadro_png()."""
        self._js("fimCaptura")

    def estado(self, ao_terminar):
        """Pede o estado atual da cena (dicionário) e entrega em ao_terminar(estado)."""
        self._js("estado", ao_terminar=lambda texto: ao_terminar(json.loads(texto) if texto else None))
