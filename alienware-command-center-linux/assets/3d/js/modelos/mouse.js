// Mouse Alienware AW720M (modelo procedural, medidas da Dell: 125 x 62 x 37,5 mm).
// Unidade: centímetro. Frente do mouse em -z, traseira em +z, esquerda em -x.
// Detalhes conferidos nas fotos e no manual da Dell:
//   - corpo simétrico com cintura leve; botões principais separados por costura em "V";
//   - roda de borracha com relevo em losangos, numa fenda escura;
//   - 2 botões laterais de CADA lado (8 botões no total; o de DPI e o LED de DPI ficam embaixo);
//   - única zona RGB: a cabeça de alienígena na palma; porta USB-C na frente.
import * as THREE from 'three';
import { formaAlien, texturaLosangos, plastico, difusor, unidadeLuz, luminancia } from '../comum.js';

const L = 12.5, W = 6.2, H = 3.75;
const BASE = 0.28;            // faixa escura da base
const HT = H - BASE;          // altura do casco
const A0 = W / 2, B = L / 2;

// expoente da superelipse do contorno: frente mais quadrada, traseira mais redonda
const expoente = (z) => (z < 0 ? 3.4 : 2.3);

// largura relativa ao longo do comprimento: cintura no meio e frente um pouco mais estreita
function modulacao(z) {
  const cintura = 1 - 0.07 * Math.exp(-(((z - 0.3) / 1.8) ** 2));
  const frente = 0.94 + 0.06 * THREE.MathUtils.smoothstep(z, -5.5, 2.5);
  return cintura * frente;
}

// altura do topo ao longo do comprimento (u = 0 na frente, 1 atrás); pico a 60%
function alturaTopo(z) {
  const u = THREE.MathUtils.clamp((z + B) / L, 0, 1);
  if (u < 0.6) return 2.35 + (HT - 2.35) * Math.sin((u / 0.6) * Math.PI / 2) ** 1.3;
  return 0.9 + (HT - 0.9) * Math.cos(((u - 0.6) / 0.4) * Math.PI / 2) ** 0.8;
}

// queda do casco do centro (r=0) até a borda (r=1): topo arredondado, laterais quase verticais
const queda = (r) => Math.pow(Math.max(0, 1 - r ** 3), 0.42);

/** Ponto do contorno na escala r (0 = centro, 1 = borda) e ângulo phi. */
function plano(r, phi) {
  const c = Math.cos(phi), s = Math.sin(phi);
  const n = expoente(s);
  const z0 = B * Math.sign(s) * Math.abs(s) ** (2 / n);
  const x0 = A0 * Math.sign(c) * Math.abs(c) ** (2 / n);
  const z = r * z0;
  return [r * x0 * modulacao(z), z];
}

/** "Raio" normalizado de um ponto (x, z) da vista de cima (inverso de plano()). */
function raioDe(x, z) {
  const n = expoente(z);
  const x0 = x / modulacao(z);
  return Math.pow(Math.abs(x0 / A0) ** n + Math.abs(z / B) ** n, 1 / n);
}

/** Altura da superfície em (x, z). */
export function altura(x, z) {
  const r = raioDe(x, z);
  return r >= 1 ? BASE : BASE + alturaTopo(z) * queda(r);
}

/** Meia largura do contorno na posição z. */
function meiaLargura(z) {
  const n = expoente(z);
  const t = Math.max(0, 1 - Math.abs(z / B) ** n);
  return A0 * Math.pow(t, 1 / n) * modulacao(z);
}

/** x da parede lateral na altura y e posição z (para encaixar os botões laterais). */
function paredeX(y, z) {
  const q = THREE.MathUtils.clamp((y - BASE) / alturaTopo(z), 0, 0.999);
  const r = Math.pow(1 - Math.pow(q, 1 / 0.42), 1 / 3);
  const n = expoente(z);
  const x0 = A0 * Math.pow(Math.max(0, r ** n - Math.abs(z / B) ** n), 1 / n);
  return x0 * modulacao(z);
}

// ---------- geometrias ----------

