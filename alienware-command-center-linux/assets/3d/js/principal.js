// Cena principal do visualizador 3D e API window.aw3d (chamada pelo Python via evaluate_javascript).
//
// API (todas as funções devolvem true/false ou um valor simples, para o Python poder ler):
//   aw3d.definirModelo('mouse'|'headset'|'teclado')
//   aw3d.definirCorCorpo('#rrggbb')
//   aw3d.definirLuz(zona, '#rrggbb')        zona: 'todas', 'logo', 'logo_esq', 'zona1'..'zona4', 'tecla:Q'...
//   aw3d.definirEfeito(nome, cor1, cor2, velocidade)   nome: fixo, respirar, transicao, espectro,
//                                                      pulsar, arco-iris, onda
//   aw3d.definirBrilho(0..100)
//   aw3d.definirLayout('104'|'87'|'75'|'60')   (só teclado)
//   aw3d.girarSozinho(true|false)
//   aw3d.resetarVista()
//   aw3d.quadro(anguloGraus, largura, altura, tempo) -> 'data:image/png;base64,...'
//   aw3d.estado() -> texto JSON com o estado atual
// Mensagens para o Python (window.webkit.messageHandlers.aw3d): {tipo:'pronto'}, {tipo:'clique', zona},
// {tipo:'erro', mensagem}.
import * as THREE from 'three';
import { Bloom } from './bloom.js';
import { Controles } from './controles.js';
import { Efeitos, normalizarEfeito } from './efeitos.js';
import { sombraContato } from './comum.js';
import * as mouse from './modelos/mouse.js';
import * as headset from './modelos/headset.js';
import * as teclado from './modelos/teclado.js';

const FABRICAS = { mouse, headset, teclado };
const CORES_CORPO = { mouse: '#202226', headset: '#202226', teclado: '#202226' };

// ---------- ponte com o Python ----------
function avisarPython(msg) {
  const h = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.aw3d;
  if (h) h.postMessage(JSON.stringify(msg));
}

// ---------- renderer ----------
const canvas = document.createElement('canvas');
document.body.appendChild(canvas);
let renderer;
try {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: 'high-performance' });
} catch (erro) {
  const aviso = document.getElementById('aviso');
  aviso.textContent = 'WebGL indisponível neste sistema.';
  aviso.style.display = 'flex';
  avisarPython({ tipo: 'erro', mensagem: 'WebGL indisponível: ' + erro.message });
  throw erro;
}
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFShadowMap;

const cena = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(24, 1, 0.5, 600);
const bloom = new Bloom(renderer);

// ---------- ambiente de estúdio (reflexos do PBR), gerado aqui mesmo ----------
function ambienteEstudio() {
  const estudio = new THREE.Scene();
  const sala = new THREE.Mesh(new THREE.BoxGeometry(100, 60, 100),
    new THREE.MeshBasicMaterial({ color: 0x15171a, side: THREE.BackSide }));
  estudio.add(sala);
  const painel = (w, h, cor, forca, pos, alvo) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h),
      new THREE.MeshBasicMaterial({ color: new THREE.Color(cor).multiplyScalar(forca), side: THREE.DoubleSide }));
    m.position.set(...pos);
    m.lookAt(...alvo);
    estudio.add(m);
  };
  painel(40, 22, '#ffffff', 3.2, [-20, 26, 18], [0, 0, 0]);   // softbox principal (cima/esquerda)
  painel(14, 40, '#dfe8f0', 2.0, [45, 8, 10], [0, 0, 0]);     // rebatedor à direita
  painel(60, 4, '#00c8d7', 1.0, [0, 6, -48], [0, 0, 0]);      // faixa ciano atrás
  painel(80, 30, '#2a2e34', 1.0, [0, -28, 0], [0, 0, 0]);     // chão
  const pmrem = new THREE.PMREMGenerator(renderer);
  const env = pmrem.fromScene(estudio, 0.02).texture;
  pmrem.dispose();
  return env;
}
cena.environment = ambienteEstudio();
cena.environmentIntensity = 0.55;

// ---------- luzes ----------
cena.add(new THREE.HemisphereLight(0xdfe6ee, 0x1b1d21, 0.55));
const principal = new THREE.DirectionalLight(0xfff4ea, 2.4);
principal.position.set(-18, 34, 22);
principal.castShadow = true;
principal.shadow.mapSize.set(2048, 2048);
principal.shadow.radius = 5;
principal.shadow.bias = -0.0004;
principal.shadow.normalBias = 0.02;
Object.assign(principal.shadow.camera, { left: -32, right: 32, top: 32, bottom: -32, near: 1, far: 120 });
cena.add(principal);
const preenchimento = new THREE.DirectionalLight(0xcfe0ff, 0.85);
preenchimento.position.set(30, 12, 18);
cena.add(preenchimento);
const recorte = new THREE.DirectionalLight(0x00c8d7, 1.2);   // luz de recorte ciano, por trás e rasante
recorte.position.set(10, 7, -36);
cena.add(recorte);

