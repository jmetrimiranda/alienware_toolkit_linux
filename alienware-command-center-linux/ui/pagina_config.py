"""Páginas simples da parte de baixo da barra lateral: Configurações e Sobre."""

import os
import subprocess

from gi.repository import Gdk, Gtk

import aparencia
from ui.widgets import Ilustracao, dica, rgb_para_hex, rotulo, titulo

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPOSITORIO = os.path.dirname(PASTA)


def _pagina(primeira, segunda):
    caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16,
                    margin_start=28, margin_end=28, margin_top=4, margin_bottom=28)
    caixa.append(titulo(primeira, segunda))
    return caixa


def _bloco(titulo_bloco, texto):
    bloco = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["bloco"])
    bloco.append(rotulo(titulo_bloco, "secao"))
    bloco.append(rotulo(texto, "texto-ajuda", wrap=True))
    return bloco


class PaginaConfig(Gtk.ScrolledWindow):
    def __init__(self, janela):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        caixa = _pagina("ALIENFX", "Configurações")
        caixa.append(self._bloco_aparencia())

        bloco = _bloco("PERMISSÕES (UDEV)",
                       "O Linux só deixa o painel falar com o mouse AW720M e com o dongle do AW725H depois de "
                       "instalar a regra udev/70-alienware-toolkit.rules (uma vez, com a sua senha). O teclado fica "
                       "de fora de propósito: a interface dele também carrega as teclas digitadas. A regra opcional "
                       "udev/71-sinowealth-keyboard-optional.rules só entra com ./install.sh --keyboard-experimental.")
        botao = dica(Gtk.Button(label="INSTALAR PERMISSÃO", css_classes=["contorno"], halign=Gtk.Align.START),
                     "Roda udev/install-udev-rules.sh com pkexec (pede a senha) e instala só a regra principal "
                     "(mouse e headset). Só precisa se o mouse aparecer como \"sem permissão\".")
        botao.connect("clicked", lambda _b: janela.pagina_mouse.dar_permissao())
        bloco.append(botao)
        caixa.append(bloco)

        bloco = _bloco("REGISTROS",
                       "logs/painel-AAAAMMDD.txt (log do painel), logs/bateria.json (último aviso de bateria do mouse) "
                       "e ~/.local/state/alienware-toolkit/aw725h.json (última bateria do headset). "
                       "O protetor do headset grava o estado em ~/.local/state/aw725h-guard/status.json e o log "
                       "no journal (journalctl --user -u alienware-headset-guard).")
        botao = dica(Gtk.Button(label="ABRIR PASTA LOGS", css_classes=["contorno"], halign=Gtk.Align.START),
                     "Abre a pasta logs/ do painel no gerenciador de arquivos.")
        botao.connect("clicked", lambda _b: self._abrir_logs())
        bloco.append(botao)
        caixa.append(bloco)

        caixa.append(_bloco("ATUALIZAÇÃO",
                            "A lista de aparelhos USB e a conexão do mouse são lidas a cada 2 s; o estado do "
                            "headset a cada 10 s enquanto a página dele está aberta."))
        self.set_child(caixa)

    def _bloco_aparencia(self):
        """Cor do aparelho no 3D, por dispositivo: preto, branco ou personalizada (aparencia.json)."""
        bloco = _bloco("COR DO APARELHO (3D)",
                       "A cor do corpo de cada aparelho no visualizador 3D. Os periféricos Alienware vêm em "
                       "Dark Side of the Moon (preto) ou Lunar Light (branco). Fica guardado em "
                       "~/.config/alienware-toolkit/aparencia.json. Não muda nada no aparelho.")
        grade = Gtk.Grid(column_spacing=10, row_spacing=8, margin_top=4)
        atuais = aparencia.ler()
        for linha, (aparelho, nome) in enumerate(aparencia.APARELHOS.items()):
            grade.attach(rotulo(nome.upper(), "secao", valign=Gtk.Align.CENTER, width_chars=20), 0, linha, 1, 1)
            grupo = None
            botoes = {}
            for coluna, (chave, texto) in enumerate((("preto", "DARK SIDE OF THE MOON"), ("branco", "LUNAR LIGHT"),
                                                     ("personalizada", "PERSONALIZADA")), start=1):
                botao = Gtk.ToggleButton(label=texto, group=grupo, css_classes=["contorno"])
                grupo = grupo or botao
                explicacao = {"preto": "Corpo preto (Dark Side of the Moon), o padrão.",
                              "branco": "Corpo branco (Lunar Light).",
                              "personalizada": "Usa a cor escolhida no quadrado ao lado."}[chave]
                dica(botao, f"{nome}: {explicacao}")
                grade.attach(botao, coluna, linha, 1, 1)
                botoes[chave] = botao
            cor = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False), valign=Gtk.Align.CENTER)
            dica(cor, f"{nome}: escolher a cor personalizada do corpo no 3D.")
            grade.attach(cor, 4, linha, 1, 1)
            valor = atuais[aparelho]
            rgba = Gdk.RGBA()
            rgba.parse(aparencia.cor_hex(aparelho) if valor not in aparencia.OPCOES else "#3a0ca3")
            cor.set_rgba(rgba)
            botoes[valor if valor in aparencia.OPCOES else "personalizada"].set_active(True)
            for chave, botao in botoes.items():
                botao.connect("toggled", self._cor_mudou, aparelho, chave, cor)
            cor.connect("notify::rgba", lambda c, _p, a=aparelho, b=botoes: self._cor_personalizada(a, b, c))
        bloco.append(grade)
        return bloco

    @staticmethod
    def _hex_do_botao(botao_cor):
        rgba = botao_cor.get_rgba()
        return rgb_para_hex(tuple(round(c * 255) for c in (rgba.red, rgba.green, rgba.blue))).lower()

    def _cor_mudou(self, botao, aparelho, chave, botao_cor):
        if botao.get_active():
            aparencia.definir(aparelho, self._hex_do_botao(botao_cor) if chave == "personalizada" else chave)

    def _cor_personalizada(self, aparelho, botoes, botao_cor):
        if botoes["personalizada"].get_active():
            aparencia.definir(aparelho, self._hex_do_botao(botao_cor))
        else:
            botoes["personalizada"].set_active(True)  # escolher uma cor já liga a opção personalizada

    @staticmethod
    def _abrir_logs():
        pasta = os.path.join(PASTA, "logs")
        os.makedirs(pasta, exist_ok=True)
        subprocess.Popen(["xdg-open", pasta])


