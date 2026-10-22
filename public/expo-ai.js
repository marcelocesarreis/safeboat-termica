/**
 * SAFEBOAT TÉRMICA — reconhecimento para o estande (pessoa · mão · objeto quente · objeto frio)
 *
 * Com 32×24 píxeis não há textura nem contorno fino: o que distingue as coisas é a ASSINATURA
 * TÉRMICA — faixa de temperatura, tamanho, forma e movimento. Por isso o classificador é feito
 * de regras explicáveis sobre blobs, não de uma rede neural que exigiria um banco de quadros
 * rotulados que ainda não existe. Pipeline por quadro:
 *
 *   ambiente (percentil 20, sobe devagar/desce rápido) → 3 máscaras (morno · quente · frio)
 *   → componentes conectados → características → classe → trilhas (id estável, voto das
 *   últimas classes, caixa suavizada, confirmação em N quadros, supressão de fundo parado)
 *
 * Roda idêntico no navegador (public/expo.html) e no Node (tools/test-expo-ai.cjs).
 */
;(function (global) {
  'use strict'
  const W = 32, H = 24, N = W * H

  const DEF = {
    warmD: 3.0,       // °C acima do ambiente = morno (pele, roupa)
    hotT: 42,         // °C absolutos = objeto quente
    alertT: 65,       // °C = ponto quente que, no barco, viraria alerta
    coldD: 4.0,       // °C abaixo do ambiente = objeto frio
    personPx: 14,     // píxeis mornos conectados para chamar de pessoa
    grow: 2,          // píxeis de dilatação para juntar os pedaços de uma mesma pessoa
    coreD: 5.0,       // °C acima do ambiente = núcleo de pele exposta
    coreMin: 29.5,    // °C mínimos para contar como pele (roupa aquecida fica abaixo)
    smallExtra: 1.5,  // blob menor que isso precisa deste contraste a mais, em °C
    skinNear: 31.5,   // blob pequeno acima disto = mão/rosto perto; abaixo = pessoa ao longe (pele diluída no píxel)
    confirm: 3,       // quadros seguidos para aparecer
    miss: 4,          // quadros sem ver antes de sumir
    staticSec: 40,    // blob pequeno/frio parado por este tempo vira fundo (lâmpada, saída de ar, vitrine)
    fovH: 55,         // MLX90640ESF-BAB: 55° × 35°
    bodyW: 0.5,       // largura típica do vulto morno de uma pessoa, em metros
  }

  const KINDS = {
    pessoa:       { label: 'Pessoa',              cor: '#B0DE8F' },
    pessoa_longe: { label: 'Pessoa ao longe',     cor: '#8fc7de' },
    mao:          { label: 'Mão ou objeto morno', cor: '#ffd60a' },
    quente:       { label: 'Objeto quente',       cor: '#ff9f0a' },
    muito_quente: { label: 'Superfície muito quente', cor: '#ff453a' },
    chama:        { label: 'Fonte de calor intensa',  cor: '#ff453a' },
    frio:         { label: 'Objeto frio',         cor: '#5ac8fa' },
  }

  // componentes conectados (8 vizinhos) de uma máscara
  function components (mask) {
    const seen = new Uint8Array(N), out = []
    for (let i = 0; i < N; i++) {
      if (!mask[i] || seen[i]) continue
      const stack = [i], px = []; seen[i] = 1
      while (stack.length) {
        const p = stack.pop(); px.push(p)
        const x = p % W, y = (p / W) | 0
        for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
          const nx = x + dx, ny = y + dy
          if (nx < 0 || nx >= W || ny < 0 || ny >= H) continue
          const q = ny * W + nx
          if (mask[q] && !seen[q]) { seen[q] = 1; stack.push(q) }
        }
      }
      out.push(px)
    }
    return out
  }

  function dilate (mask, r) {
    if (!r) return mask
    const o = new Uint8Array(N)
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      if (!mask[y * W + x]) continue
      for (let dy = -r; dy <= r; dy++) for (let dx = -r; dx <= r; dx++) {
        const xx = x + dx, yy = y + dy
        if (xx >= 0 && xx < W && yy >= 0 && yy < H) o[yy * W + xx] = 1
      }
    }
    return o
  }

  function blur3 (f) {   // 1-2-1 × 1-2-1, borda replicada
    const o = new Float32Array(N)
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      let s = 0
      for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
        const xx = Math.max(0, Math.min(W - 1, x + dx)), yy = Math.max(0, Math.min(H - 1, y + dy))
        s += f[yy * W + xx] * (2 - Math.abs(dx)) * (2 - Math.abs(dy))
      }
      o[y * W + x] = s / 16
    }
    return o
  }

  function stats (px, f, hotT) {
    let x0 = W, y0 = H, x1 = 0, y1 = 0, sx = 0, sy = 0, maxT = -1e9, minT = 1e9, sum = 0, skinMax = -1e9, hotPx = 0, skinPx = 0
    for (const p of px) {
      const x = p % W, y = (p / W) | 0, v = f[p]
      if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y
      sx += x; sy += y; sum += v
      if (v > maxT) maxT = v; if (v < minT) minT = v
      if (v >= hotT) hotPx++
      else if (v <= 38.5) { if (v > skinMax) skinMax = v; if (v >= 28) skinPx++ }   // 38,5–hotT é halo de objeto quente, não pele
    }
    return { x0, y0, x1, y1, cx: sx / px.length, cy: sy / px.length, px: px.length, maxT, minT, meanT: sum / px.length, skinMax, hotPx, skinPx }
  }

  class ExpoAI {
    constructor (opts) { this.o = Object.assign({}, DEF, opts || {}); this.reset() }
    reset () { this.amb = null; this.tracks = []; this.nextId = 1; this.lastT = null }

    _ambient (f, dt) {
      const s = Float32Array.from(f).sort()
      const p20 = s[(N * 0.2) | 0]
      if (this.amb == null) this.amb = p20
      else { const tau = p20 < this.amb ? 2 : 25; this.amb += (p20 - this.amb) * Math.min(1, dt / tau) }   // quem enche a cena é gente: sobe devagar
      return this.amb
    }

    _distance (b) {
      const wpx = b.x1 - b.x0 + 1
      if (b.x0 === 0 || b.x1 === W - 1 || b.px > 300) return { m: null, txt: 'a menos de 1 m' }
      const a = (this.o.fovH / W) * Math.PI / 180
      let m = this.o.bodyW / (wpx * Math.tan(a)); m = Math.max(0.5, Math.min(5, Math.round(m * 2) / 2))
      return { m, txt: '≈ ' + m.toFixed(1).replace('.', ',') + ' m' }
    }

    _classify (group, b, amb) {
      const o = this.o
      if (group === 'hot') {
        const kind = b.maxT >= 120 ? 'chama' : b.maxT >= o.alertT ? 'muito_quente' : 'quente'
        return { kind, conf: Math.min(99, 82 + (b.maxT - o.hotT) / 3), temp: b.maxT,
          detail: kind === 'quente' ? 'bebida quente, carregador, lâmpada…' : kind === 'chama' ? 'chama, brasa ou resistência' : 'no barco: escape, alternador, conexão elétrica' }
      }
      if (group === 'cold') return { kind: 'frio', conf: Math.min(96, 70 + (amb - b.minT) * 3), temp: b.minT, detail: 'bebida gelada, gelo, metal frio…' }
      if (b.px >= o.personPx) {
        const d = this._distance(b)
        return { kind: 'pessoa', conf: Math.min(99, 72 + Math.min(22, b.px / 4) + (b.skinMax >= 30 && b.skinMax <= 36.5 ? 5 : 0)), temp: b.skinMax, detail: d.txt, dist: d.m }
      }
      if (b.skinMax >= o.skinNear) return { kind: 'mao', conf: 78, temp: b.skinMax, detail: 'perto da câmera' }
      return { kind: 'pessoa_longe', conf: 62, temp: b.skinMax, detail: 'a mais de 3 m' }
    }

    /** frame: Float32Array(768) em °C · tSec: relógio em segundos → { amb, objects, people, hottest, alert } */
    process (frame, tSec) {
      const o = this.o
      const dt = this.lastT == null ? 0.125 : Math.max(0.01, Math.min(2, tSec - this.lastT)); this.lastT = tSec
      const amb = this._ambient(frame, dt)
      const warmT = amb + o.warmD, coldT = amb - o.coldD
      // morno/frio saem de uma cópia suavizada 3×3 (o MLX90640 a 16 Hz tem ~1 °C de ruído por píxel e cantos mais quentes);
      // o QUENTE sai do quadro cru: um ponto de 1 píxel a 80 °C não pode ser diluído
      const soft = blur3(frame)
      const mWarm = new Uint8Array(N), mHot = new Uint8Array(N), mCold = new Uint8Array(N)
      for (let i = 0; i < N; i++) { if (soft[i] >= warmT) mWarm[i] = 1; if (frame[i] >= o.hotT) mHot[i] = 1; if (soft[i] <= coldT) mCold[i] = 1 }

      const found = []
      for (const px of components(mHot)) found.push({ group: 'hot', b: stats(px, frame, o.hotT) })
      for (const px of components(mCold)) { if (px.length >= 3) found.push({ group: 'cold', b: stats(px, soft, o.hotT) }) }
      // uma pessoa aparece em pedaços (rosto a 33 °C, roupa a 26–29 °C com vãos frios): os pedaços a até 2·grow píxeis
      // se juntam num blob só, e só é PESSOA o blob que tem núcleo de pele (rosto/mãos) — roupa sozinha não conta
      const mGrow = dilate(mWarm, o.grow)
      for (const pxAll of components(mGrow)) {
        const px = pxAll.filter(p => mWarm[p])
        if (px.length < 3) continue
        const b = stats(px, soft, o.hotT)
        b.hotPx = 0; b.corePx = 0
        const coreT = Math.max(amb + o.coreD, o.coreMin)   // núcleo = pele exposta: no quadro cru (um rosto a 3 m tem 1–2 píxeis e a suavização o diluiria)
        for (const p of px) { if (frame[p] >= o.hotT) b.hotPx++; else if (frame[p] >= coreT) b.corePx++ }
        if (b.px >= o.personPx && b.corePx < 1) continue   // vulto morno sem nenhum píxel de pele = roupa/fundo, não pessoa
        if (b.px < o.personPx) {   // blob pequeno só vale com contraste folgado e longe da borda (borda/canto do sensor = ruído)
          const edge = b.x0 === 0 || b.y0 === 0 || b.x1 === W - 1 || b.y1 === H - 1
          if (b.skinMax < warmT + o.smallExtra || (edge && b.px < 8)) continue
        }
        // blob morno que é só o halo de um objeto quente: o objeto já entrou como 'hot'
        if (b.hotPx > 0 && b.skinPx < o.personPx) continue
        if (b.skinMax < warmT) continue
        found.push({ group: 'warm', b })
      }
      for (const d of found) Object.assign(d, this._classify(d.group, d.b, amb))

      // ---- trilhas: casa cada detecção com a trilha mais próxima do mesmo grupo
      for (const t of this.tracks) t.hit = false
      const pairs = []
      found.forEach((d, di) => this.tracks.forEach((t, ti) => {
        if (t.group !== d.group) return
        const dist = Math.hypot(t.cx - d.b.cx, t.cy - d.b.cy), r = Math.max(4, Math.sqrt(Math.max(t.px, d.b.px)))
        if (dist <= r) pairs.push({ di, ti, dist })
      }))
      pairs.sort((a, b) => a.dist - b.dist)
      const usedD = new Set(), usedT = new Set()
      for (const p of pairs) {
        if (usedD.has(p.di) || usedT.has(p.ti)) continue
        usedD.add(p.di); usedT.add(p.ti)
        this._update(this.tracks[p.ti], found[p.di], tSec)
      }
      found.forEach((d, di) => {
        if (usedD.has(di)) return
        const b = d.b
        const t = { id: this.nextId++, group: d.group, age: 0, miss: 0, votes: [], box: [b.x0, b.y0, b.x1, b.y1], born: tSec, stillSince: tSec, ref: { cx: b.cx, cy: b.cy, px: b.px }, hidden: false }
        this.tracks.push(t); this._update(t, d, tSec)
      })
      for (const t of this.tracks) if (!t.hit) t.miss++
      this.tracks = this.tracks.filter(t => t.miss <= o.miss)

      const objects = []
      for (const t of this.tracks) {
        if (t.age < o.confirm || t.hidden) continue
        const K = KINDS[t.kind]
        objects.push({ id: t.id, kind: t.kind, label: K.label, cor: K.cor, detail: t.detail, conf: Math.round(t.conf), temp: t.temp, dist: t.dist,
          x0: t.box[0], y0: t.box[1], x1: t.box[2], y1: t.box[3], cx: t.cx, cy: t.cy, px: t.px, age: tSec - t.born,
          alert: t.group === 'hot' && t.temp >= o.alertT })
      }
      const rank = k => (k.alert ? 0 : k.kind === 'pessoa' ? 1 : k.kind === 'quente' ? 2 : k.kind === 'frio' ? 3 : 4)
      objects.sort((a, b) => rank(a) - rank(b) || b.px - a.px)
      let hottest = -1e9; for (let i = 0; i < N; i++) if (frame[i] > hottest) hottest = frame[i]
      return { amb, objects, people: objects.filter(k => k.kind === 'pessoa' || k.kind === 'pessoa_longe').length, hottest, alert: objects.find(k => k.alert) || null }
    }

    _update (t, d, tSec) {
      const b = d.b, o = this.o
      t.hit = true; t.miss = 0; t.age++
      t.cx = b.cx; t.cy = b.cy; t.px = b.px
      const k = t.age === 1 ? 1 : 0.45   // caixa suavizada: sem tremedeira na tela
      t.box = [t.box[0] + (b.x0 - t.box[0]) * k, t.box[1] + (b.y0 - t.box[1]) * k, t.box[2] + (b.x1 - t.box[2]) * k, t.box[3] + (b.y1 - t.box[3]) * k]
      t.votes.push(d.kind); if (t.votes.length > 8) t.votes.shift()
      const cnt = {}; let best = d.kind, bn = 0
      for (const v of t.votes) { cnt[v] = (cnt[v] || 0) + 1; if (cnt[v] > bn) { bn = cnt[v]; best = v } }
      t.kind = best
      if (best === d.kind) { t.detail = d.detail; t.dist = d.dist; t.conf = t.conf == null ? d.conf : t.conf + (d.conf - t.conf) * 0.3 }
      t.temp = t.temp == null ? d.temp : t.temp + (d.temp - t.temp) * 0.35
      // fundo parado: só blobs pequenos e frios (uma PESSOA parada continua pessoa; um ponto QUENTE nunca é escondido)
      const moved = Math.hypot(b.cx - t.ref.cx, b.cy - t.ref.cy) > 1.5 || Math.abs(b.px - t.ref.px) > 0.35 * Math.max(3, t.ref.px)
      if (moved) { t.ref = { cx: b.cx, cy: b.cy, px: b.px }; t.stillSince = tSec; t.hidden = false }
      else if (tSec - t.stillSince > o.staticSec && (t.group === 'cold' || (t.group === 'warm' && t.kind !== 'pessoa'))) t.hidden = true
    }
  }

  // ------------------------------------------------------------ cena de demonstração
  // Roteiro de 40 s em laço (para testar a tela sem a câmera): visitante chega, mostra um café,
  // outra pessoa passa ao fundo, aparece uma lata gelada e, no fim, um ponto quente em rampa.
  class DemoScene {
    constructor () { this.amb = 24 }
    frame (tSec) {
      const t = tSec % 40, f = new Float32Array(N)
      const blobs = []   // [cx, cy, rx, ry, temp]
      const ease = (a, b, x) => Math.max(0, Math.min(1, (x - a) / (b - a)))
      if (t > 2 && t < 20) {
        const k = ease(2, 6, t) - ease(17, 20, t), cx = 34 - 18 * k + Math.sin(tSec * 1.3) * 0.4
        blobs.push([cx, 15, 4.6, 8, 29.6], [cx, 5.5, 2.3, 2.7, 33.8])
        if (t > 9 && t < 17) blobs.push([cx + 5.5, 12 + Math.sin(tSec * 2) * 0.5, 1.2, 1.4, 61])
      }
      if (t > 19 && t < 31) { const cx = -3 + 40 * ease(19, 31, t); blobs.push([cx, 14, 1.3, 3.2, 28.4], [cx, 9.6, 0.9, 1.0, 30.2]) }
      if (t > 23 && t < 32) blobs.push([9 + Math.sin(tSec) * 0.8, 17, 1.3, 2.0, 12])
      if (t > 32 && t < 39.5) blobs.push([22, 13, 1.5, 1.5, 30 + 75 * ease(32, 37, t)])
      for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
        let v = this.amb + 0.4 * Math.sin(x / 9 + y / 7) + (Math.random() - 0.5) * 0.7
        for (const [cx, cy, rx, ry, temp] of blobs) {
          const d = Math.hypot((x - cx) / rx, (y - cy) / ry)
          const w = d <= 0.75 ? 1 : d >= 1.35 ? 0 : 1 - (d - 0.75) / 0.6   // borda borrada, como a óptica real
          if (w > 0) v = v + (temp - v) * w
        }
        f[y * W + x] = v
      }
      return f
    }
  }

  global.TermicaExpo = { W, H, ExpoAI, DemoScene, KINDS, DEF }
})(typeof window !== 'undefined' ? window : globalThis)