// ---------- chão (só recebe sombra; o fundo é pintado na composição) ----------
const chao = new THREE.Mesh(new THREE.PlaneGeometry(400, 400), new THREE.ShadowMaterial({ opacity: 0.38 }));
chao.rotation.x = -Math.PI / 2;
chao.receiveShadow = true;
cena.add(chao);

// plataforma giratória: aparelho + sombra de contato
const plataforma = new THREE.Group();
cena.add(plataforma);
const controles = new Controles(canvas, camera, plataforma);
const efeitos = new Efeitos();

// ---------- estado ----------
const estado = {
  modelo: null, // nome
  atual: null,  // objeto devolvido por criar()
  sombra: null,
  corCorpo: { ...CORES_CORPO },
  coresZona: {},       // por modelo: { zona: hex }
  layout: '104',
  cor1: '#00c8d7',
  capturando: false,
};

function enquadrar() {
  const caixa = new THREE.Box3().setFromObject(estado.atual.grupo);
  const esfera = caixa.getBoundingSphere(new THREE.Sphere());
  const tam = caixa.getSize(new THREE.Vector3());
  const v = estado.atual.vista || {};
  controles.enquadrar(tam, tam.y * 0.42, v.giro ?? -0.6, v.inclinacao ?? 0.38, v.zoom ?? 1);
  // sombra de contato do tamanho da base do aparelho
  if (estado.sombra) plataforma.remove(estado.sombra);
  estado.sombra = sombraContato(tam.x * 1.25, tam.z * 1.25, v.sombra ?? 0.7);
  plataforma.add(estado.sombra);
  principal.shadow.camera.left = principal.shadow.camera.bottom = -esfera.radius * 1.6;
  principal.shadow.camera.right = principal.shadow.camera.top = esfera.radius * 1.6;
  principal.shadow.camera.updateProjectionMatrix();
}

function aplicarCoresZona() {
  const cores = estado.coresZona[estado.modelo] || {};
  for (const u of estado.atual.unidades) {
    u.cor.set(estado.cor1);
    for (const [zona, hex] of Object.entries(cores)) {
      if (zona === 'todas' || u.zonas.includes(zona) || u.id === zona) u.cor.set(hex);
    }
  }
}

// ---------- API ----------
const api = {
  definirModelo(nome) {
    if (!FABRICAS[nome]) return false;
    if (estado.atual) {
      plataforma.remove(estado.atual.grupo);
      estado.atual.descartar?.();
    }
    estado.modelo = nome;
    estado.atual = FABRICAS[nome].criar({ layout: estado.layout });
    estado.atual.grupo.traverse((o) => { if (o.isMesh && !o.userData.semSombra) o.castShadow = true; });
    plataforma.add(estado.atual.grupo);
    estado.atual.definirCorCorpo(estado.corCorpo[nome]);
    aplicarCoresZona();
    enquadrar();
    return true;
  },
  definirCorCorpo(hex) {
    estado.corCorpo[estado.modelo] = hex;
    estado.atual.definirCorCorpo(hex);
    return true;
  },
  definirLuz(zona, hex) {
    zona = zona || 'todas';
    const cores = (estado.coresZona[estado.modelo] ||= {});
    if (zona === 'todas') {
      estado.coresZona[estado.modelo] = {};
      estado.cor1 = hex;
    } else {
      cores[zona] = hex;
    }
    aplicarCoresZona();
    return true;
  },
  definirEfeito(nome, cor1, cor2, velocidade) {
    efeitos.definir(nome, cor2, velocidade);
    if (cor1) {
      estado.cor1 = cor1;
      estado.coresZona[estado.modelo] = {};
      aplicarCoresZona();
    }
    return efeitos.nome;
  },
  definirBrilho(valor) {
    efeitos.brilho = THREE.MathUtils.clamp(+valor, 0, 100);
    return true;
  },
  definirLayout(nome) {
    estado.layout = String(nome);
    if (estado.modelo === 'teclado') {
      estado.atual.definirLayout(estado.layout);
      estado.atual.grupo.traverse((o) => { if (o.isMesh && !o.userData.semSombra) o.castShadow = true; });
      aplicarCoresZona();
      enquadrar();
    }
    return true;
  },
  girarSozinho(sim) {
    controles.girarSozinho = !!sim;
    return true;
  },
  resetarVista() {
    controles.resetar();
    return true;
  },
  zonas() {
    return JSON.stringify(estado.atual.zonas);
  },
  /** Teste: "clica" no centro da primeira zona de luz visível, pelo mesmo caminho do clique real. */
  testarClique() {
    const candidatos = [];
    estado.atual.grupo.traverse((o) => { if (o.userData.zona) candidatos.push(o); });
    const r = canvas.getBoundingClientRect();
    for (const alvo of candidatos) {
      const c = new THREE.Box3().setFromObject(alvo).getCenter(new THREE.Vector3()).project(camera);
      const z = zonaSob({ clientX: r.left + ((c.x + 1) / 2) * r.width, clientY: r.top + ((1 - c.y) / 2) * r.height });
      if (z) {
        avisarPython({ tipo: 'clique', zona: z.zona });
        return z.zona;
      }
    }
    return null;
  },
  estado() {
    return JSON.stringify({ modelo: estado.modelo, corCorpo: estado.corCorpo[estado.modelo], cor1: estado.cor1,
      coresZona: estado.coresZona[estado.modelo] || {}, efeito: efeitos.nome, brilho: efeitos.brilho,
      velocidade: efeitos.velocidade, layout: estado.layout, girarSozinho: controles.girarSozinho,
      zonas: estado.atual.zonas, unidades: estado.atual.unidades.length });
  },
  /** Desenha um quadro fixo (giro em graus a partir da vista inicial) e devolve uma imagem em data URL.
   *  O laço de animação fica pausado até aw3d.fimCaptura(), para gravar sequências sem pulos. */
  quadro(anguloGraus = 0, largura = 960, altura = 720, tempo = null, formato = 'image/png') {
    estado.capturando = true;
    redimensionar(largura, altura, 1);
    controles.voltando = null;
    controles.giro = controles.inicial.giro + THREE.MathUtils.degToRad(anguloGraus);
    controles.inclinacao = controles.inicial.inclinacao;
    controles.distancia = controles.distanciaAlvo = controles.inicial.distancia;
    controles.aplicar();
    efeitos.aplicar(estado.atual.unidades, tempo ?? relogio.t);
    estado.atual.animar?.(tempo ?? relogio.t);
    bloom.render(cena, camera);
    return canvas.toDataURL(formato, 0.92);
  },
  fimCaptura() {
    estado.capturando = false;
    relogio.antes = performance.now();
    return true;
  },
};
window.aw3d = api;

