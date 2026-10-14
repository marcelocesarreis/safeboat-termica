// Modelos 3D (VRML 2.0) dos footprints próprios da TERMICA v1, gerados com JSCAD:
//   lib/3d/MLX90640_TO-39-110.wrl  — sensor TO-39 versão 110° (lata Ø9,30 × 5,70 + flange Ø10,03, aba, 4 pinos Ø0,45)
//   lib/3d/KF350-3.5-2P.wrl        — borne parafuso 3,5 mm 2 vias (corpo 7,0 × 7,4 × 7,3)
// Eixos do modelo no KiCad: x = x do footprint, y = −y do footprint (y do KiCad aponta p/ baixo), z p/ cima;
// unidade do VRML no KiCad = 0,1" (2,54 mm) → coordenadas divididas por 2,54.
//   node make_3d_models.cjs
const path = require('path')
const fs = require('fs')
const jscad = require(path.join(__dirname, '..', '..', 'node_modules', '@jscad', 'modeling'))
const { cylinder, cuboid, cylinderElliptic } = jscad.primitives
const { subtract, union } = jscad.booleans
const { translate } = jscad.transforms
const { geom3 } = jscad.geometries

const OUT = path.join(__dirname, 'lib', '3d')
fs.mkdirSync(OUT, { recursive: true })

function vrml (shapes) {
  // shapes = [{ geom, color: [r,g,b] }]
  let s = '#VRML V2.0 utf8\n# SAFEBOAT TERMICA v1 — gerado por hardware/pcb/make_3d_models.cjs\n'
  for (const { geom, color } of shapes) {
    const polys = geom3.toPolygons(geom)
    const pts = []; const idx = []
    for (const p of polys) {
      const base = pts.length
      for (const v of p.vertices) pts.push(v)
      idx.push([...Array(p.vertices.length).keys()].map(k => base + k).join(' ') + ' -1')
    }
    s += 'Shape {\n appearance Appearance { material Material { diffuseColor ' + color.map(c => c.toFixed(3)).join(' ') +
         ' specularColor 0.3 0.3 0.3 shininess 0.4 } }\n geometry IndexedFaceSet {\n  solid FALSE\n  coord Coordinate { point [\n'
    s += pts.map(v => v.map(c => (c / 2.54).toFixed(4)).join(' ')).join(',\n') + '\n  ] }\n  coordIndex [\n' + idx.join(',\n') + '\n  ]\n }\n}\n'
  }
  return s
}

// ------------------------------------------------------------ MLX90640 TO-39 (110°)
const q = 5.84 / 2 * Math.cos(Math.PI / 4)        // 2,065 — pinos em círculo Ø5,84 a 45°
const canR = 4.65, canH = 5.7, flangeR = 5.015, flangeH = 0.1
let flange = cylinder({ radius: flangeR, height: flangeH, center: [0, 0, flangeH / 2], segments: 64 })
// aba (0,8 × 0,8) na borda do flange, em +y do footprint = −y do modelo
flange = union(flange, cuboid({ size: [0.8, 0.9, flangeH], center: [0, -(flangeR + 0.35), flangeH / 2] }))
let can = cylinder({ radius: canR, height: canH - 0.5, center: [0, 0, flangeH + (canH - 0.5) / 2], segments: 64 })
can = union(can, translate([0, 0, flangeH + canH - 0.5], cylinderElliptic({ startRadius: [canR, canR], endRadius: [canR - 0.5, canR - 0.5], height: 0.5, segments: 64 })))
const aperture = cylinder({ radius: 1.3, height: 0.3, center: [0, 0, flangeH + canH - 0.1], segments: 32 })
can = subtract(can, aperture)
const filter = cylinder({ radius: 1.3, height: 0.1, center: [0, 0, flangeH + canH - 0.25], segments: 32 })
const pinL = 2.6   // 1,6 da placa + 1,0 (pino cortado depois da solda)
const pins = [[q, q], [q, -q], [-q, -q], [-q, q]].map(([x, y]) => cylinder({ radius: 0.225, height: pinL, center: [x, -y, -pinL / 2], segments: 16 }))
fs.writeFileSync(path.join(OUT, 'MLX90640_TO-39-110.wrl'), vrml([
  { geom: flange, color: [0.85, 0.70, 0.30] },
  { geom: can, color: [0.22, 0.08, 0.12] },
  { geom: filter, color: [0.55, 0.55, 0.60] },
  { geom: union(...pins), color: [0.85, 0.70, 0.30] },
]))

// ------------------------------------------------------------ KF350-3.5-2P
const bw = 7.0, bd = 7.4, bh = 7.3
let body = cuboid({ size: [bw, bd, bh], center: [0, 0, bh / 2] })
for (const x of [-1.75, 1.75]) {
  body = subtract(body, cylinder({ radius: 1.3, height: 3, center: [x, -0.6, bh - 1.0], segments: 32 }))       // acesso do parafuso (topo)
  body = subtract(body, translate([x, -bd / 2 + 1.0, 2.6], cuboid({ size: [2.6, 2.2, 2.6] })))                 // entrada do fio (face −y)
}
const screws = [-1.75, 1.75].map(x => cylinder({ radius: 1.1, height: 0.4, center: [x, -0.6, bh - 2.3], segments: 32 }))
const tpins = [-1.75, 1.75].map(x => cuboid({ size: [1.0, 1.0, 2.6], center: [x, 0, -1.3] }))
fs.writeFileSync(path.join(OUT, 'KF350-3.5-2P.wrl'), vrml([
  { geom: body, color: [0.10, 0.45, 0.25] },
  { geom: union(...screws), color: [0.75, 0.75, 0.78] },
  { geom: union(...tpins), color: [0.80, 0.80, 0.82] },
]))
console.log('modelos gravados em', OUT, fs.readdirSync(OUT).map(f => f + ' ' + fs.statSync(path.join(OUT, f)).size + ' B').join(' | '))
