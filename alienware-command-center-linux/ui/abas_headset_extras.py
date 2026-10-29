"""Abas extras da página do headset AW725H: Microfone, Equalizador, Iluminação e Bateria.

Integração (sem reescrever ui/pagina_headset.py): copie headset_aw725h.py e equalizador.py para a
raiz do app, este arquivo para ui/, e acrescente no fim do PaginaHeadset.__init__:

    from ui.abas_headset_extras import adicionar_abas_extras
    self.extras = adicionar_abas_extras(self)

O que cada aba faz:
- MICROFONE: ganho e mudo de hardware do microfone e dos fones (amixer -c Dongle), retorno da
  própria voz por software (pw-loopback) e o último botão do headset visto no canal HID.
- EQUALIZADOR: EQ por software no PipeWire (sink "AW725H EQ"), presets e 10 bandas; nada muda
  antes de ✓ APLICAR.
- ILUMINAÇÃO: só PRÉ-VISUALIZAÇÃO (no 3D, se a página tiver o visualizador; senão num desenho
  próprio). O protocolo da luz do AW725H é desconhecido: requer captura no Windows.
- BATERIA: o que o canal HID (lido em modo só leitura) revelou e os dados do manual.

Nada aqui escreve no canal HID do dongle.
"""

import atexit
import colorsys
import math
import os

import cairo
from gi.repository import GLib, Gtk

import equalizador as eq
import headset_aw725h as hs
from ui.widgets import (CIANO, AnelBateria, PreviaCor, RodaDeCores, dica, em_segundo_plano, fonte,
                        grade_info, hex_para_rgb, rgb_para_hex, rotulo)

# modo de captura de tela ou demonstração: não liga nada e não grava estado
CAPTURA = "ALIENWARE_CAPTURA" in os.environ or "ALIENWARE_DEMO" in os.environ

EFEITOS = ["fixo", "respirar", "transição", "espectro", "pulsar", "arco-íris"]
EFEITOS_DESCRICAO = {
    "fixo": "Cor parada, sempre acesa.",
    "respirar": "Acende e apaga devagar.",
    "transição": "Alterna entre a cor principal e a 2ª cor.",
    "espectro": "Passa por todas as cores sozinho.",
    "pulsar": "Pisca na cor escolhida.",
    "arco-íris": "Gira pelas cores 100% saturadas, mais rápido que o espectro.",
}
AVISO_LUZ = ("REQUER CAPTURA NO WINDOWS: o protocolo da luz do AW725H ainda não é conhecido. "
             "Esta aba só pré-visualiza; nada é enviado ao headset.")


def adicionar_abas_extras(pagina):
    """Cria as 4 abas na página do headset e devolve o controlador (guarde em self.extras)."""
    return ExtrasHeadset(pagina)


class ExtrasHeadset:
    """Liga as abas novas à página: leitor HID passivo, timer e troca de abas."""

    def __init__(self, pagina):
        self.pagina = pagina
        # Última bateria e aviso 01 guardados para o próximo início (não grava nada no modo de captura)
        estado = None if CAPTURA else os.path.join(
            os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"),
            "alienware-toolkit", "aw725h.json")
        self.leitor = hs.LeitorPassivo(ao_evento=lambda ev: GLib.idle_add(self._evento, ev),
                                       arquivo_estado=estado)
        self.leitor.start()
        self.monitor = hs.MonitorMicrofone()
        atexit.register(self.monitor.parar)  # o pw-loopback não pode ficar órfão quando o app fecha

        self.abas = {
            "microfone": AbaMicrofone(self),
            "equalizador": AbaEqualizador(self),
            "iluminacao": AbaIluminacao(self),
            "bateria": AbaBateria(self),
        }
        explicacoes = {
            "microfone": "Ganho e mudo do microfone e dos fones no próprio dongle (ALSA) e retorno da sua voz.",
            "equalizador": "Equalizador por software no PipeWire: presets e 10 bandas para o AW725H.",
            "iluminacao": "Pré-visualização da luz do logo. Mudar a luz de verdade requer captura no Windows.",
            "bateria": "Bateria e avisos do canal HID do dongle (lido sem enviar nada).",
        }
        # Rótulos curtos: com 8 abas, nomes longos deixariam a janela mais larga que 1280 px
        nomes = {"microfone": "Mic", "equalizador": "EQ", "iluminacao": "Luz", "bateria": "Bateria"}
        for nome, aba in self.abas.items():
            pagina.abas.adicionar(nome, nomes[nome], aba.widget, explicacoes[nome])

        # A página base trata só as abas dela em ao_trocar; as novas passam por aqui antes
        original = pagina.abas.ao_trocar

        def ao_trocar(nome):
            if nome in self.abas:
                self.abas[nome].atualizar()
            elif original:
                original(nome)
        pagina.abas.ao_trocar = ao_trocar
        GLib.timeout_add_seconds(2, self._timer)
        for aba in self.abas.values():
            aba.atualizar()

    def _timer(self):
        """A cada 2 s, só a aba nova que estiver aberta relê os dados."""
        if self.pagina.get_mapped():
            aba = self.abas.get(self.pagina.abas.atual())
            if aba:
                aba.atualizar(periodico=True)
        return True

    def _evento(self, ev):
        for aba in self.abas.values():
            if hasattr(aba, "ao_evento"):
                aba.ao_evento(ev)
        return False

    def visualizador(self):
        """Visualizador 3D da página (job aw3-3d), se já estiver integrado; senão None."""
        for nome in ("visualizador3d", "visualizador", "vis3d"):
            vis = getattr(self.pagina, nome, None)
            if vis is not None and hasattr(vis, "set_light"):
                return vis
        return None


