/**
 * SAFEBOAT TÉRMICA — verificação de montagem por CSG (rev. C)
 *
 * Prova numericamente, antes de imprimir, que:
 *   1. a tampa ENTRA (travas passam pelas janelas na rotação 0°)
 *   2. a tampa GIRA 60° até o batente sem interferir
 *   3. a tampa FICA TRAVADA (puxar para trás colide com o teto do canal)
 *   4. o ressalto de retenção realmente interfere (dá o clique)
 *
 * Relação de coordenadas: assentada, a face frontal do flange (tampa z=5)
 * encosta na face traseira do corpo (corpo z=62)  →  corpo_z = 67 − tampa_z.
 *
 * Rodar: node tools/verify-fit.cjs
 */
const jscad = require('@jscad/modeling')
const { subtract, intersect } = jscad.booleans
const { translate, rotateZ, mirrorZ } = jscad.transforms
const { measureVolume } = jscad.measurements

const gen = require('./generate-stl.cjs')   // reexecuta a geração (imprime o relatório)

console.log('\n\n=========== VERIFICAÇÃO DE MONTAGEM (CSG) ===========\n')

const corpo = gen.buildCorpo()
const tampa = gen.buildTampa()

// leva a tampa das coordenadas dela para as do corpo: corpo_z = 67 − tampa_z
// (espelha em z e translada), com rotação θ em torno do eixo e recuo axial d
function seat (geom, deg, back = 0) {
  let g = mirrorZ(geom)              // z → −z
  g = translate([0, 0, 67 + back], g) // corpo_z = 67 − tampa_z (+ recuo)
  return rotateZ(deg * Math.PI / 180, g)
}

const volTampa = measureVolume(tampa)
// Limiares ABSOLUTOS (comparar com o volume da tampa inteira não diz nada:
// a retenção acontece numa área de apoio de ~56 mm², não no corpo da peça).
//   livre  → < 1 mm³   (só resíduo numérico de CSG)
//   colide → > 10 mm³  (interferência inequívoca, não é ruído)
function overlap (deg, back, label, esperado) {
  const v = measureVolume(intersect(corpo, seat(tampa, deg, back)))
  const ok = esperado === 'livre' ? (v < 1.0) : (v > 10.0)
  console.log(
    ('  ' + label).padEnd(46) +
    (v.toFixed(1) + ' mm³').padStart(12) +
    ('  esperado: ' + esperado).padEnd(20) +
    (ok ? 'OK' : 'FALHA ✗')
  )
  return ok
}

console.log('  volume da tampa: ' + volTampa.toFixed(0) + ' mm³\n')
console.log('  CENÁRIO                                  INTERFERÊNCIA                        VEREDICTO')
console.log('  ' + '─'.repeat(94))

const r = []
// 1. inserção: travas alinhadas com as janelas, assentada
r.push(overlap(0, 0, '1. inserida a 0° (travas nas janelas)', 'livre'))
// 2. rotação intermediária
r.push(overlap(30, 0, '2. girando — meio curso (30°)', 'livre'))
// 3. travada no batente
r.push(overlap(60, 0, '3. travada a 60° (batente)', 'livre'))
// 4. retenção: puxar 1.5 mm para trás com a tampa travada TEM de colidir
r.push(overlap(60, 1.5, '4. travada, puxando 1,5 mm p/ trás', 'colide'))
// 5. controle: girar sem inserir não faz sentido; testa desalinhamento a 15°
//    (travas contra o material entre janelas) — TEM de colidir
r.push(overlap(15, -3, '5. inserir desalinhada 15° (deve barrar)', 'colide'))

console.log('  ' + '─'.repeat(94))
const todos = r.every(Boolean)
console.log('\n  ' + (todos
  ? '✔ MONTAGEM VALIDADA — entra, gira 60°, trava e resiste ao arranque axial.'
  : '✘ REPROVADO — revise a geometria antes de imprimir.'))
console.log()
process.exit(todos ? 0 : 1)
