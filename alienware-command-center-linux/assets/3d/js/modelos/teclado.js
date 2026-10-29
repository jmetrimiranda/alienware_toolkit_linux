// Teclado gamer genérico (modelo procedural) com layout configurável e RGB por tecla.
// Layouts ANSI: '104' (completo), '87' (TKL), '75' (75%, 84 teclas) e '60' (60%, 61 teclas).
// Unidade: centímetro; 1u = 1,905 cm (passo padrão das teclas). Frente em +z.
// Cada tecla é uma unidade de luz: a legenda acende na cor da tecla e um brilho vaza por baixo.
// Zonas: 'todas', 'zona1'..'zona4' (quatro faixas da esquerda para a direita), 'fileira1'..'fileira6'
// (de cima para baixo; o Redragon K617 Rainbow tem uma cor fixa por fileira) e 'tecla:<id>'.
import * as THREE from 'three';
import { plastico, luminancia } from '../comum.js';

const U = 1.905;
const FOLGA = 0.2;          // espaço entre teclas
const BORDA = 1.0;          // borda do gabinete em volta das teclas

// Gramática de cada linha: "id[=rótulo][:largura[:altura]]" separados por espaço; "_n" = vão de n unidades.
const FILEIRA_F = 'Esc _1 F1 F2 F3 F4 _0.5 F5 F6 F7 F8 _0.5 F9 F10 F11 F12';
const NAV_F = '_0.25 PrtSc=Prt ScrLk=Scr Pause=Pau';
const LINHAS = {
  1: 'Grave=` 1 2 3 4 5 6 7 8 9 0 Minus=- Equal== Backspace:2',
  2: 'Tab:1.5 Q W E R T Y U I O P LBr=[ RBr=] Backslash=\\:1.5',
  3: 'Caps:1.75 A S D F G H J K L Semi=; Quote=\' Enter:2.25',
  4: 'ShiftL=Shift:2.25 Z X C V B N M Comma=, Dot=. Slash=/ ShiftR=Shift:2.75',
  5: 'CtrlL=Ctrl:1.25 WinL=Win:1.25 AltL=Alt:1.25 Space=:6.25 AltR=Alt:1.25 WinR=Win:1.25 Menu:1.25 CtrlR=Ctrl:1.25',
};
const NAV = {
  1: '_0.25 Ins Home PgUp', 2: '_0.25 Del End PgDn', 3: '', 4: '_1.25 Up=↑', 5: '_0.25 Left=← Down=↓ Right=→',
};
const NUM = {
  0: '', 1: '_0.25 NumLock=Num NSlash=/ NStar=* NMinus=-', 2: '_0.25 N7=7 N8=8 N9=9 NPlus=+:1:2',
  3: '_3.5 N4=4 N5=5 N6=6', 4: '_1.25 N1=1 N2=2 N3=3 NEnter=Ent:1:2', 5: '_0.25 N0=0:2 NDot=.',
};

export const LAYOUTS = {
  104: { nome: 'Completo (104)', linhas: [FILEIRA_F + ' ' + NAV_F + ' _4.25',
    ...[1, 2, 3, 4, 5].map((i) => [LINHAS[i], NAV[i], NUM[i]].join(' '))], vaoF: 0.5 },
  87: { nome: 'TKL (87)', linhas: [FILEIRA_F + ' ' + NAV_F, ...[1, 2, 3, 4, 5].map((i) => LINHAS[i] + ' ' + NAV[i])], vaoF: 0.5 },
  75: { nome: '75% (84)', vaoF: 0.1, linhas: [
    'Esc F1 F2 F3 F4 F5 F6 F7 F8 F9 F10 F11 F12 PrtSc=Prt Ins Del',
    LINHAS[1] + ' Home', LINHAS[2] + ' PgUp', LINHAS[3] + ' PgDn',
    'ShiftL=Shift:2.25 Z X C V B N M Comma=, Dot=. Slash=/ ShiftR=Shift:1.75 Up=↑ End',
    'CtrlL=Ctrl:1.25 WinL=Win:1.25 AltL=Alt:1.25 Space=:6.25 AltR=Alt Fn CtrlR=Ctrl Left=← Down=↓ Right=→'] },
  60: { nome: '60% (61)', vaoF: 0, linhas: [
    'Esc 1 2 3 4 5 6 7 8 9 0 Minus=- Equal== Backspace:2', LINHAS[2], LINHAS[3], LINHAS[4],
    'CtrlL=Ctrl:1.25 WinL=Win:1.25 AltL=Alt:1.25 Space=:6.25 AltR=Alt:1.25 Fn:1.25 Menu:1.25 CtrlR=Ctrl:1.25'] },
};

