"""
Ponte USB -> WebSocket: testa a tela de exposição (public/expo.html) com a câmera REAL ligada no cabo,
sem tirar o notebook da internet para entrar na rede da câmera.

    python tools/usb-ws-bridge.py COM7            # serve ws://localhost:8181
    http://localhost:8097/expo.html?cam=localhost:8181   (a página aceita host:porta em ?cam=)

Repassa cada quadro de 1546 B (A5 5A 01 ... soma) como uma mensagem binária, igual ao firmware termica-expo na porta 81.
Opcional: --gravar arquivo.bin guarda os quadros crus (fixture para calibrar o classificador).
"""
import sys, time, socket, threading, hashlib, base64, struct
import serial

FRAME = 1546
PORT = 8181
clients, lock = [], threading.Lock()


def handshake(c):
    data = b''
    while b'\r\n\r\n' not in data:
        chunk = c.recv(2048)
        if not chunk:
            return False
        data += chunk
    key = None
    for line in data.split(b'\r\n'):
        if line.lower().startswith(b'sec-websocket-key:'):
            key = line.split(b':', 1)[1].strip()
    if not key:
        return False
    acc = base64.b64encode(hashlib.sha1(key + b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest())
    c.sendall(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ' + acc + b'\r\n\r\n')
    return True


def acceptor():
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('127.0.0.1', PORT)); srv.listen(4)
    while True:
        c, _ = srv.accept()
        try:
            if handshake(c):
                c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                with lock: clients.append(c)
                print('cliente conectado', flush=True)
            else:
                c.close()
        except OSError:
            c.close()


def broadcast(frame):
    msg = b'\x82\x7e' + struct.pack('>H', len(frame)) + frame
    with lock:
        for c in clients[:]:
            try: c.sendall(msg)
            except OSError: clients.remove(c); print('cliente saiu', flush=True)


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else 'COM7'
    rec = open(sys.argv[sys.argv.index('--gravar') + 1], 'ab') if '--gravar' in sys.argv else None
    threading.Thread(target=acceptor, daemon=True).start()
    s = serial.Serial(port, 115200, timeout=0.2); s.dtr = True
    print(f'{port} -> ws://localhost:{PORT}', flush=True)
    buf, n, t0 = b'', 0, time.time()
    while True:
        buf += s.read(8192)
        while True:
            i = buf.find(b'\xa5\x5a\x01')
            if i < 0: buf = buf[-2:]; break
            if len(buf) - i < FRAME: buf = buf[i:]; break
            f = buf[i:i + FRAME]
            if (sum(f[:-2]) & 0xFFFF) == f[-2] | (f[-1] << 8):
                broadcast(f); n += 1; buf = buf[i + FRAME:]
                if rec: rec.write(f)
            else:
                buf = buf[i + 1:]
        if time.time() - t0 > 10:
            print(f'{n / (time.time() - t0):.1f} quadros/s, {len(clients)} cliente(s)', flush=True); n, t0 = 0, time.time()


if __name__ == '__main__':
    main()
