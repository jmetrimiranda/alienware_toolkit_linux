// Alienware Toolkit hover: anima o ícone do Alienware Toolkit na Ubuntu Dock e no dash do overview.
//
// Ao passar o mouse: troca o gicon do St.Icon pelos quadros de frames/<tamanho>/ (olhos acendem,
// LED do microfone pisca, balanço) e dá um pulinho com actor.ease. Ao sair, volta ao ícone normal.
// Os ícones são procurados de novo a cada poucos segundos e quando os favoritos mudam, porque a dock
// recria os ícones (troca de monitor, de configuração ou de favoritos).
// Regra da casa: todo callback fica dentro de try/catch; um erro aqui nunca pode derrubar o shell.

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';

import * as AppFavorites from 'resource:///org/gnome/shell/ui/appFavorites.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const APP_ID = 'io.github.jmetrimiranda.AlienwareToolkit.desktop';
const TAG = '[alienware-toolkit-hover]';
const TOTAL_QUADROS = 16;   // frame-00 .. frame-15
const INICIO_LACO = 8;      // 0-7 = entrada (acende e pula); 8-15 = laço enquanto o mouse fica em cima
const MS_ENTRADA = 70;
const MS_LACO = 90;
const SEGUNDOS_BUSCA = 3;   // checagem periódica (a dock pode ser recriada sem aviso)
const PULO_PX = 4;

