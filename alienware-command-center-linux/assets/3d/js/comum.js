// Peças compartilhadas pelos modelos: contorno da cabeça de alienígena, texturas feitas em canvas
// (relevo de borracha, trama de tecido, sombra de contato) e materiais base.
import * as THREE from 'three';

/**
 * Cabeça de alienígena (desenho próprio, inspirado no logo): crânio largo, queixo fino e
 * olhos amendoados inclinados, que viram furos. Altura 1 (y de -0,5 no queixo a +0,5 no topo).
 */
export function formaAlien() {
  const f = new THREE.Shape();
  f.moveTo(0, -0.5);
  f.bezierCurveTo(0.13, -0.47, 0.36, -0.17, 0.4, 0.08);
  f.bezierCurveTo(0.44, 0.33, 0.26, 0.5, 0, 0.5);
  f.bezierCurveTo(-0.26, 0.5, -0.44, 0.33, -0.4, 0.08);
  f.bezierCurveTo(-0.36, -0.17, -0.13, -0.47, 0, -0.5);
  for (const lado of [1, -1]) {
    const olho = new THREE.Path();
    olho.moveTo(lado * 0.055, -0.07);
    olho.bezierCurveTo(lado * 0.07, 0.06, lado * 0.2, 0.13, lado * 0.33, 0.12);
    olho.bezierCurveTo(lado * 0.3, 0.0, lado * 0.17, -0.11, lado * 0.055, -0.07);
    f.holes.push(olho);
  }
  return f;
}

/** Canvas -> textura (repetível). */
function textura(canvas, repetir = true, cor = false) {
  const t = new THREE.CanvasTexture(canvas);
  if (repetir) t.wrapS = t.wrapT = THREE.RepeatWrapping;
  if (cor) t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}

/** Relevo em losangos (borracha da roda do mouse), para bumpMap. */
export function texturaLosangos() {
  const c = document.createElement('canvas');
  c.width = c.height = 128;
  const g = c.getContext('2d');
  g.fillStyle = '#000';
  g.fillRect(0, 0, 128, 128);
  for (let y = 0; y < 8; y++) {
    for (let x = 0; x < 8; x++) {
      const cx = x * 16 + (y % 2) * 8 + 8, cy = y * 16 + 8;
      const gr = g.createRadialGradient(cx, cy, 0, cx, cy, 8);
      gr.addColorStop(0, '#fff');
      gr.addColorStop(1, '#000');
      g.fillStyle = gr;
      g.beginPath();
      g.moveTo(cx, cy - 8); g.lineTo(cx + 8, cy); g.lineTo(cx, cy + 8); g.lineTo(cx - 8, cy);
      g.fill();
    }
  }
  return textura(c);
}

/** Trama de tecido (arco do headset), para bumpMap. */
export function texturaTecido() {
  const c = document.createElement('canvas');
  c.width = c.height = 256;
  const g = c.getContext('2d');
  const img = g.createImageData(256, 256);
  for (let y = 0; y < 256; y++) {
    for (let x = 0; x < 256; x++) {
      const fio = (Math.sin(x * 1.6) * 0.5 + 0.5) * (Math.sin(y * 1.6 + (x % 8 < 4 ? 0 : 1.6)) * 0.5 + 0.5);
      const v = Math.floor(90 + fio * 120 + Math.random() * 45);
      const i = (y * 256 + x) * 4;
      img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
      img.data[i + 3] = 255;
    }
  }
  g.putImageData(img, 0, 0);
  return textura(c);
}

/** Favos hexagonais (almofadas e grade interna do headset), para bumpMap. */
export function texturaFavos() {
  const c = document.createElement('canvas');
  c.width = 222; c.height = 256;
  const g = c.getContext('2d');
  g.fillStyle = '#fff';
  g.fillRect(0, 0, c.width, c.height);
  g.strokeStyle = '#000';
  g.lineWidth = 5;
  const r = 18.5, w = Math.sqrt(3) * r;
  for (let linha = -1; linha < 10; linha++) {
    for (let col = -1; col < 8; col++) {
      const cx = col * w + (linha % 2 ? w / 2 : 0), cy = linha * r * 1.5;
      g.beginPath();
      for (let k = 0; k < 6; k++) {
        const a = Math.PI / 6 + (k * Math.PI) / 3;
        g.lineTo(cx + r * Math.cos(a), cy + r * Math.sin(a));
      }
      g.closePath();
      g.stroke();
    }
  }
  return textura(c);
}

/** Sombra de contato: mancha radial escura e suave, colocada logo acima do chão. */
export function sombraContato(largura, profundidade, opacidade = 0.75) {
  const c = document.createElement('canvas');
  c.width = c.height = 128;
  const g = c.getContext('2d');
  const gr = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  gr.addColorStop(0, 'rgba(0,0,0,1)');
  gr.addColorStop(0.45, 'rgba(0,0,0,0.6)');
  gr.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = gr;
  g.fillRect(0, 0, 128, 128);
  const malha = new THREE.Mesh(
    new THREE.PlaneGeometry(largura, profundidade),
    new THREE.MeshBasicMaterial({ map: textura(c, false), color: 0x000000, transparent: true,
                                  opacity: opacidade, depthWrite: false }),
  );
  malha.rotation.x = -Math.PI / 2;
  malha.position.y = 0.02;
  malha.renderOrder = -1;
  return malha;
}

/** Luminância de uma cor hexadecimal (0–1), para escolher tons de peças secundárias. */
export function luminancia(hex) {
  const c = new THREE.Color(hex);
  return 0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b;
}

/** Plástico fosco com leve verniz (corpo dos aparelhos). */
export function plastico(cor, aspereza = 0.5) {
  return new THREE.MeshPhysicalMaterial({ color: cor, roughness: aspereza, metalness: 0,
                                          clearcoat: 0.12, clearcoatRoughness: 0.5 });
}

/** Material das zonas de luz: difusor leitoso que acende com emissive. */
export function difusor(corApagada = '#c9ccd1') {
  return new THREE.MeshStandardMaterial({ color: corApagada, roughness: 0.35, metalness: 0,
                                          emissive: 0x000000, emissiveIntensity: 1 });
}

/** Unidade de luz padrão (um ou mais materiais de difusor). */
export function unidadeLuz(id, zonas, x, y, materiais, corInicial = '#00c8d7') {
  return {
    id, zonas, x, y,
    cor: new THREE.Color(corInicial),
    aplicar(cor, k) {
      for (const m of materiais) {
        m.emissive.copy(cor);
        m.emissiveIntensity = k;
      }
    },
  };
}