def _bloco(titulo, explicacao=None):
    """Caixa com borda (classe .bloco) e o título da seção."""
    caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["bloco"])
    topo = Gtk.Box(spacing=10)
    topo.append(rotulo(titulo, "secao", hexpand=True))
    caixa.append(topo)
    if explicacao:
        caixa.set_tooltip_text(explicacao)
    caixa.topo = topo
    return caixa


# =====================================================================
# MICROFONE
# =====================================================================

class AbaMicrofone:
    def __init__(self, extras):
        self.extras = extras
        self.atualizando = False
        self.pendente = {}
        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.rotulo_estado = rotulo("lendo o mixer do dongle...", "dim", wrap=True)
        caixa.append(self.rotulo_estado)

        # --- microfone ---
        bloco = _bloco("MICROFONE (GANHO NO DONGLE)")
        self.mic_ligado = self._chave(bloco.topo, "mic_ligado",
                                      "Liga/desliga o microfone no próprio dongle ('Headset Capture Switch'). "
                                      "Desligado, nenhum app recebe a sua voz.")
        self.mic = self._escala(bloco, "mic", 0, 30,
                                "Ganho do microfone no dongle ('Headset Capture Volume', 0–30 = −30 a 0 dB). "
                                "Muda na hora.")
        caixa.append(bloco)

        # --- fones ---
        bloco = _bloco("FONES (VOLUME DE HARDWARE)")
        self.som = self._chave(bloco.topo, "som",
                               "Liga/desliga o som dos fones no dongle ('PCM Playback Switch').")
        self.volume = self._escala(bloco, "volume", 0, 74,
                                   "Volume dos fones no dongle ('PCM Playback Volume', 0–74 = −74 a 0 dB). "
                                   "É o mesmo controle que o PipeWire usa: o volume do GNOME acompanha.")
        caixa.append(bloco)

        # --- retorno da voz ---
        bloco = _bloco("OUVIR A PRÓPRIA VOZ (MONITOR)")
        self.chave_monitor = dica(Gtk.Switch(valign=Gtk.Align.CENTER),
                                  "Toca o microfone do headset nos próprios fones (pw-loopback). "
                                  "Por software: há ~40–80 ms de atraso.")
        self.chave_monitor.connect("state-set", self._monitor_mudou)
        bloco.topo.append(self.chave_monitor)
        linha = Gtk.Box(spacing=12)
        self.volume_monitor = dica(Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1),
                                   "Volume do retorno da sua voz (0 a 100%).")
        self.volume_monitor.set_value(50)
        self.volume_monitor.set_hexpand(True)
        self.volume_monitor.connect("value-changed", self._volume_monitor_mudou)
        linha.append(self.volume_monitor)
        self.valor_monitor = rotulo("50%", "valor-medio", width_chars=4, xalign=1)
        linha.append(self.valor_monitor)
        bloco.append(linha)
        self.rotulo_monitor = rotulo(
            "O AW725H não expõe sidetone de hardware no Linux; isto é um retorno por software.",
            "texto-ajuda", wrap=True)
        bloco.append(self.rotulo_monitor)
        caixa.append(bloco)

        # --- botões do headset ---
        bloco = _bloco("BOTÕES DO HEADSET (CANAL HID)")
        self.rotulo_botao = rotulo("nenhum botão visto ainda", "dim", wrap=True)
        bloco.append(self.rotulo_botao)
        bloco.append(rotulo(
            "O mudo do microfone do headset (botão vermelho ou microfone recolhido) é feito dentro do "
            "headset e não aparece no mixer. Os botões de mídia chegam como teclas de volume/play.",
            "texto-ajuda", wrap=True))
        caixa.append(bloco)
        self.widget = self.extras.pagina.rolavel(caixa)

    def _chave(self, topo, chave, explicacao):
        topo.append(rotulo("Ligado", "dim"))
        sw = dica(Gtk.Switch(valign=Gtk.Align.CENTER), explicacao)
        sw.connect("notify::active", lambda s, _p: self._mudou(chave, s.get_active()))
        topo.append(sw)
        return sw

    def _escala(self, bloco, chave, minimo, maximo, explicacao):
        linha = Gtk.Box(spacing=12)
        escala = dica(Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, minimo, maximo, 1), explicacao)
        escala.set_hexpand(True)
        escala.add_mark(maximo, Gtk.PositionType.BOTTOM, "0 dB")
        linha.append(escala)
        valor = rotulo("—", "valor-medio", width_chars=7, xalign=1)
        linha.append(valor)
        bloco.append(linha)
        escala.connect("value-changed", lambda e: self._escala_mudou(chave, e, valor, maximo))
        return escala

    def atualizar(self, periodico=False):
        em_segundo_plano(hs.ler_mixer, self._mostrar)
        if periodico:
            self._mostrar_monitor()

    def _mostrar(self, m):
        if m["erro"] or m["volume"] is None:
            self.rotulo_estado.set_text(f"Mixer do dongle indisponível: {m['erro'] or 'dongle desconectado'}")
            return
        self.rotulo_estado.set_text("Ajustes gravados no dongle na hora (amixer -c Dongle).")
        self.atualizando = True
        for chave, widget in (("mic", self.mic), ("volume", self.volume)):
            if chave not in self.pendente:  # não atropela quem está arrastando
                widget.set_value(m[chave])
        self.mic_ligado.set_active(bool(m["mic_ligado"]))
        self.som.set_active(bool(m["som"]))
        self.atualizando = False
        self._mostrar_monitor()

    def _escala_mudou(self, chave, escala, valor, maximo):
        passo = round(escala.get_value())
        valor.set_text(f"{hs.passo_para_db(passo, maximo)} dB")
        if self.atualizando:
            return
        # Espera parar de arrastar (250 ms) antes de chamar o amixer
        if chave in self.pendente:
            GLib.source_remove(self.pendente[chave])
        self.pendente[chave] = GLib.timeout_add(250, self._aplicar, chave, passo)

    def _aplicar(self, chave, valor):
        self.pendente.pop(chave, None)
        if not CAPTURA:
            em_segundo_plano(lambda: hs.definir(chave, valor), lambda _r: None)
        return False

    def _mudou(self, chave, ligado):
        if not self.atualizando and not CAPTURA:
            em_segundo_plano(lambda: hs.definir(chave, ligado), lambda _r: self.atualizar())

    # --- monitor da voz ---

    def _monitor_mudou(self, _sw, ligar):
        if self.atualizando or CAPTURA:
            return False
        volume = self.volume_monitor.get_value() / 100

        def fazer():
            if ligar:
                return self.extras.monitor.iniciar(volume)
            self.extras.monitor.parar()
            return True, "desligado"
        em_segundo_plano(fazer, self._monitor_terminou)
        return True  # o estado visual muda depois de confirmar

    def _monitor_terminou(self, resultado):
        ok, msg = resultado
        if not ok:
            self.rotulo_monitor.set_text(f"Não consegui ligar o retorno: {msg}")
        self._mostrar_monitor()

    def _mostrar_monitor(self):
        ativo = self.extras.monitor.ativo
        self.atualizando = True  # set_active emite state-set de novo; sem a trava, ligaria/desligaria outra vez
        self.chave_monitor.set_state(ativo)
        self.chave_monitor.set_active(ativo)
        self.atualizando = False

    def _volume_monitor_mudou(self, escala):
        self.valor_monitor.set_text(f"{round(escala.get_value())}%")
        if "monitor" in self.pendente:  # espera parar de arrastar (250 ms), como no mixer
            GLib.source_remove(self.pendente["monitor"])
        self.pendente["monitor"] = GLib.timeout_add(250, self._aplicar_volume_monitor)

    def _aplicar_volume_monitor(self):
        self.pendente.pop("monitor", None)
        if self.extras.monitor.ativo:
            volume = self.volume_monitor.get_value() / 100
            em_segundo_plano(lambda: self.extras.monitor.definir_volume(volume), lambda _r: None)
        return False

    def ao_evento(self, ev):
        if ev.tipo == "botao" and ev.valores.get("botoes"):
            self.rotulo_botao.set_text(f"{ev.hora}  {ev.descricao}")


