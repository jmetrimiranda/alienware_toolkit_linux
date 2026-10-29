// Motor de efeitos de luz (pré-visualização dos efeitos do AlienFX).
// Cada aparelho expõe "unidades" de luz (o logo do mouse, cada logo do headset, cada tecla),
// com uma cor-base e uma posição normalizada (x, y entre 0 e 1). A cada quadro o motor calcula
// a cor e a intensidade de cada unidade e chama unidade.aplicar(cor, intensidade).
import * as THREE from 'three';

export const EFEITOS = ['fixo', 'respirar', 'transicao', 'espectro', 'pulsar', 'arco-iris', 'onda'];

// nomes aceitos (com e sem acento, e os do AWCC em inglês)
const SINONIMOS = {
  'transição': 'transicao', 'arco_iris': 'arco-iris', 'arco-íris': 'arco-iris', 'arcoiris': 'arco-iris',
  static: 'fixo', breathing: 'respirar', morph: 'transicao', spectrum: 'espectro', pulse: 'pulsar',
  rainbow: 'arco-iris', wave: 'onda',
};

export function normalizarEfeito(nome) {
  const n = String(nome || 'fixo').trim().toLowerCase();
  const final = SINONIMOS[n] || n;
  return EFEITOS.includes(final) ? final : 'fixo';
}

const tmp = new THREE.Color();

export class Efeitos {
  constructor() {
    this.nome = 'fixo';
    this.cor2 = new THREE.Color('#ff2bd6');
    this.velocidade = 50;   // 0–100
    this.brilho = 100;      // 0–100
    this.intensidade = 2.6; // multiplicador HDR das zonas acesas (faz o bloom aparecer)
  }

  definir(nome, cor2, velocidade) {
    this.nome = normalizarEfeito(nome);
    if (cor2) this.cor2.set(cor2);
    if (velocidade !== undefined && velocidade !== null) this.velocidade = THREE.MathUtils.clamp(+velocidade, 0, 100);
  }

  /** Atualiza todas as unidades no tempo t (segundos). */
  aplicar(unidades, t) {
    const v = 0.15 + (this.velocidade / 100) * 1.85;   // ciclos por segundo, aproximadamente
    const geral = (this.brilho / 100) * this.intensidade;
    for (const u of unidades) {
      let k = 1;
      const cor = tmp.copy(u.cor);
      switch (this.nome) {
        case 'respirar':
          k = 0.5 - 0.5 * Math.cos(t * v * Math.PI);
          k = k * k;
          break;
        case 'transicao':
          cor.lerp(this.cor2, 0.5 - 0.5 * Math.cos(t * v * Math.PI * 0.8));
          break;
        case 'espectro':
          cor.setHSL((t * v * 0.12) % 1, 1, 0.5);
          break;
        case 'pulsar': {
          // duas batidas curtas e uma pausa
          const f = (t * v * 0.7) % 1;
          k = Math.exp(-(((f - 0.1) / 0.05) ** 2)) + 0.75 * Math.exp(-(((f - 0.3) / 0.05) ** 2));
          break;
        }
        case 'arco-iris':
          cor.setHSL(((t * v * 0.12 - u.x * 0.85 - u.y * 0.15) % 1 + 1) % 1, 1, 0.5);
          break;
        case 'onda': {
          // uma faixa da cor da zona corre da esquerda para a direita sobre a 2ª cor
          const frente = (t * v * 0.35) % 1.6 - 0.3;
          const d = u.x - frente;
          const m = Math.exp(-((d / 0.14) ** 2));
          cor.copy(this.cor2).lerp(u.cor, m);
          k = 0.45 + 0.55 * m;
          break;
        }
        default:
          break;
      }
      u.aplicar(cor, k * geral);
    }
  }
}