class PaginaSobre(Gtk.ScrolledWindow):
    def __init__(self, janela):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        caixa = _pagina("ALIENFX", "Sobre")
        linha = Gtk.Box(spacing=28)
        logo = dica(Ilustracao("logo.svg", 120, 140), "Logo do Alienware Toolkit (desenho próprio, não é o logo oficial).")
        logo.set_hexpand(False)
        logo.set_vexpand(False)
        linha.append(logo)
        textos = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.CENTER)
        textos.append(rotulo("ALIENWARE TOOLKIT FOR LINUX", "valor-medio"))
        textos.append(rotulo("Interface v3 · GTK4 + libadwaita · WebKit 6.0 + three.js · Python", "dim"))
        textos.append(rotulo("github.com/jmetrimiranda/alienware_toolkit_linux", "dim", "mono", selectable=True))
        linha.append(textos)
        caixa.append(linha)
        caixa.append(_bloco("O QUE FAZ",
                            "Mouse AW720M: cor, zonas, efeito, brilho e bateria (pelo protocolo APIv7 do "
                            "alienfx-tools, de T-Troll, confirmado no AW720M em 29/10/2026). Headset AW725H: estado, "
                            "reinícios do dongle, proteção contra quedas, áudio, microfone, equalizador, bateria e "
                            "prévia da luz. Teclado Redragon K617 Fizz Rainbow: prévia 3D, atalhos Fn e leitura. "
                            "Outros aparelhos: só informações. Modelos 3D procedurais com three.js (MIT)."))
        caixa.append(_bloco("AVISO",
                            "Projeto pessoal, sem ligação com a Dell/Alienware. Para firmware, macros, DPI e o "
                            "resto, use o Alienware Command Center no Windows."))
        self.set_child(caixa)