# =====================================================================
# EQUALIZADOR
# =====================================================================

class CurvaEQ(Gtk.DrawingArea):
    """Gráfico da resposta do EQ (20 Hz–20 kHz em escala log, −12 a +12 dB)."""

    def __init__(self):
        super().__init__(content_height=112, hexpand=True)
        self.ganhos = [0] * 10
        self.set_draw_func(self._desenhar)

    def definir(self, ganhos):
        self.ganhos = list(ganhos)
        self.queue_draw()

    def _desenhar(self, _area, cr, largura, altura):
        m_esq, m_dir, m_cima, m_baixo = 34, 8, 8, 18
        w, h = largura - m_esq - m_dir, altura - m_cima - m_baixo

        def x_de(f):
            return m_esq + w * math.log10(f / 20) / 3  # 20 Hz → 20 kHz = 3 décadas

        def y_de(db):
            return m_cima + h * (1 - (db + 12) / 24)

        fonte(cr, "Inter", 10)
        cr.set_line_width(1)
        for db in (-12, -6, 0, 6, 12):
            cr.set_source_rgba(1, 1, 1, 0.16 if db == 0 else 0.06)
            cr.move_to(m_esq, y_de(db))
            cr.line_to(m_esq + w, y_de(db))
            cr.stroke()
            cr.set_source_rgb(0.54, 0.56, 0.6)
            cr.move_to(2, y_de(db) + 3)
            cr.show_text(f"{db:+d}" if db else "0")
        for f, texto in ((31, "31"), (125, "125"), (500, "500"), (2000, "2k"), (8000, "8k"), (16000, "16k")):
            cr.set_source_rgba(1, 1, 1, 0.06)
            cr.move_to(x_de(f), m_cima)
            cr.line_to(x_de(f), m_cima + h)
            cr.stroke()
            cr.set_source_rgb(0.54, 0.56, 0.6)
            cr.move_to(x_de(f) - 8, altura - 4)
            cr.show_text(texto)
        # Só o formato (como os sliders); o pré-ganho que evita saturar vai escrito no canto
        curva = eq.resposta_em_frequencia(self.ganhos, com_pre_ganho=False)
        pre = eq.pre_ganho(self.ganhos)
        if pre < 0:
            cr.set_source_rgb(0.54, 0.56, 0.6)
            cr.move_to(m_esq + w - 104, m_cima + 10)
            cr.show_text(f"pré-ganho {pre:.1f} dB")
        # Área preenchida entre a curva e a linha de 0 dB
        cr.move_to(x_de(curva[0][0]), y_de(0))
        for f, db in curva:
            cr.line_to(x_de(f), y_de(max(-12, min(12, db))))
        cr.line_to(x_de(curva[-1][0]), y_de(0))
        cr.close_path()
        cr.set_source_rgba(*CIANO, 0.12)
        cr.fill()
        cr.set_source_rgb(*CIANO)
        cr.set_line_width(2)
        for i, (f, db) in enumerate(curva):
            (cr.move_to if i == 0 else cr.line_to)(x_de(f), y_de(max(-12, min(12, db))))
        cr.stroke()


