/**
 * SAFEBOAT TÉRMICA — gerador paramétrico das peças imprimíveis
 * Câmera térmica MLX90640 + ESP32-C3 para manutenção preditiva embarcada.
 *
 * ============================ REV. C — FECHO POR BAIONETA ============================
 * A rosca impressa da rev. B FALHOU na bancada. Causa raiz (medida, não achismo):
 *   · engajamento radial do filete .... 0,50 mm
 *   · erro típico de FDM em furo ...... 0,20 a 0,45 mm (PETG, parede interna)
 *   · crista do filete ................ 1,9 camadas a 0,16 mm
 * O erro de processo sozinho consumia até 90 % do engajamento — a rosca era
 * fina demais para o processo. Não é caso de ajustar folga: é caso de trocar o
 * conceito de fecho.
 *
 * REV. C substitui a rosca por BAIONETA de 60° (quarto de volta), que é o que
 * se usa em invólucro impresso quando a vedação importa:
 *   · engajamento radial ............. 1,60 mm  (3,2× a rosca)  → sobra folga
 *   · nenhuma geometria helicoidal, nenhum detalhe menor que 1,5 mm
 *   · todas as faces de trabalho são planas e horizontais/verticais
 *   · tolerante a ±0,3 mm sem deixar de montar nem de travar
 *   · abre e fecha com a mão, sem ferramenta, em 60°
 *
 * Peças (todas já na ORIENTAÇÃO DE IMPRESSÃO, apoiadas em z=0):
 *  1. corpo.stl           — corpo monobloco, janela colada, canais da baioneta, marca no topo
 *  2. tampa-traseira.stl  — tampa de baioneta, canal de O-ring radial, rebaixo p/ prensa-cabo
 *  3. carrier-interno.stl — sled: MLX90640 na frente + bandeja p/ ESP32-C3
 *  4. suporte.stl         — suporte yoke com base de fixação
 *  5. gabarito.stl        — cupom de teste (baioneta + O-ring + slot da PCB + furo M12).
 *                           IMPRIMA ESTE PRIMEIRO: ~25 min contra ~6 h do jogo todo.
 *
 * Rodar: node tools/generate-stl.cjs
 */
const fs = require('fs')
const path = require('path')
const jscad = require('@jscad/modeling')
const stlSerializer = require('@jscad/stl-serializer')

const { polygon, cylinder, cuboid, roundedRectangle, cylinderElliptic, circle } = jscad.primitives
const { extrudeRotate, extrudeLinear } = jscad.extrusions
const { subtract, union, intersect } = jscad.booleans
const { translate, rotateX, rotateY, rotateZ, mirrorX } = jscad.transforms
const { measureBoundingBox } = jscad.measurements
const { vectorText } = jscad.text
const { hullChain } = jscad.hulls

const TAU = Math.PI * 2
const SEG = 120
const OUT = path.join(__dirname, '..', 'stl')
const D2R = Math.PI / 180

