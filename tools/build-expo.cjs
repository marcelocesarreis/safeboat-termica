// Embute public/expo.html no firmware termica-expo: cola os scripts e a logo dentro do HTML,
// comprime com gzip e gera firmware/termica-expo/expo_page.h.   Uso: node tools/build-expo.cjs
const fs = require('fs'), path = require('path'), zlib = require('zlib')
const PUB = path.join(__dirname, '..', 'public')
let html = fs.readFileSync(path.join(PUB, 'expo.html'), 'utf8')
html = html.replace(/<!--[\s\S]*?-->/g, '')
html = html.replace(/<script src="([^"]+)"><\/script>/g, (m, src) => '<script>' + fs.readFileSync(path.join(PUB, src), 'utf8').replace(/<\/script/gi, '<\/script') + '</script>')
html = html.replace(/src="(img\/[^"]+\.png)"/g, (m, src) => 'src="data:image/png;base64,' + fs.readFileSync(path.join(PUB, src)).toString('base64') + '"')
if (/<script src=|src="img\//.test(html)) throw new Error('sobrou referência externa: a página tem de ser um arquivo só')
const gz = zlib.gzipSync(Buffer.from(html, 'utf8'), { level: 9 })
const rows = []
for (let i = 0; i < gz.length; i += 24) rows.push('  ' + [...gz.subarray(i, i + 24)].map(b => '0x' + b.toString(16).padStart(2, '0')).join(','))
const out = `// GERADO por tools/build-expo.cjs a partir de public/expo.html — não edite à mão.\n#pragma once\n#include <pgmspace.h>\nstatic const unsigned int EXPO_PAGE_GZ_LEN = ${gz.length};\nstatic const unsigned char EXPO_PAGE_GZ[] PROGMEM = {\n${rows.join(',\n')}\n};\n`
fs.writeFileSync(path.join(__dirname, '..', 'firmware', 'termica-expo', 'expo_page.h'), out)
console.log(`expo_page.h: ${html.length} B de HTML → ${gz.length} B gzip`)