// nomes alternativos aceitos por definirLayout()
const APELIDOS = { full: 104, completo: 104, '100': 104, tkl: 87, '80': 87, '75%': 75, '60%': 60, '84': 75, '61': 60,
  k617: 60 };  // Redragon K617 Fizz: 60%, 61 teclas, ANSI

export function normalizarLayout(nome) {
  const n = String(nome).toLowerCase().replace('%', '').trim();
  const v = APELIDOS[n] || APELIDOS[n + '%'] || +n;
  return LAYOUTS[v] ? v : 104;
}

/** Lê o layout e devolve a lista de teclas com posição em unidades. */
export function teclasDoLayout(nome) {
  const lay = LAYOUTS[normalizarLayout(nome)];
  const teclas = [];
  const vistos = new Set();
  let y = 0;
  lay.linhas.forEach((linha, i) => {
    let x = 0;
    for (const tok of linha.split(/\s+/).filter(Boolean)) {
      if (tok.startsWith('_')) { x += parseFloat(tok.slice(1)); continue; }
      const [, cabeca, w = '1', h = '1'] = tok.match(/^(.*?)(?::([\d.]+))?(?::([\d.]+))?$/);
      const igual = cabeca.indexOf('=');
      let id = igual > 0 ? cabeca.slice(0, igual) : cabeca;
      const rotulo = igual > 0 ? cabeca.slice(igual + 1) : cabeca;
      while (vistos.has(id)) id += '_';
      vistos.add(id);
      teclas.push({ id, rotulo, x, y, w: +w, h: +h });
      x += +w;
    }
    y += 1 + (i === 0 ? lay.vaoF : 0);
  });
  return teclas;
}

// ---------- texturas das legendas (um atlas com todos os rótulos) ----------
const CELULA = 128;
function atlasLegendas(rotulos) {
  const colunas = 16;
  const linhas = Math.ceil(rotulos.length / colunas);
  const c = document.createElement('canvas');
  c.width = colunas * CELULA;
  c.height = THREE.MathUtils.ceilPowerOfTwo(Math.max(1, linhas) * CELULA);
  const g = c.getContext('2d');
  g.fillStyle = '#fff';
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  const indice = {};
  rotulos.forEach((r, i) => {
    const cx = (i % colunas) * CELULA + CELULA / 2, cy = Math.floor(i / colunas) * CELULA + CELULA / 2;
    let tam = r.length === 1 ? 58 : r.length <= 3 ? 40 : 30;
    g.font = `600 ${tam}px "Inter", "Cantarell", "DejaVu Sans", sans-serif`;
    while (g.measureText(r).width > CELULA * 0.86 && tam > 12) {
      tam -= 2;
      g.font = `600 ${tam}px "Inter", "Cantarell", "DejaVu Sans", sans-serif`;
    }
    g.fillText(r, cx, cy);
    indice[r] = i;
  });
  const t = new THREE.CanvasTexture(c);
  t.anisotropy = 8;
  return { textura: t, indice, colunas, linhas: c.height / CELULA };
}

/** Brilho que vaza por baixo das teclas (mancha radial). */
function texturaVazamento() {
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const g = c.getContext('2d');
  const gr = g.createRadialGradient(32, 32, 4, 32, 32, 32);
  gr.addColorStop(0, 'rgba(255,255,255,1)');
  gr.addColorStop(0.6, 'rgba(255,255,255,0.45)');
  gr.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = gr;
  g.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
}

// ---------- geometrias ----------
function retangulo(w, h, r) {
  const f = new THREE.Shape();
  const x = -w / 2, y = -h / 2;
  f.moveTo(x + r, y);
  f.lineTo(x + w - r, y); f.quadraticCurveTo(x + w, y, x + w, y + r);
  f.lineTo(x + w, y + h - r); f.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  f.lineTo(x + r, y + h); f.quadraticCurveTo(x, y + h, x, y + h - r);
  f.lineTo(x, y + r); f.quadraticCurveTo(x, y, x + r, y);
  return f;
}