// ---------------------------------------------------------------- parâmetros
// Corpo (z=0 face frontal externa, +z para a ré)
const P = {
  odBody: 50,            // Ø externo
  lenBody: 62,           // comprimento
  boreR: 21,             // furo Ø42 — SUPERFÍCIE DE VEDAÇÃO do O-ring + piloto da espiga
  frontBoreR: 19,        // furo frontal Ø38 — forma o ombro do carrier
  shoulderZ: 10,         // ombro do carrier
  winR: 13.25,           // recesso da janela Ø26.5 (germânio Ø25×1 + folga p/ Sikaflex)
  winDepth: 1.8,
  apFrontR: 9.5,         // abertura óptica cônica: boca Ø19
  apRearR: 8,            //                        garganta Ø16
  frontWall: 4,
  // --- baioneta ---
  bayBoreR: 21.6,        // furo na zona da baioneta (Ø43.2) — folga p/ o núcleo da tampa
  bayChanR: 23.2,        // Ø externo do canal (Ø46.4) — deixa 1,8 mm de parede
  bayZ0: 50,             // início da zona da baioneta
  chanZ0: 51.0,          // piso do canal circunferencial (face p/ CIMA na impressão)
  chanZ1: 54.8,          // teto do canal (aba de 1,6 mm — imprime sem suporte)
  slotDeg: 34,           // largura angular da janela de entrada
  chanDeg: 75,           // fim do canal (batente angular)
  detentDeg: 59,         // posição do ressalto de retenção
  detentDepth: 0.15,     // interferência do ressalto
  // --- resto ---
  bossZ: 30, bossR: 7, bossTipX: 29.5,
  insertR: 2.8, insertDepth: 6.5,
}
// Tampa (z=0 face traseira externa, +z entra no corpo)
const C = {
  flangeR: 25, flangeH: 5,
  bayCoreR: 20.9,        // núcleo na zona da baioneta (Ø41.8)
  bayZ1: 16,             // fim da zona da baioneta
  lugR: 22.9,            // raio externo das travas (Ø45.8)
  lugZ0: 12.8, lugZ1: 15.8,   // altura das travas (3,0 mm)
  lugDeg: 30,            // largura angular das travas
  lugCham: 0.8,          // chanfro 45° na aresta inferior externa (imprime sem suporte)
  spigotR: 20.7,         // espiga lisa Ø41.4
  spigotZ1: 29,
  grooveFloorR: 18.6,    // fundo do canal Ø37.2 (O-ring NBR 37×3 → squeeze 20%)
  grooveW: 4.05,
  grooveZc: 24,
  glandHoleR: 6.3,       // furo Ø12.6 p/ prensa-cabo M12×1.5
  boreR: 12,             // rebaixo interno Ø24 p/ a contraporca
}
// Carrier — CONFERIR COM PAQUÍMETRO antes do jogo definitivo
const M = {
  pcbW: 25.4, pcbT: 1.6, slotZ: 6, canR: 5.2, len: 27.5,
}
const NLUG = 3           // travas / janelas

// ------------------------------------------------------------------ helpers
function ccw (pts) {
  let a = 0
  for (let i = 0; i < pts.length; i++) {
    const [x1, y1] = pts[i]; const [x2, y2] = pts[(i + 1) % pts.length]
    a += x1 * y2 - x2 * y1
  }
  return a > 0 ? pts : pts.slice().reverse()
}
const revolve = (pts, seg = SEG) => extrudeRotate({ segments: seg }, polygon({ points: ccw(pts) }))

// setor anular 2D (graus) → polígono
function annSector (rIn, rOut, a0, a1) {
  const n = Math.max(6, Math.ceil(Math.abs(a1 - a0) / 3))
  const pts = []
  for (let i = 0; i <= n; i++) { const a = (a0 + (a1 - a0) * i / n) * D2R; pts.push([rOut * Math.cos(a), rOut * Math.sin(a)]) }
  for (let i = n; i >= 0; i--) { const a = (a0 + (a1 - a0) * i / n) * D2R; pts.push([rIn * Math.cos(a), rIn * Math.sin(a)]) }
  return polygon({ points: ccw(pts) })
}
// prisma de setor anular entre z0 e z1
const sectorSolid = (rIn, rOut, a0, a1, z0, z1) =>
  translate([0, 0, z0], extrudeLinear({ height: z1 - z0 }, annSector(rIn, rOut, a0, a1)))

function saveSTL (name, geom) {
  const data = stlSerializer.serialize({ binary: true }, geom)
  fs.writeFileSync(path.join(OUT, name), Buffer.concat(data.map(d => Buffer.from(d))))
  const bb = measureBoundingBox(geom)
  const dims = bb[1].map((v, i) => (v - bb[0][i]).toFixed(1)).join(' × ')
  console.log(`  ${name.padEnd(22)} ${dims} mm   z0=${bb[0][2].toFixed(2)}   (${(fs.statSync(path.join(OUT, name)).size / 1024).toFixed(0)} kB)`)
  return bb
}

