// Headset Alienware AW725H (modelo procedural; Dell: 214 mm de altura, 184 mm de largura, 112 mm de
// profundidade, almofadas de 95 mm). Unidade: centímetro. Frente em +z, esquerda em -x.
// Detalhes conferidos nas fotos da Dell:
//   - arco largo (45 mm) forrado de tecido escuro e cinta de suspensão por baixo, com presilhas cinza;
//   - conchas em forma de ovo, com a "proa" para baixo e para a frente; braço preto atrás de cada concha;
//   - almofadas de tecido com favos hexagonais;
//   - logo de alienígena com RGB nas DUAS conchas (manual: "Alien head LED"); LED de energia pequeno;
//   - microfone retrátil saindo da frente da concha esquerda.
import * as THREE from 'three';
import { formaAlien, texturaTecido, texturaFavos, plastico, difusor, unidadeLuz, luminancia } from '../comum.js';

const XC = 7.7;        // centro das conchas (x)
const YC = 6.4;        // altura do centro das conchas
const RY = 5.4, RZ = 4.7, PROF = 2.5;   // semi-eixos da casca (altura, largura, profundidade do domo)

/** Varre um perfil 2D (u = espessura, v = largura em z) ao longo de uma curva plana no plano xy. */
function varrer(pontos, perfil) {
  const pos = [];
  const idx = [];
  const np = perfil.length;
  for (let i = 0; i < pontos.length; i++) {
    const p = pontos[i];
    const a = pontos[Math.max(0, i - 1)], b = pontos[Math.min(pontos.length - 1, i + 1)];
    const t = new THREE.Vector2(b.x - a.x, b.y - a.y).normalize();
    const n = new THREE.Vector2(t.y, -t.x);    // normal para fora do arco
    for (const [u, v] of perfil) pos.push(p.x + n.x * u, p.y + n.y * u, v);
  }
  for (let i = 0; i < pontos.length - 1; i++) {
    for (let j = 0; j < np; j++) {
      const a = i * np + j, b = i * np + ((j + 1) % np), c = (i + 1) * np + j, d = (i + 1) * np + ((j + 1) % np);
      idx.push(a, c, b, b, c, d);
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  // UV simples (para a trama do tecido): u ao longo do arco, v ao redor do perfil
  const uv = [];
  for (let i = 0; i < pontos.length; i++) for (let j = 0; j < np; j++) uv.push(i / (pontos.length - 1) * 8, j / np * 2);
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  g.setIndex(idx);
  g.computeVertexNormals();
  return g;
}

/** Retângulo de cantos redondos como lista de pontos (perfil da faixa). */
function perfilFaixa(espessura, largura, raio, passos = 5) {
  const pts = [];
  const cantos = [[espessura / 2 - raio, largura / 2 - raio, 0], [-espessura / 2 + raio, largura / 2 - raio, Math.PI / 2],
                  [-espessura / 2 + raio, -largura / 2 + raio, Math.PI], [espessura / 2 - raio, -largura / 2 + raio, Math.PI * 1.5]];
  for (const [cu, cv, a0] of cantos) {
    for (let k = 0; k <= passos; k++) {
      const a = a0 + (k / passos) * (Math.PI / 2);
      pts.push([cu + raio * Math.cos(a), cv + raio * Math.sin(a)]);
    }
  }
  return pts.reverse();
}

/** Arco elíptico (centro cx, cy; semi-eixos a, b) entre os ângulos t0 e t1. */
function arco(a, b, cy, t0, t1, n = 90) {
  const pts = [];
  for (let i = 0; i <= n; i++) {
    const t = t0 + (t1 - t0) * (i / n);
    pts.push(new THREE.Vector2(a * Math.cos(t), cy + b * Math.sin(t)));
  }
  return pts;
}

/** Deforma um ponto da concha em forma de ovo: a parte de baixo avança para a frente ("proa"). */
function ovo(v) {
  const baixo = Math.max(0, -v.y / RY);
  const frente = 0.5 * (1 + v.z / RZ);
  v.z += 1.1 * baixo * frente;
  v.y *= 1 + 0.1 * baixo;
}

/** Aplica um mapeamento (rotação própria, sem espelhar) + ovo() a todos os vértices. */
function mapear(g, f) {
  const p = g.attributes.position;
  const v = new THREE.Vector3();
  for (let i = 0; i < p.count; i++) {
    f(v.fromBufferAttribute(p, i));
    ovo(v);
    p.setXYZ(i, v.x, v.y, v.z);
  }
  g.computeVertexNormals();
  return g;
}

/** Casca: meio elipsoide virado para fora (lado = -1 esquerda, 1 direita), em coordenadas da concha. */
function geometriaCasca(lado) {
  const g = new THREE.SphereGeometry(1, 64, 48, 0, Math.PI);   // metade com z >= 0
  return mapear(g, (v) => v.set(lado * (0.9 + v.z * PROF), v.y * RY, -lado * v.x * RZ));
}

/** Aro lateral entre a casca e a almofada. */
function geometriaAro(lado) {
  const g = new THREE.CylinderGeometry(1, 1, 1, 64, 1, true);
  return mapear(g, (v) => v.set(lado * 0.35 + v.y * 1.12, -v.x * RY, v.z * RZ));
}

export function criar() {
  const grupo = new THREE.Group();
  grupo.name = 'AW725H';

  const tecido = texturaTecido();
  tecido.repeat.set(1, 1);
  const favos = texturaFavos();
  favos.repeat.set(5, 5);
  const matCasca = plastico('#202226', 0.42);
  const matTecido = new THREE.MeshPhysicalMaterial({ color: '#2a2c30', roughness: 0.95, bumpMap: tecido, bumpScale: 0.6,
                                                     sheen: 0.6, sheenRoughness: 0.8, sheenColor: new THREE.Color('#5a5f66') });
  const matCinta = new THREE.MeshPhysicalMaterial({ color: '#1e2023', roughness: 0.95, bumpMap: tecido, bumpScale: 0.4,
                                                    sheen: 0.4, sheenColor: new THREE.Color('#44484e') });
  const matAlmofada = new THREE.MeshStandardMaterial({ color: '#17181b', roughness: 0.9, bumpMap: favos, bumpScale: 1.5 });
  const matPreto = plastico('#111214', 0.55);
  const matCinza = plastico('#3a3d42', 0.5);
  const matLogos = [difusor(), difusor()];
  const matLed = new THREE.MeshStandardMaterial({ color: '#111', emissive: '#30ff70', emissiveIntensity: 1.6 });

  // ---- arco principal (tecido) e cinta de suspensão ----
  const arcoTopo = new THREE.Mesh(varrer(arco(XC + 0.6, 10.2, 11.0, -0.12, Math.PI + 0.12), perfilFaixa(1.0, 4.5, 0.45)), matTecido);
  grupo.add(arcoTopo);
  const cinta = new THREE.Mesh(varrer(arco(XC - 0.9, 8.4, 11.0, 0.32, Math.PI - 0.32), perfilFaixa(0.35, 3.2, 0.15)), matCinta);
  grupo.add(cinta);
  // presilhas cinza que prendem a cinta no arco
  for (const lado of [-1, 1]) {
    const t = lado > 0 ? 0.32 : Math.PI - 0.32;
    const pres = new THREE.Mesh(new THREE.BoxGeometry(1.0, 1.6, 3.6), matCinza);
    pres.position.set((XC - 0.3) * Math.cos(t), 11.0 + 9.2 * Math.sin(t) - 0.3, 0);
    pres.rotation.z = t - Math.PI / 2;
    grupo.add(pres);
  }

  // ---- conchas ----
  for (const lado of [-1, 1]) {
    const concha = new THREE.Group();
    concha.position.set(lado * XC, YC, 0);
    grupo.add(concha);

    // casca (meio ovo) virada para fora e aro até a almofada
    const casca = new THREE.Mesh(geometriaCasca(lado), matCasca);
    concha.add(casca);
    concha.add(new THREE.Mesh(geometriaAro(lado), matCasca));
    // almofada (anel) + tecido interno
    const almofada = new THREE.Mesh(new THREE.TorusGeometry(3.45, 1.2, 24, 72), matAlmofada);
    almofada.rotation.y = Math.PI / 2;
    almofada.scale.set(1, 1.08, 0.95);
    almofada.position.x = lado * -1.05;
    concha.add(almofada);
    const interno = new THREE.Mesh(new THREE.CircleGeometry(3.6, 48), matAlmofada);
    interno.rotation.y = lado > 0 ? -Math.PI / 2 : Math.PI / 2;
    interno.scale.set(1, 1.08, 1);
    interno.position.x = lado * -0.6;
    concha.add(interno);

    // logo: projeta a cabeça de alienígena na casca com raios vindos de fora
    casca.updateMatrixWorld(true);
    concha.updateMatrixWorld(true);
    const forma = new THREE.ShapeGeometry(formaAlien(), 24);
    const pos = forma.attributes.position;
    const raio = new THREE.Raycaster();
    const tamanho = 2.3, yLogo = -0.85, zLogo = 0.3;
    for (let i = 0; i < pos.count; i++) {
      const sy = yLogo + pos.getY(i) * tamanho;
      const sz = zLogo - pos.getX(i) * tamanho * lado;   // espelhado: a face fica virada para fora
      raio.set(concha.localToWorld(new THREE.Vector3(lado * 20, sy, sz)), new THREE.Vector3(-lado, 0, 0));
      const hit = raio.intersectObject(casca)[0];
      const x = hit ? concha.worldToLocal(hit.point.clone()).x + lado * 0.03 : lado * 3;
      pos.setXYZ(i, x, sy, sz);
    }
    forma.computeVertexNormals();
    const logo = new THREE.Mesh(forma, matLogos[lado < 0 ? 0 : 1]);
    logo.userData = { zona: lado < 0 ? 'logo_esq' : 'logo_dir', semSombra: true,
                      dica: `Logo AlienFX da concha ${lado < 0 ? 'esquerda' : 'direita'} (RGB): clique para escolher a cor` };
    concha.add(logo);

    // braço preto: desce do arco por trás da concha até o pivô
    const braco = new THREE.CatmullRomCurve3([
      new THREE.Vector3(lado * (XC + 0.5), 11.2, -0.6),
      new THREE.Vector3(lado * (XC + 0.9), 10.0, -3.6),
      new THREE.Vector3(lado * (XC + 0.6), 7.6, -5.2),
      new THREE.Vector3(lado * (XC + 0.2), 6.0, -4.9),
    ]);
    grupo.add(new THREE.Mesh(new THREE.TubeGeometry(braco, 40, 0.42, 12, false), matPreto));
    const ponta = new THREE.Mesh(new THREE.SphereGeometry(0.62, 20, 16), matPreto);
    ponta.position.set(lado * (XC + 0.2), 6.0, -4.75);
    grupo.add(ponta);
    // ponteira do arco (plástico preto onde o tecido termina)
    const ponteira = new THREE.Mesh(new THREE.BoxGeometry(1.25, 1.6, 4.7), matPreto);
    ponteira.position.set(lado * (XC + 0.55), 10.9, 0);
    ponteira.rotation.z = lado * 0.08;
    grupo.add(ponteira);
  }

  // ---- microfone retrátil (concha esquerda, na frente e embaixo) ----
  const fenda = new THREE.Mesh(new THREE.BoxGeometry(0.7, 0.55, 2.4), matPreto);
  fenda.position.set(-XC - 1.15, YC - 3.2, 3.05);
  fenda.rotation.x = -0.65;
  grupo.add(fenda);
  const haste = new THREE.CatmullRomCurve3([
    new THREE.Vector3(-XC - 1.1, YC - 3.6, 3.6),
    new THREE.Vector3(-XC - 0.7, YC - 5.0, 6.2),
    new THREE.Vector3(-XC + 0.4, YC - 5.6, 9.0),
    new THREE.Vector3(-XC + 1.6, YC - 5.7, 10.6),
  ]);
  grupo.add(new THREE.Mesh(new THREE.TubeGeometry(haste, 48, 0.2, 10, false), matPreto));
  const capsula = new THREE.Mesh(new THREE.CapsuleGeometry(0.4, 1.3, 6, 16), matPreto);
  const fim = haste.getPoint(1), dir = haste.getTangent(1);
  capsula.position.copy(fim).addScaledVector(dir, 0.55);
  capsula.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
  grupo.add(capsula);

  // LED de energia (pequeno, na borda de trás da concha esquerda) e botões
  const led = new THREE.Mesh(new THREE.SphereGeometry(0.12, 10, 8), matLed);
  led.position.set(-XC - 0.85, YC - 2.0, -4.25);
  led.userData.semSombra = true;
  grupo.add(led);
  for (const [y, z] of [[YC - 0.6, -4.55], [YC - 1.6, -4.3]]) {
    const b = new THREE.Mesh(new THREE.CylinderGeometry(0.32, 0.32, 0.5, 16), matPreto);
    b.rotation.x = Math.PI / 2;
    b.position.set(-XC - 0.85, y, z);
    grupo.add(b);
  }

  // apoia no chão pelo ponto mais baixo
  const caixa = new THREE.Box3().setFromObject(grupo);
  grupo.position.y = -caixa.min.y;

  const unidades = [
    unidadeLuz('logo_esq', ['logo', 'logo_esq', 'todas'], 0, 0.5, [matLogos[0]]),
    unidadeLuz('logo_dir', ['logo', 'logo_dir', 'todas'], 1, 0.5, [matLogos[1]]),
  ];

  return {
    grupo,
    unidades,
    zonas: ['logo', 'logo_esq', 'logo_dir'],
    vista: { giro: 0.75, inclinacao: 0.22, zoom: 1, sombra: 0.55 },
    definirCorCorpo(hex) {
      const claro = luminancia(hex) > 0.35;
      matCasca.color.set(hex);
      for (const m of matLogos) m.color.set(claro ? '#7d838a' : '#3b3e44');
    },
    descartar() {
      grupo.traverse((o) => { if (o.isMesh) o.geometry.dispose(); });
      tecido.dispose();
      favos.dispose();
    },
  };
}