export default class AlienwareToolkitHover extends Extension {
    enable() {
        this._icones = new Map();   // appIcon -> {hover, destroy, onde}
        this._anim = null;          // animação em curso (um ícone por vez)
        this._idleId = 0;
        this._quadros = {};
        for (const t of [128, 256]) {
            this._quadros[t] = [];
            for (let i = 0; i < TOTAL_QUADROS; i++) {
                const nome = `frame-${String(i).padStart(2, '0')}.png`;
                const arq = Gio.File.new_for_path(GLib.build_filenamev([this.path, 'frames', `${t}`, nome]));
                this._quadros[t].push(new Gio.FileIcon({file: arq}));
            }
        }

        // checagem periódica + sinais que costumam recriar os ícones
        this._buscaId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, SEGUNDOS_BUSCA, () => {
            this._buscar();
            return GLib.SOURCE_CONTINUE;
        });
        this._favId = AppFavorites.getAppFavorites().connect('changed', () => this._buscarLogo());
        this._overviewId = Main.overview.connect('showing', () => this._buscarLogo());
        this._extId = Main.extensionManager.connect('extension-state-changed', () => this._buscarLogo());
        this._buscarLogo();
        console.log(`${TAG} ligada`);
    }

    disable() {
        for (const id of [this._buscaId, this._idleId]) {
            if (id)
                GLib.source_remove(id);
        }
        this._buscaId = this._idleId = 0;
        AppFavorites.getAppFavorites().disconnect(this._favId);
        Main.overview.disconnect(this._overviewId);
        Main.extensionManager.disconnect(this._extId);
        this._parar();
        for (const appIcon of [...this._icones.keys()])
            this._esquecer(appIcon, false);
        this._icones = null;
        this._quadros = null;
        console.log(`${TAG} desligada`);
    }

    // Busca logo que o shell ficar ocioso (junta vários sinais seguidos numa busca só).
    _buscarLogo() {
        try {
            if (this._idleId)
                return;
            this._idleId = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                this._idleId = 0;
                this._buscar();
                return GLib.SOURCE_REMOVE;
            });
        } catch (e) {
            this._erro('buscarLogo', e);
        }
    }

    // Dashes conhecidos: o de cada Ubuntu Dock (filhos diretos do uiGroup com .dash) e o do overview.
    // Com a Ubuntu Dock ligada, Main.overview.dash costuma ser o próprio dash da dock: não repete.
    _dashes() {
        const lista = [];
        for (const filho of Main.layoutManager.uiGroup.get_children()) {
            if (filho.dash?._box)
                lista.push([filho.dash, `dock (monitor ${filho.monitorIndex ?? 0})`]);
        }
        const ov = Main.overview.dash;
        if (ov?._box && !lista.some(([d]) => d === ov))
            lista.push([ov, 'overview']);
        return lista;
    }

    _buscar() {
        try {
            for (const [dash, onde] of this._dashes()) {
                for (const item of dash._box.get_children()) {
                    const appIcon = item.child;
                    if (!appIcon?.app || this._icones.has(appIcon))
                        continue;
                    if (appIcon.app.get_id() === APP_ID)
                        this._acompanhar(appIcon, onde);
                }
            }
        } catch (e) {
            this._erro('buscar', e);
        }
    }

    _acompanhar(appIcon, onde) {
        const ids = {onde};
        ids.hover = appIcon.connect('notify::hover', () => {
            try {
                if (appIcon.hover)
                    this._iniciar(appIcon);
                else if (this._anim?.appIcon === appIcon)
                    this._parar();
            } catch (e) {
                this._erro('hover', e);
            }
        });
        // o ícone foi destruído (a dock o recriou): só esquece, a próxima busca acha o novo
        ids.destroy = appIcon.connect('destroy', () => {
            try {
                this._esquecer(appIcon, true);
            } catch (e) {
                this._erro('destroy', e);
            }
        });
        this._icones.set(appIcon, ids);
        console.log(`${TAG} ícone encontrado: ${onde}`);
    }

    _esquecer(appIcon, destruido) {
        const ids = this._icones?.get(appIcon);
        if (!ids)
            return;
        this._icones.delete(appIcon);
        if (this._anim?.appIcon === appIcon)
            this._parar();
        if (!destruido) {
            appIcon.disconnect(ids.hover);
            appIcon.disconnect(ids.destroy);
        }
    }

    // St.Icon dentro do AppIcon (BaseIcon.icon). Ele é recriado quando o tamanho ou o tema mudam.
    _stIcon(appIcon) {
        const icone = appIcon.icon?.icon;
        return icone instanceof St.Icon ? icone : null;
    }

    _iniciar(appIcon) {
        this._parar();
        const stIcon = this._stIcon(appIcon);
        if (!stIcon)
            return;
        const escala = St.ThemeContext.get_for_stage(global.stage).scale_factor;
        const tamanho = stIcon.icon_size * escala > 128 ? 256 : 128;
        const anim = {appIcon, stIcon, original: stIcon.gicon, quadros: this._quadros[tamanho], quadro: 0, timerId: 0};
        anim.destroyId = stIcon.connect('destroy', () => {
            try {
                anim.stIcon = null;
                if (this._anim === anim)
                    this._parar();
            } catch (e) {
                this._erro('destroy do St.Icon', e);
            }
        });
        this._anim = anim;
        stIcon.gicon = anim.quadros[0];
        anim.timerId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, MS_ENTRADA, () => this._passo(anim));

        // pulinho do ícone inteiro: sobe rápido e volta quicando
        stIcon.remove_transition('translation-y');
        stIcon.ease({
            translation_y: -PULO_PX * escala,
            duration: 140,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            onStopped: terminou => {
                try {
                    if (terminou && this._anim === anim && anim.stIcon) {
                        anim.stIcon.ease({
                            translation_y: 0,
                            duration: 380,
                            mode: Clutter.AnimationMode.EASE_OUT_BOUNCE,
                        });
                    }
                } catch (e) {
                    this._erro('pulo', e);
                }
            },
        });
        console.log(`${TAG} hover: animação iniciada (${tamanho} px, ${this._icones.get(appIcon)?.onde})`);
    }

    // Um quadro. Na entrada (0-7) roda mais rápido; depois fica no laço 8-15 até o mouse sair.
    _passo(anim) {
        try {
            if (this._anim !== anim || !anim.stIcon) {
                anim.timerId = 0;
                return GLib.SOURCE_REMOVE;
            }
            anim.quadro = anim.quadro + 1 >= TOTAL_QUADROS ? INICIO_LACO : anim.quadro + 1;
            anim.stIcon.gicon = anim.quadros[anim.quadro];
            if (anim.quadro === INICIO_LACO && !anim.noLaco) {
                anim.noLaco = true;
                anim.timerId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, MS_LACO, () => this._passo(anim));
                return GLib.SOURCE_REMOVE;
            }
            return GLib.SOURCE_CONTINUE;
        } catch (e) {
            this._erro('quadro', e);
            anim.timerId = 0;
            this._parar();
            return GLib.SOURCE_REMOVE;
        }
    }

    // Para a animação e devolve o ícone normal.
    _parar() {
        const anim = this._anim;
        if (!anim)
            return;
        this._anim = null;
        try {
            if (anim.timerId)
                GLib.source_remove(anim.timerId);
            anim.timerId = 0;
            if (anim.stIcon) {
                anim.stIcon.disconnect(anim.destroyId);
                anim.stIcon.gicon = anim.original;
                anim.stIcon.remove_transition('translation-y');
                anim.stIcon.translation_y = 0;
            }
        } catch (e) {
            this._erro('parar', e);
        }
    }

    _erro(onde, e) {
        console.error(`${TAG} erro em ${onde}: ${e?.message ?? e}`);
    }
}