const cacheTecla = new Map();
/** Tecla com topo afunilado (perfil "cherry" simplificado). */
function geometriaTecla(w, h) {
  const chave = `${w}x${h}`;
  if (cacheTecla.has(chave)) return cacheTecla.get(chave);
  const largura = w * U - FOLGA, fundo = h * U - FOLGA;
  const g = new THREE.ExtrudeGeometry(retangulo(largura, fundo, 0.16), {
    depth: 0.72, bevelEnabled: true, bevelThickness: 0.08, bevelSize: 0.08, bevelSegments: 2, curveSegments: 4 });
  g.rotateX(-Math.PI / 2);   // extrusão para cima (+y)
  g.computeBoundingBox();
  const { min, max } = g.boundingBox;
  const p = g.attributes.position;
  for (let i = 0; i < p.count; i++) {
    // o topo recua 0,18 cm de cada lado (mesmo recuo em teclas largas)
    const t = (p.getY(i) - min.y) / (max.y - min.y);
    p.setX(i, p.getX(i) * (1 - t * 0.36 / largura));
    p.setZ(i, p.getZ(i) * (1 - t * 0.36 / fundo));
    p.setY(i, p.getY(i) - min.y);
  }
  g.computeVertexNormals();
  cacheTecla.set(chave, g);
  return g;
}