// ---------- clique e dica nas zonas de luz ----------
const raio = new THREE.Raycaster();
const ponteiro = new THREE.Vector2();
const dica = document.getElementById('dica');

function zonaSob(e) {
  const r = canvas.getBoundingClientRect();
  ponteiro.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  raio.setFromCamera(ponteiro, camera);
  const acertos = raio.intersectObjects(estado.atual.grupo.children, true);
  for (const a of acertos) {
    let o = a.object;
    while (o && !o.userData.zona) o = o.parent;
    if (o) return o.userData;
    if (!a.object.userData.atravessar) return null;  // a primeira peça sólida esconde o que há atrás
  }
  return null;
}

canvas.addEventListener('pointermove', (e) => {
  if (controles.arrastando || !estado.atual) { dica.style.display = 'none'; return; }
  const z = zonaSob(e);
  canvas.classList.toggle('sobre-zona', !!z);
  if (z) {
    dica.textContent = z.dica || z.zona;
    dica.style.left = `${e.clientX + 14}px`;
    dica.style.top = `${e.clientY + 12}px`;
    dica.style.display = 'block';
  } else {
    dica.style.display = 'none';
  }
});
canvas.addEventListener('pointerleave', () => { dica.style.display = 'none'; });
canvas.addEventListener('pointerup', (e) => {
  if (controles.moveu || e.button !== 0) return;
  const z = zonaSob(e);
  if (z) avisarPython({ tipo: 'clique', zona: z.zona });
});

// ---------- laço de desenho ----------
// relógio simples (segundos); t pode começar adiantado pelos testes
const relogio = { t: 0, antes: performance.now() };
let tamanho = { w: 0, h: 0, pr: 0 };

function redimensionar(w, h, pr = Math.min(window.devicePixelRatio || 1, 2)) {
  w = Math.max(1, Math.round(w)); h = Math.max(1, Math.round(h));
  if (w === tamanho.w && h === tamanho.h && pr === tamanho.pr) return;
  tamanho = { w, h, pr };
  renderer.setPixelRatio(pr);
  renderer.setSize(w, h, false);
  bloom.setSize(Math.round(w * pr), Math.round(h * pr));
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  controles.ajustarProporcao();
}

function quadroAnimado() {
  if (estado.capturando) return;
  const agora = performance.now();
  const dt = Math.min((agora - relogio.antes) / 1000, 0.1);
  relogio.antes = agora;
  relogio.t += dt;
  redimensionar(canvas.clientWidth, canvas.clientHeight);
  controles.atualizar(dt);
  efeitos.aplicar(estado.atual.unidades, relogio.t);
  estado.atual.animar?.(relogio.t);
  bloom.render(cena, camera);
}

// ---------- início (parâmetros na URL servem para testes: ?modelo=headset&efeito=onda) ----------
const p = new URLSearchParams(location.search);
if (p.get('layout')) estado.layout = p.get('layout');
api.definirModelo(p.get('modelo') || 'mouse');
if (p.get('corpo')) api.definirCorCorpo(p.get('corpo'));
if (p.get('efeito') || p.get('cor')) api.definirEfeito(normalizarEfeito(p.get('efeito')), p.get('cor'), p.get('cor2'), 50);
if (p.get('girar') === '0') api.girarSozinho(false);
if (p.get('angulo')) controles.giro = controles.inicial.giro + THREE.MathUtils.degToRad(+p.get('angulo'));
if (p.get('tempo')) relogio.t = +p.get('tempo');
renderer.setAnimationLoop(quadroAnimado);
avisarPython({ tipo: 'pronto' });