function geometriaCasco() {
  const NR = 64, NP = 180;
  const pos = [];
  const idx = [];
  for (let i = 0; i <= NR; i++) {
    const r = Math.sin((Math.PI / 2) * (i / NR));   // anéis mais densos perto da borda
    for (let j = 0; j < NP; j++) {
      const [x, z] = plano(r, (j / NP) * Math.PI * 2);
      pos.push(x, BASE + alturaTopo(z) * queda(r), z);
    }
  }
  for (let i = 0; i < NR; i++) {
    for (let j = 0; j < NP; j++) {
      const a = i * NP + j, b = i * NP + ((j + 1) % NP);
      const c = (i + 1) * NP + j, d = (i + 1) * NP + ((j + 1) % NP);
      idx.push(a, b, c, b, d, c);
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setIndex(idx);
  g.computeVertexNormals();
  return g;
}

/** Projeta uma forma 2D (vista de cima) na superfície: (sx, sy) da forma -> (x, z) do mouse. */
function decalque(forma, cx, cz, escala, elevar = 0.012, giro = 0) {
  const g = new THREE.ShapeGeometry(forma, 24);
  const p = g.attributes.position;
  const cs = Math.cos(giro), sn = Math.sin(giro);
  for (let i = 0; i < p.count; i++) {
    const sx = p.getX(i) * escala, sy = p.getY(i) * escala;
    const x = cx + sx * cs - sy * sn;
    const z = cz - (sx * sn + sy * cs);   // o "alto" da forma aponta para a frente (-z)
    p.setXYZ(i, x, altura(x, z) + elevar, z);
  }
  g.computeVertexNormals();
  return g;
}

/** Costura: tubo fino seguindo pontos (x, z) sobre a superfície. */
function costura(pontosXZ, raio = 0.026) {
  const pts = pontosXZ.map(([x, z]) => new THREE.Vector3(x, altura(x, z) + 0.004, z));
  const curva = new THREE.CatmullRomCurve3(pts);
  return new THREE.TubeGeometry(curva, pts.length * 3, raio, 6, false);
}

function retanguloArredondado(w, h, r) {
  const f = new THREE.Shape();
  const x = -w / 2, y = -h / 2;
  f.moveTo(x + r, y);
  f.lineTo(x + w - r, y); f.quadraticCurveTo(x + w, y, x + w, y + r);
  f.lineTo(x + w, y + h - r); f.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  f.lineTo(x + r, y + h); f.quadraticCurveTo(x, y + h, x, y + h - r);
  f.lineTo(x, y + r); f.quadraticCurveTo(x, y, x + r, y);
  return f;
}

// ---------- montagem ----------

export function criar() {
  const grupo = new THREE.Group();
  grupo.name = 'AW720M';

  const matCorpo = plastico('#202226', 0.52);
  const matLateral = plastico('#2b2d31', 0.6);
  const matEscuro = new THREE.MeshStandardMaterial({ color: '#0d0e10', roughness: 0.75 });
  const matCostura = new THREE.MeshStandardMaterial({ color: '#08090a', roughness: 0.9 });
  const losangos = texturaLosangos();
  losangos.repeat.set(26, 2);
  const matBorracha = new THREE.MeshStandardMaterial({ color: '#141518', roughness: 0.85,
                                                       bumpMap: losangos, bumpScale: 1.2 });
  const matLogo = difusor();

  // casco
  const casco = new THREE.Mesh(geometriaCasco(), matCorpo);
  grupo.add(casco);

  // base escura (um pouco recolhida em relação ao casco)
  const contorno = [];
  for (let j = 0; j < 120; j++) {
    const [x, z] = plano(0.975, (j / 120) * Math.PI * 2);
    contorno.push(new THREE.Vector2(x, -z));
  }
  const base = new THREE.Mesh(new THREE.ExtrudeGeometry(new THREE.Shape(contorno),
    { depth: BASE + 0.12, bevelEnabled: false }), matEscuro);
  base.rotation.x = -Math.PI / 2;
  base.position.y = 0.01;
  grupo.add(base);

  // fenda e roda de rolagem
  const zRoda = -3.55;
  grupo.add(new THREE.Mesh(decalque(retanguloArredondado(0.98, 2.6, 0.45), 0, zRoda, 1, 0.006), matEscuro));
  const roda = new THREE.Mesh(new THREE.CylinderGeometry(1.05, 1.05, 0.6, 64, 1), matBorracha);
  roda.rotation.z = Math.PI / 2;
  roda.position.set(0, altura(0, zRoda) - 0.5, zRoda);
  grupo.add(roda);

  // costura central (frente -> roda e roda -> encontro do "V")
  const zFrente = -B * 0.999, zEncontro = 0.95;
  const central1 = [];
  for (let t = 0; t <= 1.0001; t += 0.1) central1.push([0, THREE.MathUtils.lerp(zFrente, zRoda - 1.32, t)]);
  const central2 = [];
  for (let t = 0; t <= 1.0001; t += 0.1) central2.push([0, THREE.MathUtils.lerp(zRoda + 1.32, zEncontro, t)]);
  grupo.add(new THREE.Mesh(costura(central1), matCostura));
  grupo.add(new THREE.Mesh(costura(central2), matCostura));
  // descida da costura central pela face da frente
  const desce = [];
  for (let k = 0; k <= 10; k++) {
    const r = 0.93 + k * 0.007;
    const [x, z] = plano(r, -Math.PI / 2);
    desce.push(new THREE.Vector3(x, BASE + alturaTopo(z) * queda(r), z - 0.004));
  }
  grupo.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(desce), 20, 0.026, 6), matCostura));

  // costuras em "V" dos botões principais (curva de Bézier na vista de cima)
  for (const lado of [-1, 1]) {
    const z0 = -B * 0.965;
    const p0 = new THREE.Vector2(lado * meiaLargura(z0) * 0.8, z0);
    const p1 = new THREE.Vector2(lado * meiaLargura(-2.8) * 0.95, -2.8);
    const p2 = new THREE.Vector2(lado * meiaLargura(0.2) * 0.78, 0.2);
    const p3 = new THREE.Vector2(0, zEncontro);
    const bez = new THREE.CubicBezierCurve(p0, p1, p2, p3);
    grupo.add(new THREE.Mesh(costura(bez.getPoints(40).map((v) => [v.x, v.y])), matCostura));
  }

  // botões laterais: dois de cada lado, encaixados na parede
  for (const lado of [-1, 1]) {
    for (const zc of [-0.55, 0.75]) {
      const y = BASE + alturaTopo(zc) * 0.5;
      const x = paredeX(y, zc);
      const inclinacao = Math.atan2(paredeX(y, zc + 0.3) - paredeX(y, zc - 0.3), 0.6);
      const botao = new THREE.Mesh(new THREE.CapsuleGeometry(0.22, 0.72, 6, 18), matLateral);
      botao.rotation.set(Math.PI / 2, lado * -inclinacao, 0, 'YXZ');
      botao.scale.set(0.5, 1, 1);
      botao.position.set(lado * (x - 0.02), y, zc);
      grupo.add(botao);
    }
  }

  // porta USB-C na frente
  const porta = new THREE.Mesh(new THREE.BoxGeometry(0.95, 0.34, 0.12), matEscuro);
  porta.position.set(0, BASE + 0.75, -B * 0.974 - 0.02);
  grupo.add(porta);

  // logo (cabeça de alienígena) na palma: a única zona RGB
  const logo = new THREE.Mesh(decalque(formaAlien(), 0, 3.3, 1.45, 0.014), matLogo);
  logo.userData = { zona: 'logo', dica: 'Logo AlienFX (RGB): clique para escolher a cor' };
  logo.userData.semSombra = true;
  grupo.add(logo);

  const unidades = [unidadeLuz('logo', ['logo', 'todas'], 0.5, 0.5, [matLogo])];

  return {
    grupo,
    unidades,
    zonas: ['logo'],
    vista: { giro: -0.75, inclinacao: 0.45, zoom: 1, sombra: 0.8 },
    definirCorCorpo(hex) {
      const claro = luminancia(hex) > 0.35;
      matCorpo.color.set(hex);
      matLateral.color.set(hex).lerp(new THREE.Color(claro ? '#9da2a8' : '#3a3d42'), 0.35);
      matLogo.color.set(claro ? '#7d838a' : '#3b3e44');
    },
    descartar() {
      grupo.traverse((o) => { if (o.isMesh) o.geometry.dispose(); });
      losangos.dispose();
    },
  };
}
