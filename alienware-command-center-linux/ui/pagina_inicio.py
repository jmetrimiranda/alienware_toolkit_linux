"""Início: cartões com os aparelhos USB conectados. Atualiza a cada 2 s.

Clicar num cartão abre a página do aparelho (mouse, headset ou "somente informações").
"""

from gi.repository import GLib, Gtk

import dispositivos
from ui.widgets import AnelBateria, Ilustracao, dica, rotulo, titulo

ARQUIVO_SVG = {"mouse": "mouse.svg", "headset": "headset.svg", "teclado": "teclado.svg", "usb": "usb.svg"}
# Desenho próprio para aparelhos suportados que têm ilustração específica
SVG_DO_ID = {"258a:002a": "teclado-k617.svg"}


class PaginaInicio(Gtk.Box):
    def __init__(self, janela):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.janela = janela
        self.assinatura = None  # lista de portas+IDs da última vez (só redesenha se mudar)
        self.aneis = []  # (tipo, anel) dos cartões com bateria: mouse e headset

        topo = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                       margin_start=28, margin_end=28, margin_top=4, margin_bottom=18)
        topo.append(titulo("ALIENFX", "Dispositivos"))
        self.resumo = rotulo("", "dim")
        topo.append(self.resumo)
        self.append(topo)

        self.grade = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=18, row_spacing=18,
                                 min_children_per_line=2, max_children_per_line=4, homogeneous=True,
                                 valign=Gtk.Align.START, margin_start=28, margin_end=28, margin_bottom=28)
        self.append(Gtk.ScrolledWindow(child=self.grade, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER))

        self.atualizar()
        GLib.timeout_add_seconds(2, self.atualizar)

    def atualizar(self):
        lista = dispositivos.listar_usb()
        assinatura = [(d["porta"], d["id"]) for d in lista]
        if assinatura != self.assinatura:
            self.assinatura = assinatura
            self._redesenhar(lista)
        self._atualizar_bateria()
        suportados = sum(d["suportado"] for d in lista)
        self.resumo.set_text(f"{len(lista)} aparelho(s) USB conectado(s) · {suportados} configurável(is) · "
                             "atualiza a cada 2 s")
        return True  # mantém o timer

    def _atualizar_bateria(self):
        mouse = self.janela.pagina_mouse.bateria
        headset = self.janela.pagina_headset.extras.leitor.estado
        for tipo, anel in self.aneis:
            if tipo == "mouse":
                anel.definir(mouse["bateria"] if mouse else None, mouse["carregando"] if mouse else False)
            else:  # headset: uma bateria só para os dois lados
                anel.definir(headset.get("bateria"), bool(headset.get("carregando")))

    def _redesenhar(self, lista):
        while (filho := self.grade.get_first_child()):
            self.grade.remove(filho)
        self.aneis = []
        # Os suportados primeiro, depois o resto pela porta
        for d in sorted(lista, key=lambda d: (not d["suportado"], d["porta"])):
            self.grade.append(self._cartao(d))

    def _cartao(self, d):
        botao = Gtk.Button(css_classes=["cartao"], width_request=250)
        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                        margin_top=14, margin_bottom=16, margin_start=16, margin_end=16)

        topo = Gtk.Box(spacing=8)
        if d["suportado"] and d["tipo"] == "teclado":
            topo.append(dica(Gtk.Label(label="PRÉVIA + LEITURA", css_classes=["etiqueta", "suportado"],
                                       valign=Gtk.Align.START),
                             "Página própria, mas sem controle de luz: as cores do K617 Rainbow são de fábrica."))
        elif d["suportado"]:
            topo.append(Gtk.Label(label="SUPORTADO", css_classes=["etiqueta", "suportado"], valign=Gtk.Align.START))
        else:
            topo.append(Gtk.Label(label="SOMENTE INFORMAÇÕES", css_classes=["etiqueta"], valign=Gtk.Align.START))
        topo.append(rotulo("", hexpand=True))
        if d["tipo"] in ("mouse", "headset"):
            anel = AnelBateria(52, 4, texto_grande=False)
            dica(anel, "Bateria do último aviso do aparelho (— = ainda não informada)."
                       + (" O headset tem uma bateria só, para os dois lados." if d["tipo"] == "headset" else ""))
            self.aneis.append((d["tipo"], anel))
            topo.append(anel)
        caixa.append(topo)

        figura = Ilustracao(SVG_DO_ID.get(d["id"], ARQUIVO_SVG[d["tipo"]]), altura=130)
        figura.set_can_target(False)
        caixa.append(figura)

        caixa.append(rotulo(d["nome"].upper(), "nome", ellipsize=3, margin_top=8))
        if d["tipo"] == "mouse":
            linha = f"{d['modo']} · bateria no anel"
            explicacao = (f"Abre a configuração do mouse: iluminação, bateria e diagnóstico. "
                          f"Conectado pelo {d['modo']}; o anel mostra o último aviso de bateria.")
        elif d["tipo"] == "headset":
            linha = "Headset sem fio · dongle 2.4G · bateria no anel"
            explicacao = ("Abre o headset: estado, reinícios do dongle, proteção contra quedas, áudio, microfone, "
                          "equalizador, prévia da luz e bateria.")
        elif d["tipo"] == "teclado" and d["suportado"]:
            linha = "Teclado 60% · cores de fábrica · prévia e atalhos Fn"
            explicacao = ("Abre o teclado: prévia 3D do modo, brilho e velocidade (o que as teclas Fn fazem), "
                          "tabela de atalhos Fn e leitura dos dados. Nada é enviado ao teclado.")
        else:
            linha = f"{d['tipo_texto']} · {d['fabricante']}"
            explicacao = "Abre uma página só com dados (fabricante, ID, velocidade, porta). Nada é configurado."
        caixa.append(rotulo(linha, "dim", ellipsize=3))
        caixa.append(rotulo(f"{d['id']} · porta {d['porta']} · {d['velocidade'].split(' · ')[-1]}",
                            "dim", "mono", ellipsize=3))
        botao.set_child(caixa)
        dica(botao, explicacao)
        botao.connect("clicked", lambda _b: self.janela.abrir_dispositivo(d))
        return botao