class AbaEqualizador:
    def __init__(self, extras):
        self.extras = extras
        self.atualizando = False
        self.ajustes = eq.ler_ajustes()
        self.preset = self.ajustes.get("preset", "plano")
        self.aplicado = (self.preset, eq.ganhos_do_preset(self.preset, self.ajustes))

        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        bloco = _bloco("EQUALIZADOR (SOFTWARE, PIPEWIRE)")
        self.chave = dica(Gtk.Switch(valign=Gtk.Align.CENTER),
                          "Liga/desliga o sink virtual \"AW725H EQ\" (filter-chain do PipeWire). Ligar grava "
                          "~/.config/pipewire/filter-chain.conf.d/aw725h-eq.conf e reinicia só o "
                          "filter-chain.service; desligar apaga o arquivo e volta a saída para o AW725H.")
        self.chave.connect("state-set", self._chave_mudou)
        bloco.topo.append(self.chave)
        self.rotulo_estado = rotulo("verificando...", "dim", wrap=True)
        bloco.append(self.rotulo_estado)
        self.padrao = dica(Gtk.CheckButton(label="Usar o AW725H EQ como saída padrão ao ligar", active=True),
                           "Com isto marcado, o som do sistema passa pelo EQ assim que ele liga "
                           "(wpctl set-default). Desmarcado, escolha o \"AW725H EQ\" no app que quiser.")
        bloco.append(self.padrao)
        caixa.append(bloco)

        # --- presets ---
        linha = Gtk.Box(spacing=8)
        self.botoes = {}
        grupo = None
        for chave, p in eq.PRESETS.items():
            botao = dica(Gtk.ToggleButton(label=p["nome"].upper(), css_classes=["contorno"], group=grupo), p["dica"])
            grupo = grupo or botao
            botao.connect("toggled", self._preset_escolhido, chave)
            linha.append(botao)
            self.botoes[chave] = botao
        caixa.append(linha)

        # --- curva + 10 bandas ---
        self.curva = dica(CurvaEQ(), "Formato da resposta do EQ. O pré-ganho (no canto) abaixa tudo por igual "
                                      "para os reforços não saturarem o som.")
        caixa.append(self.curva)
        faixas = Gtk.Box(spacing=4, homogeneous=True)
        self.escalas = []
        self.valores = []
        for i, freq in enumerate(eq.BANDAS):
            coluna = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            nome = f"{freq // 1000}k" if freq >= 1000 else str(freq)
            valor = rotulo("0", "dim", xalign=0.5)
            escala = Gtk.Scale.new_with_range(Gtk.Orientation.VERTICAL, -eq.LIMITE_DB, eq.LIMITE_DB, 0.5)
            escala.set_inverted(True)  # para cima = mais
            escala.set_size_request(-1, 104)
            escala.add_mark(0, Gtk.PositionType.LEFT, None)
            dica(escala, f"Banda de {nome}Hz: de −12 a +12 dB. Mexer aqui passa para o preset Personalizado.")
            escala.connect("value-changed", self._banda_mudou, i)
            coluna.append(valor)
            coluna.append(escala)
            coluna.append(rotulo(nome, "secao", xalign=0.5))
            faixas.append(coluna)
            self.escalas.append(escala)
            self.valores.append(valor)
        caixa.append(faixas)

        # --- aplicar / cancelar (a página pode mover para a barra inferior) ---
        botoes = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        self.cancelar_botao = dica(Gtk.Button(label="✕  CANCELAR", css_classes=["cancelar"]),
                                   "Volta ao preset e às bandas que estão aplicados agora.")
        self.cancelar_botao.connect("clicked", lambda _b: self.cancelar())
        self.aplicar_botao = dica(Gtk.Button(label="✓  APLICAR", css_classes=["aplicar"]),
                                  "Aplica o preset/bandas: com o EQ ligado muda na hora (pw-cli, sem cortar o "
                                  "som) e grava para o próximo início; com o EQ desligado, só guarda a escolha.")
        self.aplicar_botao.connect("clicked", lambda _b: self.aplicar())
        botoes.append(self.cancelar_botao)
        botoes.append(self.aplicar_botao)
        caixa.append(botoes)
        caixa.append(rotulo(
            "Como funciona: os apps tocam no sink \"AW725H EQ\"; ele aplica 10 filtros biquad e manda o som "
            "para o AW725H. A saída do EQ é um stream comum do AW725H, então o protetor (aba Proteção) "
            "continua reabrindo o áudio a cada ~110 s normalmente (testado). O EQ do AWCC/Dolby é do "
            "Windows e não existe no dongle.", "texto-ajuda", wrap=True))
        self.widget = self.extras.pagina.rolavel(caixa)
        self._carregar(*self.aplicado)

    def _carregar(self, preset, ganhos):
        """Mostra um preset e as bandas sem marcar nada como pendente."""
        self.atualizando = True
        self.preset = preset
        self.botoes[preset].set_active(True)
        for escala, ganho in zip(self.escalas, ganhos):
            escala.set_value(ganho)
        self.atualizando = False
        self._redesenhar()

    def ganhos(self):
        return [round(e.get_value() * 2) / 2 for e in self.escalas]

    def tem_pendente(self):
        return (self.preset, self.ganhos()) != (self.aplicado[0], list(self.aplicado[1]))

    def _redesenhar(self):
        ganhos = self.ganhos()
        for valor, g in zip(self.valores, ganhos):
            valor.set_text(f"{g:+.1f}" if g else "0")
        self.curva.definir(ganhos)
        pendente = self.tem_pendente()
        self.aplicar_botao.set_sensitive(pendente)
        self.cancelar_botao.set_sensitive(pendente)

    def _preset_escolhido(self, botao, chave):
        if not botao.get_active() or self.atualizando:
            return
        ganhos = eq.ganhos_do_preset(chave, self.ajustes)
        self._carregar(chave, ganhos)

    def _banda_mudou(self, _escala, _i):
        if self.atualizando:
            return
        if self.preset != "personalizado":  # mexer numa banda vira "Personalizado"
            self.atualizando = True
            self.preset = "personalizado"
            self.botoes["personalizado"].set_active(True)
            self.atualizando = False
        self._redesenhar()

    def cancelar(self):
        self._carregar(*self.aplicado)

    def aplicar(self):
        preset, ganhos = self.preset, self.ganhos()
        self.ajustes["preset"] = preset
        if preset == "personalizado":
            self.ajustes["personalizado"] = ganhos
        self.ajustes["padrao"] = self.padrao.get_active()
        self.aplicado = (preset, ganhos)
        self._redesenhar()
        if CAPTURA:
            return
        eq.salvar_ajustes(self.ajustes)
        nome = eq.PRESETS[preset]["nome"]

        def fazer():
            est = eq.estado()
            if not est["ativo"]:
                return True, "escolha guardada (o EQ está desligado)"
            eq.gravar_fragmento(ganhos, nome)
            return eq.aplicar_ao_vivo(ganhos, est["id"])
        em_segundo_plano(fazer, self._terminou)

    def _chave_mudou(self, _sw, ligar):
        if self.atualizando:
            return False
        if CAPTURA:
            return True
        self.rotulo_estado.set_text("ligando..." if ligar else "desligando...")
        preset, ganhos = self.aplicado
        nome, como_padrao = eq.PRESETS[preset]["nome"], self.padrao.get_active()
        self.ajustes["ligado"] = ligar
        eq.salvar_ajustes(self.ajustes)
        em_segundo_plano(lambda: eq.ligar(ganhos, nome, como_padrao=como_padrao) if ligar else eq.desligar(),
                         self._terminou)
        return True

    def _terminou(self, resultado):
        ok, msg = resultado
        self.erro = None if ok else msg  # mostrado junto com o estado relido logo abaixo
        GLib.timeout_add(600, lambda: self.atualizar() and False)

    def atualizar(self, periodico=False):
        # pw-dump é pesado: no timer de 2 s, relê só a cada 3 voltas (~6 s)
        self.voltas = getattr(self, "voltas", 0) + 1
        if periodico and self.voltas % 3:
            return
        em_segundo_plano(eq.estado, self._mostrar_estado)

    def _mostrar_estado(self, est):
        self.atualizando = True
        self.chave.set_active(est["ativo"])
        self.chave.set_state(est["ativo"])
        self.atualizando = False
        if est["ativo"]:
            destino = est["saida_ligada_em"] or "nenhuma saída"
            alvo = "AW725H" if destino and "AW725H" in destino else destino
            self.rotulo_estado.set_text(f"Ligado: sink AW725H EQ (nó {est['id']}) → {alvo}. "
                                        f"Preset aplicado: {eq.PRESETS[self.aplicado[0]]['nome']}.")
        elif est["instalado"]:
            self.rotulo_estado.set_text("Configurado, mas o filter-chain.service não está rodando.")
        else:
            self.rotulo_estado.set_text("Desligado: o som vai direto para o AW725H.")
        if getattr(self, "erro", None):
            self.rotulo_estado.set_text(f"Falhou: {self.erro}. {self.rotulo_estado.get_text()}")
            self.erro = None


