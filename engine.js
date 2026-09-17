/**
 * SAFEBOAT TÉRMICA — rede de análise de imagens térmicas (edge analytics)
 *
 * Este módulo é a implementação de referência do pipeline de manutenção preditiva:
 *   aquisição → normalização → baseline por regime → delta/z-score → blobs →
 *   persistência → classificação por zona → diagnóstico → alerta
 *
 * Roda idêntico no navegador (demo com frames MOCADOS do MLX90640 32×24) e em
 * Node.js — a Bancada já o alimenta com quadros reais pela USB; o firmware Wi-Fi o porta para C, dentro da câmera.
 */
;(function (global) {
  'use strict'

  const W = 32, H = 24            // resolução nativa do MLX90640
  const N = W * H

  // ------------------------------------------------------------- colormap
  // Ironbow clássico de termografia (preto → púrpura → vermelho → amarelo → branco)
  const IRON = [
    [0.00, 0, 0, 20], [0.15, 32, 0, 90], [0.30, 108, 0, 140], [0.45, 180, 20, 110],
    [0.60, 226, 80, 50], [0.75, 250, 150, 20], [0.90, 255, 220, 60], [1.00, 255, 255, 240],
  ]
  function ironbow (t) { // t ∈ [0,1] → [r,g,b]
    t = Math.max(0, Math.min(1, t))
    for (let i = 1; i < IRON.length; i++) {
      if (t <= IRON[i][0]) {
        const [t0, r0, g0, b0] = IRON[i - 1]; const [t1, r1, g1, b1] = IRON[i]
        const k = (t - t0) / (t1 - t0)
        return [r0 + k * (r1 - r0), g0 + k * (g1 - g0), b0 + k * (b1 - b0)]
      }
    }
    return [255, 255, 240]
  }

  // -------------------------------------------------------- cenas mocadas
  // Cada cena é um mapa térmico base (regime de cruzeiro estabilizado) composto
  // por contribuições gaussianas dos equipamentos, como o MLX90640 enxergaria
  // a ~60 cm na praça de máquinas.
  function gauss (x, y, cx, cy, sx, sy) {
    const dx = (x - cx) / sx, dy = (y - cy) / sy
    return Math.exp(-(dx * dx + dy * dy) / 2)
  }

  const LAYOUTS = {
    motor: {
      ambient: 27,
      sources: [ // [cx, cy, sx, sy, amplitude °C]
        [15, 14, 6.5, 4.2, 43],   // bloco do motor ~70°C
        [15, 7, 7.5, 1.6, 88],    // coletor de escape ~115°C
        [24, 7, 2.0, 1.8, 112],   // turbina ~140°C
        [7, 15, 1.9, 1.9, 25],    // alternador ~52°C
        [11, 18, 1.5, 1.4, 19],   // bomba d'água ~46°C
        [21, 19, 1.4, 1.2, 13],   // mancal do eixo ~40°C
      ],
      zones: [ // ordem importa: primeira zona que contém o centróide vence
        { box: [21, 4, 27, 10], label: 'Turbina' },
        { box: [5, 3, 26, 10], label: 'Coletor de escape' },
        { box: [4, 12, 10, 19], label: 'Alternador' },
        { box: [9, 15, 14, 21], label: 'Bomba d’água' },
        { box: [17, 16, 24, 22], label: 'Mancal do eixo' },
      ],
      defaultZone: 'Bloco do motor',
      anomalies: {
        alternador: { cx: 7, cy: 15, sx: 2.0, sy: 2.0, amp: 46, ramp: 22, nome: 'Superaquecimento do alternador' },
        escape: { cx: 13, cy: 7, sx: 2.6, sy: 1.8, amp: 80, ramp: 18, nome: 'Vazamento na junta do escape' },
        mancal: { cx: 21, cy: 19, sx: 1.6, sy: 1.4, amp: 38, ramp: 28, nome: 'Mancal sem lubrificação' },
      },
    },
    painel: {
      ambient: 30,
      sources: [
        [8, 12, 1.1, 7.0, 9],     // barramento A ~39°C
        [16, 12, 1.1, 7.0, 10],   // barramento B ~40°C
        [24, 12, 1.1, 7.0, 8],    // barramento C ~38°C
        [8, 6, 1.6, 1.3, 13],     // disjuntor principal
        [16, 6, 1.6, 1.3, 11],
        [24, 6, 1.6, 1.3, 12],
      ],
      zones: [
        { box: [5, 3, 11, 9], label: 'Disjuntor A' },
        { box: [13, 3, 19, 9], label: 'Disjuntor B' },
        { box: [21, 3, 27, 9], label: 'Disjuntor C' },
        { box: [5, 9, 11, 21], label: 'Barramento A' },
        { box: [13, 9, 19, 21], label: 'Barramento B' },
        { box: [21, 9, 27, 21], label: 'Barramento C' },
      ],
      defaultZone: 'Quadro elétrico',
      anomalies: {
        conexao: { cx: 16, cy: 14, sx: 1.4, sy: 1.6, amp: 44, ramp: 20, nome: 'Conexão frouxa / oxidada' },
        disjuntor: { cx: 24, cy: 6, sx: 1.7, sy: 1.4, amp: 36, ramp: 24, nome: 'Disjuntor sobrecarregado' },
      },
    },
  }

  // diagnóstico sugerido pela IA por zona detectada
  const DIAGNOSTICO = {
    'Turbina': 'Verificar folga do eixo e fluxo de óleo; comparar com curva histórica de EGT.',
    'Coletor de escape': 'Provável vazamento de junta ou trinca — risco de incêndio; inspecionar na próxima parada.',
    'Alternador': 'Rolamento ou regulador em falha iminente; medir tensão de carga e ruído.',
    'Bomba d’água': 'Possível cavitação ou selo seco; checar fluxo de água bruta.',
    'Mancal do eixo': 'Lubrificação insuficiente ou desalinhamento; engraxar e monitorar tendência.',
    'Bloco do motor': 'Aquecimento fora do padrão do regime; verificar arrefecimento.',
    'Disjuntor A': 'Contato interno degradado; reapertar terminais e medir queda de tensão.',
    'Disjuntor B': 'Contato interno degradado; reapertar terminais e medir queda de tensão.',
    'Disjuntor C': 'Contato interno degradado; reapertar terminais e medir queda de tensão.',
    'Barramento A': 'Conexão frouxa/oxidada no barramento; reaperto com torque nominal.',
    'Barramento B': 'Conexão frouxa/oxidada no barramento; reaperto com torque nominal.',
    'Barramento C': 'Conexão frouxa/oxidada no barramento; reaperto com torque nominal.',
    'Quadro elétrico': 'Ponto quente elétrico; termografar de perto e reapertar.',
  }

  // ------------------------------------------------------- câmera mocada
  class MockCamera {
    constructor (name, layout) {
      this.name = name
      this.layout = LAYOUTS[layout]
      this.base = new Float32Array(N)
      const L = this.layout
      for (let y = 0; y < H; y++) {
        for (let x = 0; x < W; x++) {
          let t = L.ambient
          for (const [cx, cy, sx, sy, amp] of L.sources) t += amp * gauss(x, y, cx, cy, sx, sy)
          this.base[y * W + x] = t
        }
      }
      this.anomaly = null       // { def, t0 }
    }
    setAnomaly (key, tSec) {
      this.anomaly = key ? { def: this.layout.anomalies[key], t0: tSec } : null
    }
    // frame simulado no instante tSec (respiração térmica + ruído NETD + anomalia em rampa)
    frame (tSec) {
      const f = new Float32Array(N)
      const breathe = 0.9 * Math.sin(tSec / 9) + 0.4 * Math.sin(tSec / 2.7)
      let an = null, k = 0
      if (this.anomaly) {
        an = this.anomaly.def
        k = Math.min(1, (tSec - this.anomaly.t0) / an.ramp)   // rampa de aquecimento
      }
      for (let y = 0; y < H; y++) {
        for (let x = 0; x < W; x++) {
          let t = this.base[y * W + x] + breathe + (Math.random() - 0.5) * 1.2
          if (an) t += an.amp * k * gauss(x, y, an.cx, an.cy, an.sx, an.sy)
          f[y * W + x] = t
        }
      }
      return f
    }
  }

  // ------------------------------------------------------------- detector
  // Baseline estatístico por pixel (média + variância, Welford) aprendido por
  // regime de operação. Anomalia = z-score alto E delta absoluto relevante,
  // agrupada em blobs com persistência temporal para matar falsos positivos.
  class ThermalDetector {
    constructor (opts = {}) {
      this.learnFrames = opts.learnFrames || 48
      this.zThresh = opts.zThresh || 4        // sensibilidade estatística
      this.dThresh = opts.dThresh || 6        // delta mínimo em °C
      this.minBlob = opts.minBlob || 3        // píxeis conectados mínimos
      this.persist = opts.persist || 3        // frames consecutivos p/ confirmar
      this.alpha = 0.004                      // adaptação lenta do baseline
      this.reset()
    }
    reset () {
      this.mean = new Float32Array(N)
      this.m2 = new Float32Array(N)
      this.n = 0
      this.tracks = []
    }
    process (frame, layout) {
      const delta = new Float32Array(N)
      // fase 1: aprendizado do baseline (Welford)
      if (this.n < this.learnFrames) {
        this.n++
        for (let i = 0; i < N; i++) {
          const d = frame[i] - this.mean[i]
          this.mean[i] += d / this.n
          this.m2[i] += d * (frame[i] - this.mean[i])
        }
        return { state: 'learning', progress: this.n / this.learnFrames, delta, blobs: [] }
      }
      // fase 2: monitoramento
      const mask = new Uint8Array(N)
      for (let i = 0; i < N; i++) {
        const sigma = Math.max(0.5, Math.sqrt(this.m2[i] / (this.n - 1)))
        delta[i] = frame[i] - this.mean[i]
        const z = delta[i] / sigma
        if (z > this.zThresh && delta[i] > this.dThresh) mask[i] = 1
        else this.mean[i] += this.alpha * delta[i]   // deriva ambiente ≠ falha
      }
      // blobs: componentes conectados 4-vizinhos
      const labels = new Int16Array(N).fill(-1)
      const blobs = []
      for (let i = 0; i < N; i++) {
        if (!mask[i] || labels[i] !== -1) continue
        const stack = [i]; const px = []
        labels[i] = blobs.length
        while (stack.length) {
          const p = stack.pop(); px.push(p)
          const x = p % W, y = (p / W) | 0
          for (const [nx, ny] of [[x - 1, y], [x + 1, y], [x, y - 1], [x, y + 1]]) {
            if (nx < 0 || nx >= W || ny < 0 || ny >= H) continue
            const q = ny * W + nx
            if (mask[q] && labels[q] === -1) { labels[q] = blobs.length; stack.push(q) }
          }
        }
        if (px.length < this.minBlob) continue
        let x0 = W, y0 = H, x1 = 0, y1 = 0, maxT = -1e9, maxD = -1e9, sx = 0, sy = 0
        for (const p of px) {
          const x = p % W, y = (p / W) | 0
          x0 = Math.min(x0, x); x1 = Math.max(x1, x)
          y0 = Math.min(y0, y); y1 = Math.max(y1, y)
          sx += x; sy += y
          maxT = Math.max(maxT, frame[p]); maxD = Math.max(maxD, delta[p])
        }
        blobs.push({ x0, y0, x1, y1, cx: sx / px.length, cy: sy / px.length, px: px.length, maxT, maxD })
      }
      // persistência temporal: casa blobs com trilhas por proximidade de centróide
      for (const t of this.tracks) t.seen = false
      for (const b of blobs) {
        let best = null, bd = 4
        for (const t of this.tracks) {
          const d = Math.hypot(t.cx - b.cx, t.cy - b.cy)
          if (d < bd) { bd = d; best = t }
        }
        if (best) { best.count++; best.cx = b.cx; best.cy = b.cy; best.seen = true; b.count = best.count }
        else { this.tracks.push({ cx: b.cx, cy: b.cy, count: 1, seen: true }); b.count = 1 }
      }
      this.tracks = this.tracks.filter(t => t.seen)
      const confirmed = blobs.filter(b => b.count >= this.persist)
      // classificação por zona + severidade + diagnóstico
      for (const b of confirmed) {
        b.zone = layout.defaultZone
        for (const z of layout.zones) {
          const [zx0, zy0, zx1, zy1] = z.box
          if (b.cx >= zx0 && b.cx <= zx1 && b.cy >= zy0 && b.cy <= zy1) { b.zone = z.label; break }
        }
        b.severity = b.maxD >= 30 ? 'critico' : b.maxD >= 15 ? 'alerta' : 'atencao'
        b.diag = DIAGNOSTICO[b.zone] || 'Investigar ponto quente fora do padrão.'
      }
      return { state: 'monitoring', delta, blobs: confirmed }
    }
  }

  // ------------------------------------------------------------ renderer
  const off = typeof document !== 'undefined' ? document.createElement('canvas') : null
  if (off) { off.width = W; off.height = H }

  // desenha um frame (ou delta) com colormap ironbow; retorna [min,max] usados
  function renderThermal (canvas, data, opts = {}) {
    const ctx2 = off.getContext('2d')
    const img = ctx2.createImageData(W, H)
    let lo = opts.min, hi = opts.max
    if (lo === undefined) { lo = Infinity; hi = -Infinity; for (let i = 0; i < N; i++) { lo = Math.min(lo, data[i]); hi = Math.max(hi, data[i]) } }
    const span = Math.max(1e-3, hi - lo)
    for (let i = 0; i < N; i++) {
      const [r, g, b] = ironbow((data[i] - lo) / span)
      img.data[i * 4] = r; img.data[i * 4 + 1] = g; img.data[i * 4 + 2] = b; img.data[i * 4 + 3] = 255
    }
    ctx2.putImageData(img, 0, 0)
    const ctx = canvas.getContext('2d')
    ctx.imageSmoothingEnabled = opts.pixelated !== true
    ctx.imageSmoothingQuality = 'high'
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(off, 0, 0, canvas.width, canvas.height)
    return [lo, hi]
  }

  // caixas dos blobs confirmados sobre o canvas já renderizado
  function drawBlobs (canvas, blobs) {
    const ctx = canvas.getContext('2d')
    const kx = canvas.width / W, ky = canvas.height / H
    const cor = { critico: '#ff453a', alerta: '#ff9f0a', atencao: '#ffd60a' }
    for (const b of blobs) {
      const x = (b.x0 - 0.5) * kx, y = (b.y0 - 0.5) * ky
      const w = (b.x1 - b.x0 + 2) * kx, h = (b.y1 - b.y0 + 2) * ky
      ctx.strokeStyle = cor[b.severity]
      ctx.lineWidth = 2
      ctx.strokeRect(x, y, w, h)
      ctx.font = '600 11px -apple-system, Segoe UI, sans-serif'
      const txt = `${b.zone} +${b.maxD.toFixed(0)}°C`
      const tw = ctx.measureText(txt).width + 10
      const ty = y > 18 ? y - 17 : y + h + 3
      ctx.fillStyle = 'rgba(6,7,12,.82)'
      ctx.fillRect(x, ty, tw, 15)
      ctx.fillStyle = cor[b.severity]
      ctx.fillText(txt, x + 5, ty + 11)
    }
  }

  global.Termica = { W, H, ironbow, MockCamera, ThermalDetector, renderThermal, drawBlobs, LAYOUTS, DIAGNOSTICO }
})(typeof window !== 'undefined' ? window : globalThis)