// ---------- montagem ----------
export function criar({ layout = '104' } = {}) {
  const grupo = new THREE.Group();
  grupo.name = 'Teclado';
  const matGabinete = plastico('#202226', 0.45);
  const matPlaca = new THREE.MeshStandardMaterial({ color: '#2a2d32', roughness: 0.55, metalness: 0.35, envMapIntensity: 0.5 });
  const matTecla = plastico('#1b1c1f', 0.6);
  const vazamento = texturaVazamento();
  const corApagada = new THREE.Color('#5d636b').multiplyScalar(0.25);
  let conteudo = null;
  const modelo = { grupo, unidades: [], zonas: [] };

  function montar(nomeLayout) {
    if (conteudo) {
      grupo.remove(conteudo);
      conteudo.traverse((o) => {
        if (o.isMesh && o.material !== matTecla) o.material.dispose?.();
        if (o.isMesh && o.userData.geometriaPropria) o.geometry.dispose();
      });
      modelo.atlas?.textura.dispose();
    }
    conteudo = new THREE.Group();
    const teclas = teclasDoLayout(nomeLayout);
    const larguraU = Math.max(...teclas.map((t) => t.x + t.w));
    const alturaU = Math.max(...teclas.map((t) => t.y + t.h));
    const larg = larguraU * U + BORDA * 2, prof = alturaU * U + BORDA * 2 + 0.4;

    // gabinete: bloco arredondado; placa metálica rebaixada por cima
    const gab = new THREE.Mesh(new THREE.ExtrudeGeometry(retangulo(larg, prof, 0.9),
      { depth: 1.6, bevelEnabled: true, bevelThickness: 0.35, bevelSize: 0.35, bevelSegments: 4, curveSegments: 8 }), matGabinete);
    gab.rotation.x = -Math.PI / 2;
    gab.position.y = 0.35;
    gab.userData.geometriaPropria = true;
    conteudo.add(gab);
    const placa = new THREE.Mesh(new THREE.ExtrudeGeometry(retangulo(larg - BORDA * 1.2, prof - BORDA * 1.2, 0.5),
      { depth: 0.05, bevelEnabled: false }), matPlaca);
    placa.rotation.x = -Math.PI / 2;
    placa.position.y = 2.32;
    placa.userData.geometriaPropria = true;
    conteudo.add(placa);

    // legendas
    const rotulos = [...new Set(teclas.map((t) => t.rotulo).filter(Boolean))];
    const atlas = atlasLegendas(rotulos);
    modelo.atlas = atlas;
    const x0 = -larguraU * U / 2, z0 = -alturaU * U / 2 + 0.2;
    const unidades = [];
    const ladoLegenda = 0.62 * U;

    for (const t of teclas) {
      const cx = x0 + (t.x + t.w / 2) * U, cz = z0 + (t.y + t.h / 2) * U;
      const tecla = new THREE.Mesh(geometriaTecla(t.w, t.h), matTecla);
      tecla.position.set(cx, 2.42, cz);
      tecla.userData = { zona: `tecla:${t.id}`, dica: `Tecla ${t.rotulo || 'Espaço'}` };
      conteudo.add(tecla);

      // legenda: quadrado com a célula do atlas, logo acima do topo da tecla
      let matLegenda = null;
      if (t.rotulo) {
        const geo = new THREE.PlaneGeometry(ladoLegenda, ladoLegenda);
        geo.rotateX(-Math.PI / 2);
        const i = atlas.indice[t.rotulo];
        const u0 = (i % atlas.colunas) / atlas.colunas, v1 = 1 - Math.floor(i / atlas.colunas) / atlas.linhas;
        const uv = geo.attributes.uv;
        for (let k = 0; k < uv.count; k++) {
          uv.setXY(k, u0 + uv.getX(k) / atlas.colunas, v1 - (1 - uv.getY(k)) / atlas.linhas);
        }
        matLegenda = new THREE.MeshBasicMaterial({ map: atlas.textura, transparent: true, depthWrite: false,
                                                   color: corApagada.clone() });
        const legenda = new THREE.Mesh(geo, matLegenda);
        legenda.position.set(0, 0.886, 0);
        legenda.userData = { semSombra: true, geometriaPropria: true, atravessar: true };
        tecla.add(legenda);
      }
      // vazamento de luz na placa, em volta da tecla
      const matVaz = new THREE.MeshBasicMaterial({ map: vazamento, transparent: true, depthWrite: false,
                                                   blending: THREE.AdditiveBlending, color: 0x000000 });
      const vaz = new THREE.Mesh(new THREE.PlaneGeometry(t.w * U + 1.1, t.h * U + 1.1), matVaz);
      vaz.rotation.x = -Math.PI / 2;
      vaz.position.set(cx, 2.38, cz);
      vaz.userData = { semSombra: true, geometriaPropria: true, atravessar: true };
      conteudo.add(vaz);

      const nx = (t.x + t.w / 2) / larguraU, ny = (t.y + t.h / 2) / alturaU;
      const zona = `zona${Math.min(4, 1 + Math.floor(nx * 4))}`;
      const fileira = `fileira${1 + Math.floor(t.y + 0.01)}`;
      unidades.push({
        id: `tecla:${t.id}`, zonas: ['todas', zona, fileira, `tecla:${t.id}`], x: nx, y: ny,
        cor: new THREE.Color('#00c8d7'),
        aplicar(cor, k) {
          if (matLegenda) matLegenda.color.copy(cor).multiplyScalar(k * 0.9).add(corApagada);
          matVaz.color.copy(cor).multiplyScalar(k * 0.4);
        },
      });
    }
    // leve inclinação de digitação (traseira mais alta)
    conteudo.rotation.x = 0.05;
    grupo.add(conteudo);
    modelo.unidades = unidades;
    modelo.zonas = ['todas', 'zona1', 'zona2', 'zona3', 'zona4', ...[1, 2, 3, 4, 5, 6].map((i) => `fileira${i}`),
                    ...teclas.map((t) => `tecla:${t.id}`)];
    modelo.layout = normalizarLayout(nomeLayout);
  }

  montar(layout);
  return Object.assign(modelo, {
    vista: { giro: -0.35, inclinacao: 0.62, zoom: 0.86, sombra: 0.6 },
    definirLayout(nome) { montar(nome); },
    definirCorCorpo(hex) {
      const claro = luminancia(hex) > 0.35;
      matGabinete.color.set(hex);
      matPlaca.color.set(hex).lerp(new THREE.Color(claro ? '#b8bcc2' : '#3a3e44'), 0.5);
      matTecla.color.set(claro ? '#e4e6e9' : '#1b1c1f');
      corApagada.set(claro ? '#4a4f57' : '#5d636b').multiplyScalar(0.25);
    },
    descartar() {
      grupo.traverse((o) => { if (o.isMesh) { o.material.dispose?.(); if (o.userData.geometriaPropria) o.geometry.dispose(); } });
      modelo.atlas?.textura.dispose();
      vazamento.dispose();
    },
  });
}