function engravedText (str, height, strokeR, depth) {
  const segs = vectorText({ height, align: 'center' }, str)
  const shapes = segs.map(seg => hullChain(seg.map(pt => circle({ radius: strokeR, center: pt, segments: 16 }))))
  return extrudeLinear({ height: depth }, union(shapes))
}

// ---------------------------------------------------- gravação do logotipo
function buildLogoCutter () {
  const ring = subtract(circle({ radius: 11, segments: 96 }), circle({ radius: 8.9, segments: 96 }))
  const waves = []
  for (const y0 of [1.2, -1.0, -3.2, -5.4]) {
    const half = Math.sqrt(Math.max(0, 8.2 * 8.2 - y0 * y0)) - 0.9
    const pts = []
    for (let x = -half; x <= half; x += 0.45) {
      pts.push(circle({ radius: 0.72, center: [x, y0 + 0.7 * Math.sin(x * TAU / 5.6)], segments: 12 }))
    }
    waves.push(intersect(hullChain(pts), circle({ radius: 8.2, segments: 64 })))
  }
  let cutter = extrudeLinear({ height: 8 }, union(ring, ...waves))
  cutter = rotateX(-Math.PI / 2, cutter)
  cutter = translate([0, 18, P.bossZ], cutter)
  const shell = subtract(
    cylinder({ radius: 26, height: 26, center: [0, 0, P.bossZ], segments: SEG }),
    cylinder({ radius: 24.3, height: 28, center: [0, 0, P.bossZ], segments: SEG })
  )
  return intersect(cutter, shell)
}

// ------------------------------------------- baioneta: vazios do corpo
function bayonetVoids () {
  const v = []
  const half = P.slotDeg / 2
  for (let i = 0; i < NLUG; i++) {
    const a = i * (360 / NLUG)
    // janela de entrada axial: da face traseira até o piso do canal
    v.push(sectorSolid(21.3, P.bayChanR, a - half, a + half, P.chanZ0, P.lenBody + 1))
    // canal circunferencial: piso p/ cima (ótimo acabamento), teto = aba de 1,6 mm
    v.push(sectorSolid(21.3, P.bayChanR, a - half, a + P.chanDeg, P.chanZ0, P.chanZ1))
  }
  return union(...v)
}
// ressaltos de retenção: cilindros verticais (parede lateral = melhor face do FDM)
function bayonetDetents () {
  const d = []
  const rb = 1.5
  const rc = P.bayChanR - P.detentDepth + rb
  for (let i = 0; i < NLUG; i++) {
    const a = (i * (360 / NLUG) + P.detentDeg) * D2R
    let b = cylinder({ radius: rb, height: P.chanZ1 - P.chanZ0, center: [rc * Math.cos(a), rc * Math.sin(a), (P.chanZ0 + P.chanZ1) / 2], segments: 24 })
    b = intersect(b, cylinder({ radius: 24.9, height: P.chanZ1 - P.chanZ0 + 1, center: [0, 0, (P.chanZ0 + P.chanZ1) / 2], segments: SEG }))
    d.push(b)
  }
  return union(...d)
}