# =====================================================================
# ILUMINAÇÃO (só pré-visualização)
# =====================================================================

def _cor_do_efeito(efeito, cor1, cor2, t, velocidade):
    """Cor (0–1) e intensidade do LED no instante t, imitando os efeitos AlienFX."""
    fase = t * (0.25 + velocidade / 50)
    r1 = tuple(c / 255 for c in cor1)
    if efeito == "respirar":
        return r1, 0.15 + 0.85 * (0.5 - 0.5 * math.cos(2 * math.pi * fase))
    if efeito == "pulsar":
        return r1, 1.0 if (fase * 2) % 1 < 0.5 else 0.08
    if efeito == "transição":
        k = 0.5 - 0.5 * math.cos(2 * math.pi * fase)
        r2 = tuple(c / 255 for c in cor2)
        return tuple(a + (b - a) * k for a, b in zip(r1, r2)), 1.0
    if efeito in ("espectro", "arco-íris"):
        giro = fase * (0.35 if efeito == "espectro" else 1.0)
        return colorsys.hsv_to_rgb(giro % 1, 1, 1), 1.0
    return r1, 1.0


class PreviaLuz(Gtk.DrawingArea):
    """Desenho próprio da concha do AW725H com o logo aceso (usado quando não há visualizador 3D)."""

    def __init__(self):
        super().__init__(content_width=200, content_height=200, halign=Gtk.Align.CENTER)
        self.efeito, self.cor1, self.cor2, self.brilho, self.velocidade, self.ligado = \
            "fixo", (0, 200, 215), (255, 0, 160), 100, 50, True
        self.t = 0.0
        self.animando = None
        self.set_draw_func(self._desenhar)

    def definir(self, **valores):
        for chave, valor in valores.items():
            setattr(self, chave, valor)
        precisa_animar = self.ligado and self.efeito != "fixo" and self.brilho > 0
        if CAPTURA:
            # No broadway sem navegador, um widget animando deixa a captura da janela vazia:
            # mostra um quadro parado do efeito (t = 1,3 s, perto do pico do respirar)
            precisa_animar, self.t = False, 1.3
        if precisa_animar and self.animando is None:
            self.animando = GLib.timeout_add(40, self._passo)
        elif not precisa_animar and self.animando is not None:
            GLib.source_remove(self.animando)
            self.animando = None
        self.queue_draw()

    def _passo(self):
        if not self.get_mapped():
            return True  # escondida: não gasta desenho, mas segue viva para quando voltar
        self.t += 0.04
        self.queue_draw()
        return True

    @staticmethod
    def _cabeca(cr, cx, cy, w, h):
        """Silhueta de cabeça alienígena (larga em cima, queixo fino)."""
        cr.move_to(cx, cy + h * 0.5)
        cr.curve_to(cx - w * 0.22, cy + h * 0.38, cx - w * 0.5, cy + h * 0.08, cx - w * 0.5, cy - h * 0.14)
        cr.curve_to(cx - w * 0.5, cy - h * 0.42, cx - w * 0.26, cy - h * 0.5, cx, cy - h * 0.5)
        cr.curve_to(cx + w * 0.26, cy - h * 0.5, cx + w * 0.5, cy - h * 0.42, cx + w * 0.5, cy - h * 0.14)
        cr.curve_to(cx + w * 0.5, cy + h * 0.08, cx + w * 0.22, cy + h * 0.38, cx, cy + h * 0.5)
        cr.close_path()

    def _desenhar(self, _area, cr, largura, altura):
        cx, cy = largura / 2, altura / 2
        raio = min(largura, altura) / 2 - 6
        cor, intensidade = _cor_do_efeito(self.efeito, self.cor1, self.cor2, self.t, self.velocidade)
        intensidade *= (self.brilho / 100) if self.ligado else 0
        # halo atrás da concha
        if intensidade > 0:
            halo = cairo.RadialGradient(cx, cy, raio * 0.2, cx, cy, raio)
            halo.add_color_stop_rgba(0, *cor, 0.35 * intensidade)
            halo.add_color_stop_rgba(1, *cor, 0)
            cr.set_source(halo)
            cr.paint()
        # concha (anel externo + tampa)
        cr.arc(cx, cy, raio * 0.86, 0, 2 * math.pi)
        cr.set_source_rgb(0.16, 0.17, 0.19)
        cr.fill_preserve()
        cr.set_source_rgb(0.25, 0.27, 0.30)
        cr.set_line_width(2)
        cr.stroke()
        cr.arc(cx, cy, raio * 0.66, 0, 2 * math.pi)
        tampa = cairo.LinearGradient(cx, cy - raio, cx, cy + raio)
        tampa.add_color_stop_rgb(0, 0.22, 0.23, 0.26)
        tampa.add_color_stop_rgb(1, 0.10, 0.11, 0.12)
        cr.set_source(tampa)
        cr.fill()
        # logo: apagado = cinza; aceso = cor misturada com branco no centro, como LED real
        w, h = raio * 0.62, raio * 0.78
        self._cabeca(cr, cx, cy, w, h)
        if intensidade > 0:
            mistura = tuple(c + (1 - c) * 0.25 for c in cor)
            cr.set_source_rgba(*mistura, 0.25 + 0.75 * intensidade)
        else:
            cr.set_source_rgb(0.30, 0.32, 0.35)
        cr.fill()
        # olhos
        cr.set_source_rgb(0.08, 0.09, 0.10)
        for lado in (-1, 1):
            cr.save()
            cr.translate(cx + lado * w * 0.2, cy - h * 0.02)
            cr.rotate(lado * 0.55)
            cr.scale(w * 0.17, w * 0.08)
            cr.arc(0, 0, 1, 0, 2 * math.pi)
            cr.restore()
            cr.fill()


