"""Peças visuais reutilizadas pelas páginas: títulos, abas, roda de cores, anel de bateria,
ilustrações SVG com brilho e gráfico de barras. Desenho próprio com cairo (Gtk.DrawingArea)."""

import colorsys
import math
import os
import threading

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Rsvg", "2.0")
from gi.repository import GLib, Gtk, Rsvg  # noqa: E402

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(PASTA, "assets")

CIANO = (0x00 / 255, 0xC8 / 255, 0xD7 / 255)
BORDA = (0x31 / 255, 0x35 / 255, 0x3B / 255)
TEXTO = (0xE8 / 255, 0xEA / 255, 0xED / 255)
APAGADO = (0x8A / 255, 0x90 / 255, 0x99 / 255)


# ---------- pequenos atalhos ----------

def fonte(cr, nome, tamanho):
    """Fonte para texto desenhado com cairo, com suavização em cinza (sem franjas coloridas)."""
    opcoes = cairo.FontOptions()
    opcoes.set_antialias(cairo.ANTIALIAS_GRAY)
    cr.set_font_options(opcoes)
    cr.select_font_face(nome, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    cr.set_font_size(tamanho)


def dica(widget, texto):
    """Coloca a dica (tooltip) e devolve o próprio widget, para escrever tudo numa linha."""
    widget.set_tooltip_text(texto)
    return widget


def rotulo(texto, *classes, **opcoes):
    """Gtk.Label alinhado à esquerda, com classes CSS."""
    opcoes.setdefault("xalign", 0)
    return Gtk.Label(label=texto, css_classes=list(classes), **opcoes)


def titulo(primeira, segunda):
    """Título no formato 'ALIENFX │ DISPOSITIVOS': primeira palavra branca, segunda ciano."""
    texto = (f'{GLib.markup_escape_text(primeira.upper())}'
             f'<span foreground="#3a3f46">  │  </span>'
             f'<span foreground="#00c8d7">{GLib.markup_escape_text(segunda.upper())}</span>')
    return Gtk.Label(label=texto, use_markup=True, xalign=0, css_classes=["titulo"])


def em_segundo_plano(funcao, ao_terminar):
    """Roda funcao() numa thread (comandos lentos) e chama ao_terminar(resultado) na tela."""
    def rodar():
        resultado = funcao()
        GLib.idle_add(lambda: ao_terminar(resultado) and False)
    threading.Thread(target=rodar, daemon=True).start()


def hex_para_rgb(texto):
    """'#00e5ff' ou '00E5FF' -> (0, 229, 255). Devolve None se não for uma cor válida."""
    texto = texto.strip().lstrip("#")
    if len(texto) == 3:
        texto = "".join(c * 2 for c in texto)
    if len(texto) != 6:
        return None
    try:
        return tuple(int(texto[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def rgb_para_hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def grade_info(pares):
    """Tabela simples 'nome: valor' (valores selecionáveis para copiar)."""
    grade = Gtk.Grid(column_spacing=24, row_spacing=10)
    for linha, (nome, valor) in enumerate(pares):
        grade.attach(rotulo(nome.upper(), "secao", valign=Gtk.Align.START), 0, linha, 1, 1)
        grade.attach(Gtk.Label(label=valor, xalign=0, selectable=True, wrap=True, max_width_chars=48), 1, linha, 1, 1)
    return grade


# ---------- abas no estilo AWCC ----------

class Abas(Gtk.Box):
    """Abas de texto com sublinhado ciano em cima de um Gtk.Stack."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.cabecalho = Gtk.Box(css_classes=["abas"])
        self.pilha = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vexpand=True)
        self.botoes = {}
        self.ao_trocar = None  # função opcional chamada com o nome da aba aberta
        self.append(self.cabecalho)
        self.append(self.pilha)

    def adicionar(self, nome, texto, conteudo, explicacao):
        grupo = next(iter(self.botoes.values()), None)
        botao = Gtk.ToggleButton(label=texto.upper(), group=grupo, tooltip_text=explicacao)
        botao.connect("toggled", self._trocou, nome)
        self.cabecalho.append(botao)
        self.botoes[nome] = botao
        self.pilha.add_named(conteudo, nome)
        if grupo is None:
            botao.set_active(True)

    def mostrar(self, nome):
        self.botoes[nome].set_active(True)

    def atual(self):
        return self.pilha.get_visible_child_name()

    def _trocou(self, botao, nome):
        if botao.get_active():
            self.pilha.set_visible_child_name(nome)
            if self.ao_trocar:
                self.ao_trocar(nome)


# ---------- ilustração SVG (com brilho opcional) ----------

class Ilustracao(Gtk.DrawingArea):
    """Desenha um SVG de assets/ centralizado. No mouse, pinta o logo e um brilho na cor escolhida.

    luz = (x, y, raio) no sistema de coordenadas do SVG, onde fica o LED (só no mouse).
    """

    def __init__(self, arquivo, largura=-1, altura=-1, luz=None, camada_luz=None):
        super().__init__(hexpand=True, vexpand=True)
        if largura > 0:
            self.set_content_width(largura)
        if altura > 0:
            self.set_content_height(altura)
        self.svg = Rsvg.Handle.new_from_file(os.path.join(ASSETS, arquivo))
        self.luz = luz
        self.camada_luz = camada_luz  # id do elemento do SVG pintado na cor (ex.: "#logo")
        self.cor = None  # (r, g, b) de 0 a 255, ou None = sem brilho
        self.intensidade = 1.0
        self.set_draw_func(self._desenhar)

    def trocar_arquivo(self, arquivo):
        self.svg = Rsvg.Handle.new_from_file(os.path.join(ASSETS, arquivo))
        self.queue_draw()

    def definir_brilho(self, cor, intensidade=1.0):
        self.cor = cor
        self.intensidade = max(0.0, min(1.0, intensidade))
        self.queue_draw()

    def _desenhar(self, _area, cr, largura, altura):
        _, w, h = self.svg.get_intrinsic_size_in_pixels()
        escala = min(largura / w, altura / h) * 0.92
        x0, y0 = (largura - w * escala) / 2, (altura - h * escala) / 2
        caixa = Rsvg.Rectangle()
        caixa.x, caixa.y, caixa.width, caixa.height = x0, y0, w * escala, h * escala

        cor = None
        if self.cor and self.luz and self.intensidade > 0:
            cor = tuple(c / 255 for c in self.cor)
            # Halo grande atrás do aparelho
            cx, cy = largura / 2, altura / 2
            raio = min(largura, altura) / 2  # termina dentro da área, sem deixar borda reta
            halo = cairo.RadialGradient(cx, cy, 0, cx, cy, raio)
            halo.add_color_stop_rgba(0, *cor, 0.30 * self.intensidade)
            halo.add_color_stop_rgba(0.6, *cor, 0.10 * self.intensidade)
            halo.add_color_stop_rgba(1, *cor, 0)
            cr.set_source(halo)
            cr.paint()

        self.svg.render_document(cr, caixa)

        if cor:
            # Brilho em volta do LED + o logo pintado na cor (usando o próprio desenho como máscara)
            lx, ly, lr = (x0 + self.luz[0] * escala, y0 + self.luz[1] * escala, self.luz[2] * escala)
            brilho = cairo.RadialGradient(lx, ly, 0, lx, ly, lr)
            brilho.add_color_stop_rgba(0, *cor, 0.75 * self.intensidade)
            brilho.add_color_stop_rgba(1, *cor, 0)
            cr.set_source(brilho)
            cr.paint()
            if self.camada_luz:
                mascara = cairo.ImageSurface(cairo.FORMAT_ARGB32, largura, altura)
                self.svg.render_layer(cairo.Context(mascara), self.camada_luz, caixa)
                # cor do LED misturada com branco no centro, como um LED aceso de verdade
                mistura = tuple(c + (1 - c) * 0.25 for c in cor)
                cr.set_source_rgba(*mistura, 0.35 + 0.65 * self.intensidade)
                cr.mask_surface(mascara, 0, 0)


# ---------- anel de bateria ----------

class AnelBateria(Gtk.DrawingArea):
    """Anel com a porcentagem no meio. None = valor desconhecido."""

    def __init__(self, tamanho=120, espessura=8, texto_grande=True):
        super().__init__(content_width=tamanho, content_height=tamanho)
        self.valor = None
        self.carregando = False
        self.espessura = espessura
        self.texto_grande = texto_grande
        self.set_draw_func(self._desenhar)

    def definir(self, valor, carregando=False):
        self.valor, self.carregando = valor, carregando
        self.queue_draw()

    def _desenhar(self, _area, cr, largura, altura):
        cx, cy = largura / 2, altura / 2
        raio = min(largura, altura) / 2 - self.espessura
        cr.set_line_width(self.espessura)
        cr.set_source_rgb(*BORDA)
        cr.arc(cx, cy, raio, 0, 2 * math.pi)
        cr.stroke()
        if self.valor is not None:
            # ciano normal, laranja abaixo de 20%, vermelho abaixo de 10%
            cor = CIANO if self.valor >= 20 else (1, 0.69, 0.13) if self.valor >= 10 else (0.95, 0.3, 0.3)
            cr.set_source_rgb(*cor)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            inicio = -math.pi / 2
            cr.arc(cx, cy, raio, inicio, inicio + 2 * math.pi * max(self.valor, 1) / 100)
            cr.stroke()
        texto = "—" if self.valor is None else f"{self.valor}%"
        fonte(cr, "Inter Display", raio * (0.55 if self.texto_grande else 0.5))
        ext = cr.text_extents(texto)
        cr.set_source_rgb(*TEXTO)
        cr.move_to(cx - ext.width / 2 - ext.x_bearing, cy - ext.height / 2 - ext.y_bearing)
        cr.show_text(texto)
        if self.carregando and self.texto_grande:
            cr.set_font_size(raio * 0.22)
            legenda = "CARREGANDO"
            ext = cr.text_extents(legenda)
            cr.set_source_rgb(*CIANO)
            cr.move_to(cx - ext.width / 2 - ext.x_bearing, cy + raio * 0.52)
            cr.show_text(legenda)


# ---------- roda de cores ----------

class RodaDeCores(Gtk.DrawingArea):
    """Roda de matiz (ângulo) × saturação (distância do centro), com brilho máximo.

    Clique ou arraste para escolher. ao_mudar(r, g, b) é chamado a cada mudança.
    O brilho do LED fica no controle "Brilho" (protocolo), não aqui: assim a cor é sempre "cheia".
    """

    def __init__(self, tamanho=210, ao_mudar=None):
        super().__init__(content_width=tamanho, content_height=tamanho,
                         halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.ao_mudar = ao_mudar
        self.matiz, self.saturacao = 0.52, 1.0
        self._cache = None  # imagem da roda (só redesenha se o tamanho mudar)
        self.set_draw_func(self._desenhar)
        arrastar = Gtk.GestureDrag()
        arrastar.connect("drag-begin", lambda g, x, y: self._escolher(x, y))
        arrastar.connect("drag-update", self._arrastou)
        self.add_controller(arrastar)
        self.set_cursor_from_name("crosshair")

    def definir_rgb(self, rgb):
        """Move o marcador para a cor dada (sem chamar ao_mudar)."""
        h, s, _ = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
        self.matiz, self.saturacao = h, s
        self.queue_draw()

    def _arrastou(self, gesto, dx, dy):
        _, x, y = gesto.get_start_point()
        self._escolher(x + dx, y + dy)

    def _escolher(self, x, y):
        largura, altura = self.get_width(), self.get_height()
        raio = min(largura, altura) / 2 - 6
        if raio <= 0:
            return  # ainda sem tamanho na tela
        dx, dy = x - largura / 2, y - altura / 2
        self.saturacao = max(0.0, min(1.0, math.hypot(dx, dy) / raio))
        self.matiz = (math.atan2(dy, dx) / (2 * math.pi)) % 1.0
        self.queue_draw()
        if self.ao_mudar:
            r, g, b = colorsys.hsv_to_rgb(self.matiz, self.saturacao, 1.0)
            self.ao_mudar(round(r * 255), round(g * 255), round(b * 255))

    def _roda(self, largura, altura):
        """Desenha a roda uma vez numa imagem: fatias de matiz + degradê branco no centro."""
        sup = cairo.ImageSurface(cairo.FORMAT_ARGB32, largura, altura)
        cr = cairo.Context(sup)
        cx, cy = largura / 2, altura / 2
        raio = min(largura, altura) / 2 - 6
        passos = 360
        for i in range(passos):
            a0 = 2 * math.pi * i / passos
            a1 = 2 * math.pi * (i + 1.5) / passos  # 0,5 de sobra para não ficar fresta entre as fatias
            cr.set_source_rgb(*colorsys.hsv_to_rgb(i / passos, 1, 1))
            cr.move_to(cx, cy)
            cr.arc(cx, cy, raio, a0, a1)
            cr.close_path()
            cr.fill()
        branco = cairo.RadialGradient(cx, cy, 0, cx, cy, raio)
        branco.add_color_stop_rgba(0, 1, 1, 1, 1)
        branco.add_color_stop_rgba(1, 1, 1, 1, 0)
        cr.set_source(branco)
        cr.arc(cx, cy, raio, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgb(*BORDA)
        cr.set_line_width(2)
        cr.arc(cx, cy, raio + 1, 0, 2 * math.pi)
        cr.stroke()
        return sup

    def _desenhar(self, _area, cr, largura, altura):
        if self._cache is None or self._cache.get_width() != largura or self._cache.get_height() != altura:
            self._cache = self._roda(largura, altura)
        cr.set_source_surface(self._cache, 0, 0)
        cr.paint()
        # marcador: círculo com a cor escolhida, borda branca e sombra escura
        raio = min(largura, altura) / 2 - 6
        x = largura / 2 + math.cos(self.matiz * 2 * math.pi) * self.saturacao * raio
        y = altura / 2 + math.sin(self.matiz * 2 * math.pi) * self.saturacao * raio
        cr.set_source_rgb(*colorsys.hsv_to_rgb(self.matiz, self.saturacao, 1))
        cr.arc(x, y, 8, 0, 2 * math.pi)
        cr.fill_preserve()
        cr.set_line_width(3)
        cr.set_source_rgba(0, 0, 0, 0.6)
        cr.stroke_preserve()
        cr.set_line_width(1.5)
        cr.set_source_rgb(1, 1, 1)
        cr.stroke()


# ---------- quadrado de cor (prévia) ----------

class PreviaCor(Gtk.DrawingArea):
    def __init__(self, largura=46, altura=30):
        super().__init__(content_width=largura, content_height=altura, css_classes=["previa-cor"],
                         valign=Gtk.Align.CENTER)
        self.rgb = (0, 0, 0)
        self.set_draw_func(self._desenhar)

    def definir(self, rgb):
        self.rgb = rgb
        self.queue_draw()

    def _desenhar(self, _area, cr, largura, altura):
        cr.set_source_rgb(*(c / 255 for c in self.rgb))
        cr.paint()


# ---------- barras por hora ----------

class BarrasPorHora(Gtk.DrawingArea):
    """Gráfico de 24 barras (uma por hora), da mais antiga (esquerda) até agora (direita)."""

    def __init__(self, altura=150):
        super().__init__(content_height=altura, hexpand=True)
        self.dados = [0] * 24
        self.set_draw_func(self._desenhar)

    def definir(self, dados):
        self.dados = list(dados)
        self.queue_draw()

    def _desenhar(self, _area, cr, largura, altura):
        base = altura - 20
        maximo = max(max(self.dados), 1)
        passo = largura / len(self.dados)
        fonte(cr, "Inter", 10)
        # linha de base
        cr.set_source_rgb(*BORDA)
        cr.rectangle(0, base, largura, 1)
        cr.fill()
        for i, valor in enumerate(self.dados):
            h = (base - 14) * valor / maximo
            # a última hora (agora) em ciano forte; as outras um pouco mais apagadas
            cr.set_source_rgba(*CIANO, 1.0 if i == len(self.dados) - 1 else 0.55)
            cr.rectangle(i * passo + 2, base - h, passo - 4, h)
            cr.fill()
        cr.set_source_rgb(*APAGADO)
        for texto, x in (("-24 h", 0), ("-12 h", largura / 2 - 12), ("agora", largura - 30)):
            cr.move_to(x, altura - 4)
            cr.show_text(texto)
        cr.move_to(0, 10)
        cr.show_text(f"máx. {maximo}/h")