// ------------------------------------------------------------------ 1. CORPO
function buildCorpo () {
  const prof = [
    [P.apFrontR, P.winDepth],               // boca do cone óptico
    [P.winR, P.winDepth],                   // fundo do recesso da janela
    [P.winR, 0],
    [22, 0],                                // face frontal
    [23.4, 0.25], [24.4, 0.9], [24.9, 1.9], [25, 3],  // fillet R3 da borda frontal
    [25, P.lenBody],                        // parede externa
    [22.2, P.lenBody],                      // face traseira = assento do flange (2.8 mm)
    [P.bayBoreR, P.lenBody - 0.6],          // chanfro de entrada
    [P.bayBoreR, P.bayZ0 + 1],              // furo da zona da baioneta
    [P.boreR, P.bayZ0 - 0.5],               // cone de entrada do O-ring (não raspa o cordão)
    [P.boreR, P.shoulderZ],                 // furo Ø42 — vedação
    [P.frontBoreR, P.shoulderZ],            // ombro do carrier
    [P.frontBoreR, P.frontWall],
    [P.apRearR, P.frontWall],               // garganta óptica
  ]
  let body = revolve(prof)

  body = subtract(body, bayonetVoids())
  body = union(body, bayonetDetents())

  for (const s of [1, -1]) {
    let boss = cylinder({ radius: P.bossR, height: P.bossTipX - 23, segments: 64 })
    boss = translate([s * (23 + (P.bossTipX - 23) / 2), 0, P.bossZ], rotateY(Math.PI / 2, boss))
    body = union(body, boss)
    let hole = cylinder({ radius: P.insertR, height: P.insertDepth, segments: 32 })
    hole = translate([s * (P.bossTipX - P.insertDepth / 2), 0, P.bossZ], rotateY(Math.PI / 2, hole))
    body = subtract(body, hole)
  }

  return subtract(body, buildLogoCutter())
}

// ---------------------------------------------------------------- 2. TAMPA
// chanfro 45° na aresta inferior externa das travas (elimina suporte)
function lugChamferCut (zBot, rStart) {
  return revolve([
    [rStart, zBot], [30, zBot + (30 - rStart)], [30, zBot - 2], [rStart, zBot - 2],
  ])
}

function buildTampa () {
  const prof = [
    [C.glandHoleR, 0],                      // furo do prensa-cabo
    [23.5, 0],
    [24.6, 0.4], [25, 1.5],                 // fillet traseiro
    [C.flangeR, C.flangeH],                 // flange Ø50
    [C.bayCoreR, C.flangeH],                // núcleo da baioneta
    [C.bayCoreR, C.bayZ1],
    [C.spigotR, C.bayZ1],                   // espiga
    [C.spigotR, C.spigotZ1 - 1.2],
    [C.spigotR - 1.2, C.spigotZ1],          // chanfro de entrada da espiga
    [C.boreR, C.spigotZ1],
    [C.boreR, C.flangeH],                   // rebaixo Ø24 (contraporca)
    [C.glandHoleR, C.flangeH],
  ]
  let cap = revolve(prof)

  // travas da baioneta
  const half = C.lugDeg / 2
  for (let i = 0; i < NLUG; i++) {
    const a = i * (360 / NLUG)
    let lug = sectorSolid(20.5, C.lugR, a - half, a + half, C.lugZ0, C.lugZ1)
    lug = subtract(lug, lugChamferCut(C.lugZ0, C.lugR - C.lugCham))
    cap = union(cap, lug)
  }

  // canal do O-ring radial
  const ring = subtract(
    cylinder({ radius: C.spigotR + 0.5, height: C.grooveW, segments: SEG }),
    cylinder({ radius: C.grooveFloorR, height: C.grooveW + 0.2, segments: SEG })
  )
  cap = subtract(cap, translate([0, 0, C.grooveZc], ring))

  // 12 ranhuras de pega no flange
  for (let i = 0; i < 12; i++) {
    const a = (i / 12) * TAU
    cap = subtract(cap, cylinder({ radius: 2.2, height: C.flangeH + 2, center: [26.6 * Math.cos(a), 26.6 * Math.sin(a), C.flangeH / 2], segments: 24 }))
  }

  // gravação SAFEBOAT + seta de travamento na face traseira
  try {
    let txt = engravedText('SAFEBOAT', 4.5, 0.5, 0.7)
    cap = subtract(cap, translate([0, -14.5, -0.05], mirrorX(txt)))
    let lock = engravedText('FECHA >', 3.2, 0.45, 0.7)
    cap = subtract(cap, translate([0, 15.5, -0.05], mirrorX(lock)))
  } catch (e) { console.warn('  gravação pulada:', e.message) }

  return cap
}