class AbaIluminacao:
    def __init__(self, extras):
        self.extras = extras
        self.cor1, self.cor2 = (0, 200, 215), (255, 0, 160)
        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        aviso = rotulo(AVISO_LUZ, "aviso", wrap=True)
        aviso.set_tooltip_text("O plano de captura com USBPcap está em docs/plano-captura-usbpcap.md.")
        caixa.append(aviso)

        # --- em cima: prévia da concha (sem 3D na página) + zona | roda de cores + hexadecimal ---
        linha = Gtk.Box(spacing=24)
        esquerda = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True)
        self.previa = None
        if extras.visualizador() is None:  # sem 3D: desenho próprio da concha
            self.previa = dica(PreviaLuz(), "Pré-visualização do logo da concha (desenho, não é o headset real).")
            esquerda.append(self.previa)
        zona = Gtk.Box(spacing=10)
        zona.append(dica(rotulo("ZONA: LOGO NAS CONCHAS", "secao", hexpand=True),
                         "O AW725H tem uma zona de luz RGB: o logo Alien Head nas conchas "
                         "(o LED de energia não é RGB)."))
        zona.append(rotulo("Luz acesa", "dim"))
        self.ligado = dica(Gtk.Switch(active=True, valign=Gtk.Align.CENTER),
                           "Pré-visualiza o logo aceso ou apagado (equivale ao \"Go Dark\" do AWCC).")
        self.ligado.connect("notify::active", lambda *_: self._atualizar_previa())
        zona.append(self.ligado)
        esquerda.append(zona)
        if self.previa is None:  # com o 3D: explica onde olhar
            esquerda.append(rotulo(
                "A prévia aparece no 3D, à esquerda, nas cabeças de alienígena das duas conchas (a mesma zona "
                "RGB nos dois lados). Clicar numa delas no 3D também abre esta aba.", "texto-ajuda", wrap=True))
        linha.append(esquerda)

        direita = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.roda = dica(RodaDeCores(170, ao_mudar=self._roda_mudou),
                         "Escolha a cor do logo: ângulo = matiz, distância do centro = saturação.")
        self.roda.definir_rgb(self.cor1)
        direita.append(self.roda)
        hexa = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        self.previa_cor = dica(PreviaCor(), "A cor escolhida.")
        self.previa_cor.definir(self.cor1)
        hexa.append(self.previa_cor)
        self.campo_hex = dica(Gtk.Entry(max_length=7, width_chars=9, css_classes=["mono"], text="#00C8D7"),
                              "Cor em hexadecimal (ex.: #00C8D7). Enter para usar.")
        self.campo_hex.connect("activate", self._hex_digitado)
        hexa.append(self.campo_hex)
        direita.append(hexa)
        linha.append(direita)
        caixa.append(linha)

        # --- embaixo, em grade: efeito e 2ª cor | brilho e velocidade ---
        grade = Gtk.Grid(column_spacing=24, row_spacing=6, column_homogeneous=True)
        grade.attach(rotulo("EFEITO", "secao"), 0, 0, 1, 1)
        grade.attach(rotulo("2ª COR (TRANSIÇÃO)", "secao"), 1, 0, 1, 1)
        self.efeito = dica(Gtk.DropDown.new_from_strings([e.capitalize() for e in EFEITOS]),
                           "Efeito da luz (pré-visualização dos efeitos AlienFX comuns).")
        self.efeito.connect("notify::selected", lambda *_: self._atualizar_previa())
        grade.attach(self.efeito, 0, 1, 1, 1)
        self.campo_hex2 = dica(Gtk.Entry(max_length=7, width_chars=9, css_classes=["mono"], text="#FF00A0",
                                         halign=Gtk.Align.START),
                               "Segunda cor do efeito transição (hexadecimal). Enter para usar.")
        self.campo_hex2.connect("activate", self._hex2_digitado)
        grade.attach(self.campo_hex2, 1, 1, 1, 1)
        self.rotulo_efeito = rotulo(EFEITOS_DESCRICAO["fixo"], "texto-ajuda", wrap=True)
        grade.attach(self.rotulo_efeito, 0, 2, 2, 1)
        for coluna, (titulo_, attr, valor, explicacao) in enumerate((
                ("BRILHO", "brilho", 100, "Brilho da pré-visualização, de 0 a 100%."),
                ("VELOCIDADE", "velocidade", 50, "Velocidade dos efeitos animados, de 0 a 100."))):
            grade.attach(rotulo(titulo_, "secao", margin_top=6), coluna, 3, 1, 1)
            escala = dica(Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1), explicacao)
            escala.set_value(valor)
            escala.set_draw_value(True)
            escala.connect("value-changed", lambda *_: self._atualizar_previa())
            setattr(self, attr, escala)
            grade.attach(escala, coluna, 4, 1, 1)
        caixa.append(grade)
        caixa.append(rotulo(
            "O AWCC muda a luz por comandos no canal de fabricante do dongle (report 6). Esses comandos não "
            "são públicos e mandar bytes no escuro pode alterar a configuração salva no headset, então o "
            "painel não envia nada. Depois de uma captura no Windows (USBPcap + AWCC), dá para implementar "
            "só os comandos vistos.", "texto-ajuda", wrap=True))
        self.widget = self.extras.pagina.rolavel(caixa)

    def _roda_mudou(self, r, g, b):
        self._usar_cor((r, g, b), mover_roda=False)

    def _hex_digitado(self, campo):
        rgb = hex_para_rgb(campo.get_text())
        if rgb:
            self._usar_cor(rgb)

    def _hex2_digitado(self, campo):
        rgb = hex_para_rgb(campo.get_text())
        if rgb:
            self.cor2 = rgb
            campo.set_text(rgb_para_hex(rgb))
            self._atualizar_previa()

    def _usar_cor(self, rgb, mover_roda=True):
        self.cor1 = rgb
        self.previa_cor.definir(rgb)
        self.campo_hex.set_text(rgb_para_hex(rgb))
        if mover_roda:
            self.roda.definir_rgb(rgb)
        self._atualizar_previa()

    def _atualizar_previa(self):
        efeito = EFEITOS[self.efeito.get_selected()]
        self.rotulo_efeito.set_text(EFEITOS_DESCRICAO[efeito])
        ligado = self.ligado.get_active()
        brilho = round(self.brilho.get_value())
        velocidade = round(self.velocidade.get_value())
        vis = self.extras.visualizador()
        if vis is not None:  # 3D do job aw3-3d: mesma API de pré-visualização
            vis.set_light("logo", rgb_para_hex(self.cor1) if ligado else "#000000")
            vis.set_effect(efeito, rgb_para_hex(self.cor1), rgb_para_hex(self.cor2), velocidade)
            vis.set_brightness(brilho if ligado else 0)
        if self.previa is not None:
            self.previa.definir(efeito=efeito, cor1=self.cor1, cor2=self.cor2, brilho=brilho,
                                velocidade=velocidade, ligado=ligado)

    def atualizar(self, periodico=False):
        if not periodico:
            self._atualizar_previa()


