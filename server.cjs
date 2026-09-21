// SAFEBOAT TÉRMICA — servidor estático da página do projeto (porta 8097)
const http = require('http')
const fs = require('fs')
const path = require('path')
const os = require('os')

const PORT = 8097
const ROOT = __dirname
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.stl': 'model/stl',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.json': 'application/json',
  '.md': 'text/markdown; charset=utf-8',
  '.ino': 'text/plain; charset=utf-8',
  '.zip': 'application/zip',
}

const ingest = []   // últimos batimentos recebidos (memória)

http.createServer((req, res) => {
  let url = decodeURIComponent(req.url.split('?')[0])
  // endpoint de depuração: salva um PNG enviado pelo navegador (verificação do viewer 3D)
  if (req.method === 'POST' && url === '/__save') {
    const chunks = []
    req.on('data', c => chunks.push(c))
    req.on('end', () => {
      const out = path.join(ROOT, 'tmp-viewer-shot.png')
      fs.writeFileSync(out, Buffer.concat(chunks))
      console.log('shot salvo:', out, Buffer.concat(chunks).length, 'bytes')
      res.writeHead(200); res.end('ok')
    })
    return
  }
  // ---- hub de TESTE local (etapa 0.2 do firmware): recebe o batimento da câmera pela rede ----
  if (req.method === 'POST' && url === '/api/v1/thermal/ingest') {
    const chunks = []; let size = 0
    req.on('data', c => { size += c.length; if (size <= 65536) chunks.push(c) })
    req.on('end', () => {
      let msg = null
      try { msg = JSON.parse(Buffer.concat(chunks).toString('utf8')) } catch (e) {}
      const rec = { t: new Date().toISOString(), de: (req.socket.remoteAddress || '').replace('::ffff:', ''), ok: !!msg, msg }
      ingest.push(rec); if (ingest.length > 50) ingest.shift()
      try { fs.mkdirSync(path.join(ROOT, 'data'), { recursive: true }); fs.appendFileSync(path.join(ROOT, 'data', 'ingest.jsonl'), JSON.stringify(rec) + '\n') } catch (e) {}
      console.log('ingest de', rec.de, msg ? `${msg.dev} ${msg.tipo} seq=${msg.seq} rssi=${msg.rssi} max=${msg.max}` : '(JSON inválido)')
      const body = JSON.stringify(msg ? { ok: 1, t: Math.floor(Date.now() / 1000) } : { ok: 0, erro: 'json' })
      res.writeHead(msg ? 200 : 400, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) }); res.end(body)
    })
    return
  }
  if (req.method === 'GET' && url === '/api/v1/thermal/last') {
    const body = JSON.stringify({ total: ingest.length, ultimos: ingest.slice(-20) })
    res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }); return res.end(body)
  }
  if (url === '/__lanip') {   // IPv4 deste PC na rede local, p/ a Bancada sugerir o hub de teste
    const ips = Object.values(os.networkInterfaces()).flat().filter(i => i && i.family === 'IPv4' && !i.internal).map(i => i.address)
    const lan = ips.find(a => /^192\.168\./.test(a)) || ips.find(a => /^10\./.test(a)) || ips.find(a => /^172\.(1[6-9]|2\d|3[01])\./.test(a)) || null
    res.writeHead(200, { 'Content-Type': 'application/json' }); return res.end(JSON.stringify({ ips, sugestao: lan ? `http://${lan}:${PORT}` : null }))
  }
  if (url === '/') url = '/index.html'
  // /stl/* e /firmware/* servidos da raiz do projeto (como no GitHub Pages), resto de public/
  const base = (url.startsWith('/stl/') || url.startsWith('/firmware/')) ? ROOT : path.join(ROOT, 'public')
  const file = path.normalize(path.join(base, url))
  // só public/, stl/ e firmware/ saem daqui — e com separador no fim, para que
  // '/firmware/../server.cjs' ou uma pasta irmã de mesmo prefixo não passem
  const allowed = ['public', 'stl', 'firmware'].some(d => file.startsWith(path.join(ROOT, d) + path.sep))
  if (!allowed || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
    res.writeHead(404); return res.end('404')
  }
  res.writeHead(200, { 'Content-Type': MIME[path.extname(file).toLowerCase()] || 'application/octet-stream' })
  fs.createReadStream(file).pipe(res)
}).listen(PORT, () => console.log(`SAFEBOAT TÉRMICA: http://localhost:${PORT}`))