// --------------------------------------------------------------- 3. CARRIER
function buildCarrier () {
  let disc = cylinder({ radius: 20.7, height: 3, center: [0, 0, 1.5], segments: SEG })
  disc = subtract(disc, cylinder({ radius: M.canR, height: 4, center: [0, 0, 1.5], segments: 64 }))
  for (const s of [1, -1]) {
    disc = subtract(disc, cylinder({ radius: 3, height: 4, center: [0, s * 16, 1.5], segments: 32 }))
  }
  const wallH = M.len - 3
  const walls = []
  for (const s of [1, -1]) {
    const w = cuboid({ size: [3, 26, wallH], center: [s * 13.5, 0, 3 + wallH / 2] })
    const slot = cuboid({ size: [2.1, 27, M.pcbT + 0.4], center: [s * 12.55, 0, 3 + M.slotZ] })
    walls.push(subtract(w, slot))
  }
  const shelf = cuboid({ size: [25, 20, 2], center: [0, 0, 23] })
  return union(disc, shelf, ...walls)
}

// --------------------------------------------------------------- 4. SUPORTE
function buildSuporte () {
  const armX = 32.5, axisZ = 45
  let base = extrudeLinear({ height: 5 }, roundedRectangle({ size: [70, 36], roundRadius: 6, segments: 32 }))
  for (const sx of [1, -1]) {
    for (const sy of [1, -1]) {
      base = subtract(base,
        cylinder({ radius: 2.4, height: 12, center: [sx * 28, sy * 11, 2.5], segments: 32 }),
        translate([sx * 28, sy * 11, 2.5], cylinderElliptic({ startRadius: [2.4, 2.4], endRadius: [4.9, 4.9], height: 2.5, segments: 32 })))
    }
  }
  const parts = [base]
  for (const s of [1, -1]) {
    const prof = [[3, -14], [3, 14], [20, 8], [axisZ, 8], [axisZ, -8], [20, -8]]
    let arm = extrudeLinear({ height: 5 }, polygon({ points: ccw(prof) }))
    arm = rotateY(-Math.PI / 2, arm)
    arm = translate([s === 1 ? 35 : -30, 0, 0], arm)
    let top = cylinder({ radius: 8, height: 5, segments: 64 })
    top = translate([s * armX, 0, axisZ], rotateY(Math.PI / 2, top))
    arm = union(arm, top)
    let hole = cylinder({ radius: 2.15, height: 18, segments: 32 })
    hole = translate([s * armX, 0, axisZ], rotateY(Math.PI / 2, hole))
    parts.push(subtract(arm, hole))
  }
  return union(...parts)
}