# =====================================================================
# BATERIA (e diagnóstico do canal HID)
# =====================================================================

class AbaBateria:
    def __init__(self, extras):
        self.extras = extras
        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        linha = Gtk.Box(spacing=22)
        self.anel = dica(AnelBateria(130),
                         "Bateria do headset em %. O AW725H tem UMA bateria interna que alimenta os dois lados, "
                         "então não existe valor por lado. O número vem do aviso que o dongle manda sozinho "
                         "quando o nível muda (c0 09, subtipo 02), lido sem enviar nada.")
        linha.append(self.anel)
        textos = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.CENTER, hexpand=True)
        textos.append(rotulo("BATERIA DO HEADSET (UMA SÓ, PARA OS DOIS LADOS)", "secao"))
        self.rotulo_bateria = rotulo("", "dim", wrap=True)
        textos.append(self.rotulo_bateria)
        linha.append(textos)
        caixa.append(linha)

        caixa.append(rotulo("CANAL HID DO DONGLE (SÓ LEITURA)", "secao"))
        self.caixa_hid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        caixa.append(dica(self.caixa_hid, "Estado do leitor passivo: o hidraw é aberto só para leitura, "
                                          "sem enviar nada ao dongle."))
        caixa.append(rotulo("PELO MANUAL", "secao", margin_top=6))
        caixa.append(grade_info([
            ("Bateria", "750 mAh, carga completa em menos de 2,5 h"),
            ("Duração", "até 58 h no 2.4 GHz com a luz desligada, 35 h com a luz ligada"),
            ("Bateria fraca", "abaixo de 20%: LED de energia pisca âmbar e o logo pisca rápido"),
            ("Desligamento", "sozinho 30 min depois de perder o dongle (fixo, sem ajuste no AWCC)"),
        ]))
        self.widget = self.extras.pagina.rolavel(caixa)

    def atualizar(self, periodico=False):
        e = self.extras.leitor.estado
        self.anel.definir(e["bateria"], bool(e["carregando"]))
        if e["bateria"] is not None:
            situacao = {True: "subindo (carregando)", False: "descendo (em uso)"}.get(e["carregando"], "")
            self.rotulo_bateria.set_text(
                f"{e['bateria']}%{', ' + situacao if situacao else ''}; último aviso em {e['hora_bateria']}. "
                "O dongle manda o nível sozinho quando ele muda (aviso c0 09, subtipo 02): a cada ~70 s em "
                "uso e a cada ~18 s carregando. É uma estimativa do headset e anda rápido perto do fim.")
        elif e["permissao"] is False:
            self.rotulo_bateria.set_text("Sem permissão para ler o dongle: instale a regra udev "
                                         "70-alienware-toolkit.rules (Configurações).")
        else:
            self.rotulo_bateria.set_text(
                "Não informado pelo dongle ainda: ele confere o nível a cada ~70 s e só manda o aviso "
                "(c0 09, subtipo 02) quando o valor muda. Pedir na hora exigiria o comando do AWCC "
                "(requer captura no Windows).")
        while (filho := self.caixa_hid.get_first_child()):
            self.caixa_hid.remove(filho)
        contagem = ", ".join(f"r{k}: {v}" for k, v in sorted(e["contagem"].items())) or "nenhum"
        ultimo = e["ultimo"]
        pares = [
            ("Dispositivo", e["caminho"] or "não encontrado"),
            ("Leitura", "ativa" if e["lendo"] else (e["erro"] or "parada")),
            ("Reports recebidos", f"{e['eventos']} ({contagem})"),
            ("Último report 8", " ".join(ultimo[8]) if 8 in ultimo else "—"),
            ("Último report 7", (ultimo[7][0] + " " + ultimo[7][1][:47] + " …") if 7 in ultimo else "—"),
            ("Aviso subtipo 01", f"0x{e['estado_01']:02x} (dois estados, a decifrar)"
             if e["estado_01"] is not None else "—"),
            ("Último botão", " ".join(e["ultimo_botao"]) if e["ultimo_botao"] else "—"),
        ]
        self.caixa_hid.append(grade_info(pares))

    def ao_evento(self, _ev):
        if self.extras.pagina.abas.atual() == "bateria":
            self.atualizar()