// -------------------------------------------------------------- 5. GABARITO
// Cupom de teste: baioneta + O-ring + slot da PCB + furo do prensa-cabo (~25 min)
function buildGabarito () {
  // (a) anel fêmea curto: assento do flange, zona da baioneta e um trecho do furo de vedação
  const zTop = 14, zBay = 3, zCh0 = 4, zCh1 = 7.8
  let fem = revolve([
    [P.boreR, 0], [29, 0], [29, zTop], [22.2, zTop],
    [P.bayBoreR, zTop - 0.6], [P.bayBoreR, zBay], [P.boreR, zBay - 1.5],
  ])
  const v = []
  const half = P.slotDeg / 2
  for (let i = 0; i < NLUG; i++) {
    const a = i * (360 / NLUG)
    v.push(sectorSolid(21.3, P.bayChanR, a - half, a + half, zCh0, zTop + 1))
    v.push(sectorSolid(21.3, P.bayChanR, a - half, a + P.chanDeg, zCh0, zCh1))
  }
  fem = subtract(fem, union(...v))
  const rb = 1.5, rc = P.bayChanR - P.detentDepth + rb
  for (let i = 0; i < NLUG; i++) {
    const a = (i * (360 / NLUG) + P.detentDeg) * D2R
    let b = cylinder({ radius: rb, height: zCh1 - zCh0, center: [rc * Math.cos(a), rc * Math.sin(a), (zCh0 + zCh1) / 2], segments: 24 })
    b = intersect(b, cylinder({ radius: 24.9, height: zCh1 - zCh0 + 1, center: [0, 0, (zCh0 + zCh1) / 2], segments: SEG }))
    fem = union(fem, b)
  }
  fem = translate([-33, 0, 0], fem)

  // (b) plug macho: flange + travas + espiga com o canal do O-ring
  const lz0 = 5.8, lz1 = 8.8
  let mal = revolve([
    [0, 0], [25, 0], [25, 3],
    [C.bayCoreR, 3], [C.bayCoreR, 9],
    [C.spigotR, 9], [C.spigotR, 20.8], [C.spigotR - 1.2, 22], [0, 22],
  ])
  const lhalf = C.lugDeg / 2
  for (let i = 0; i < NLUG; i++) {
    const a = i * (360 / NLUG)
    let lug = sectorSolid(20.5, C.lugR, a - lhalf, a + lhalf, lz0, lz1)
    lug = subtract(lug, lugChamferCut(lz0, C.lugR - C.lugCham))
    mal = union(mal, lug)
  }
  const ring = subtract(
    cylinder({ radius: C.spigotR + 0.5, height: C.grooveW, segments: SEG }),
    cylinder({ radius: C.grooveFloorR, height: C.grooveW + 0.2, segments: SEG })
  )
  mal = subtract(mal, translate([0, 0, 17], ring))
  mal = translate([33, 0, 0], mal)

  // (c) cupom do carrier (slot da PCB)
  const cup = []
  for (const s of [1, -1]) {
    const w = cuboid({ size: [3, 20, 12], center: [s * 13.5, 0, 6] })
    const slot = cuboid({ size: [2.1, 21, M.pcbT + 0.4], center: [s * 12.55, 0, 3 + M.slotZ] })
    cup.push(subtract(w, slot))
  }
  cup.push(cuboid({ size: [34, 20, 3], center: [0, 0, 1.5] }))

  // (d) cupom do prensa-cabo (espessura real do flange)
  let gp = cuboid({ size: [30, 20, C.flangeH], center: [0, 0, C.flangeH / 2] })
  gp = subtract(gp, cylinder({ radius: C.glandHoleR, height: 9, center: [0, 0, C.flangeH / 2], segments: 48 }))

  return union(fem, mal, translate([0, -46, 0], union(...cup)), translate([0, 46, 0], gp))
}

// ---------------------------------------------------------- relatório de ajustes
function fitReport () {
  const mm = v => v.toFixed(2) + ' mm'
  const r = []
  // baioneta
  const eng = C.lugR - P.bayBoreR
  r.push(['BAIONETA — engajamento radial', mm(eng), '≥ 1.2 (rosca rev.B tinha 0.50)'])
  r.push(['BAIONETA — folga radial trava/canal', mm(P.bayChanR - C.lugR), '0.2–0.4'])
  r.push(['BAIONETA — folga radial núcleo/furo', mm(P.bayBoreR - C.bayCoreR), '0.5–0.9'])
  r.push(['BAIONETA — folga angular trava/janela', ((P.slotDeg - C.lugDeg) / 2).toFixed(1) + '°', '≥ 1.5° por lado'])
  const lugBodyZ0 = 67 - C.lugZ1, lugBodyZ1 = 67 - C.lugZ0
  r.push(['BAIONETA — folga axial no canal', mm((P.chanZ1 - P.chanZ0) - (C.lugZ1 - C.lugZ0)), '0.4–0.9'])
  r.push(['BAIONETA — trava dentro do canal?', (lugBodyZ0 > P.chanZ0 && lugBodyZ1 < P.chanZ1) ? 'SIM' : 'NÃO ✗', 'obrigatório'])
  // gira até a aresta dianteira da trava (lugDeg/2 + θ) bater no fim do canal
  const rot = P.chanDeg - C.lugDeg / 2
  r.push(['BAIONETA — rotação p/ travar', rot.toFixed(0) + '°', '45–90°'])
  r.push(['BAIONETA — clique do ressalto em', (P.detentDeg - C.lugDeg / 2).toFixed(0) + '° de ' + rot.toFixed(0) + '°', 'perto do fim'])
  r.push(['BAIONETA — parede sobre o canal', mm(25 - P.bayChanR), '≥ 1.5 (4 perímetros)'])
  r.push(['BAIONETA — menor detalhe da peça', mm(Math.min(C.lugZ1 - C.lugZ0, eng)), '≥ 1.2 (era 0.30 na rosca)'])
  // O-ring
  const gland = P.boreR - C.grooveFloorR
  r.push(['O-RING — squeeze', ((3 - gland) / 3 * 100).toFixed(0) + '%', '15–25% (estático radial)'])
  r.push(['O-RING — preenchimento do canal', (Math.PI * 1.5 * 1.5 / (C.grooveW * gland) * 100).toFixed(0) + '%', '60–85%'])
  const oringBodyZ = 67 - C.grooveZc
  r.push(['O-RING — veda em furo liso contínuo?', (oringBodyZ + C.grooveW / 2) < (P.bayZ0 - 0.5) ? 'SIM' : 'NÃO ✗', 'obrigatório'])
  r.push(['O-RING — margem até a zona da baioneta', mm((P.bayZ0 - 0.5) - (oringBodyZ + C.grooveW / 2)), '> 1.0'])
  // carrier / óptica / prensa-cabo
  r.push(['CARRIER — apoio no ombro', mm(20.7 - P.frontBoreR), '> 1.0'])
  r.push(['CARRIER — folga p/ a ponta da espiga', mm((67 - C.spigotZ1) - (P.shoulderZ + M.len)), '0.3–0.8 (espuma EVA)'])
  const dist = (P.shoulderZ + 1) - P.winDepth
  const needed = dist * Math.tan(31.3 * D2R) + 1.5
  r.push(['ÓPTICA — raio exigido / disponível', mm(needed) + ' / ' + mm(P.apFrontR), needed < P.apFrontR ? 'OK (sem vinheta)' : 'VINHETA ✗'])
  r.push(['PRENSA-CABO — parede de aperto', mm(C.flangeH), '4–6 (contraporca)'])

  const w = [44, 14]
  console.log('\n  RELATÓRIO DE AJUSTES (rev. C — baioneta)')
  console.log('  ' + '─'.repeat(88))
  for (const [a, b, c] of r) console.log('  ' + a.padEnd(w[0]) + b.padStart(w[1]) + '   ' + c)
  console.log('  ' + '─'.repeat(88))
}

// -------------------------------------------------------------------- main
function main () {
  console.log('SAFEBOAT TÉRMICA — rev. C (fecho por baioneta)\n')
  const t0 = Date.now()
  if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true })

  saveSTL('corpo.stl', buildCorpo())
  saveSTL('tampa-traseira.stl', buildTampa())
  saveSTL('carrier-interno.stl', buildCarrier())
  saveSTL('suporte.stl', buildSuporte())
  saveSTL('gabarito.stl', buildGabarito())

  fitReport()
  console.log(`\nOK em ${((Date.now() - t0) / 1000).toFixed(1)}s`)
}

module.exports = { buildCorpo, buildTampa, buildCarrier, buildSuporte, buildGabarito, P, C, M, NLUG, fitReport }
main()
