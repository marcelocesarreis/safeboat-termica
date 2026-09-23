# SAFEBOAT Térmica

Sistema de manutenção preditiva por visão térmica com IA para embarcações.
Câmera térmica própria — **MLX90640 (32×24 px) + ESP32-C3 SuperMini** — em case
estanque Ø50×62 mm impresso em ASA, com conexão Wi-Fi e alimentação 12 V do barco.

## Página do projeto

```
node server.cjs        # http://localhost:8097  (launch.json: "safeboat-termica")
```

A página (`public/index.html`) contém: visualizador 3D com vista explodida,
demo **ao vivo** da rede de análise com 3 câmeras mocadas, método de
comparação/detecção, esquema elétrico, cabeamento, fixação, fabricação e BOM.

## Rede de análise (`public/engine.js`)

Implementação de referência do pipeline, idêntica no navegador (mock) e em Node:

1. Aquisição 32×24 @ 4 Hz por I²C, dentro da câmera
2. Normalização (Ta do sensor)
3. Baseline por pixel (média+σ, Welford) por regime de operação
4. Comparação: Δ e z-score (anomalia: z>4 **e** Δ>6 °C)
5. Blobs (componentes conectados ≥3 px)
6. Persistência temporal (≥3 frames)
7. Classificação por zona de equipamento + severidade
8. Alerta com diagnóstico sugerido

Com hardware real: `public/bancada.html` (USB) já alimenta o detector com quadros do sensor.
Rede: ver `firmware/PLANO-WIFI.md` — HTTPS para o hub, receita do VIB, sem MQTT.

## Hardware

- Módulo MLX90640 (GY-MCU90640) via I²C (GPIO8/9, 400 kHz) no ESP32-C3
- Buck MP1584EN 12→5 V + TVS SMBJ26A; MLX no 3V3 do ESP
- Janela frontal de **germânio Ø25×1** (vidro comum bloqueia 8–14 µm);
  alternativa de bancada: filme HDPE 0,25 mm no mesmo recesso
- Vedação (rev. C): tampa de **baioneta 60°** + O-ring NBR 37×3 radial + prensa-cabo M12 IP68
  (a rosca impressa da rev. B falhou: 0,50 mm de engajamento contra 0,20–0,45 mm de erro de FDM)

## CAD paramétrico

```
node tools/generate-stl.cjs    # regenera stl/*.stl (corpo, tampa, carrier, suporte)
```

Mesma receita validada no projeto Vigia (`../safeboat-camera-nv`).

## Retomar o projeto em outra máquina

Este ramo (`projeto`) tem o código-fonte completo; o ramo `main` é só o site publicado no GitHub Pages
(cópia de `public/` + `stl/` + `firmware/`).

```
git clone -b projeto https://github.com/marcelocesarreis/safeboat-termica.git
cd safeboat-termica
npm install            # JSCAD, three, pngjs (CAD e página)
npm start              # servidor local + hub de teste em http://localhost:8097  (Bancada: /bancada.html)
npm run stl            # regenera os STL da rev. C;  node tools/verify-fit.cjs confere a montagem
node tools/test-parser.cjs
```

Firmware (placa ESP32-C3 SuperMini + MLX90640, fonte em `firmware/termica/termica.ino`, versão atual 0.2.8):

```
arduino-cli core install esp32:esp32@3.3.10
arduino-cli lib install "Adafruit MLX90640"
arduino-cli compile --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc,PartitionScheme=min_spiffs --build-path firmware/build-termica firmware/termica
arduino-cli upload -p COMx --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc,PartitionScheme=min_spiffs --input-dir firmware/build-termica
```

Use sempre a MESMA `--build-path` (a primeira compilação é longa; as seguintes são rápidas). Os binários prontos da
0.2.8 estão em `firmware/build-termica-0.2.8/` — dá para gravar sem compilar. Ferramentas Python (`pip install pyserial bleak`):
`tools/wifi-cmd.py` (comandos pela USB; recusa o comando de senha), `tools/ble-test.py` (teste do Bluetooth), `tools/serial-dump.py`.

Estado em 19/09/2026: USB, Wi-Fi (HTTPS ao hub, sem MQTT) e Bluetooth LE funcionando; o sensor MLX90640 parou de
responder no I²C (conferir os 4 fios 3V3/GND/GPIO8=SDA/GPIO9=SCL). Próxima etapa: 0.3, detector a bordo — ver `firmware/PLANO-WIFI.md`.
A senha do Wi-Fi fica só na NVS da placa (digitada na Bancada pela USB); não está em nenhum arquivo do repositório.

## Hardware — PCB v1 (22/09/2026)

Placa própria em `hardware/pcb/` (KiCad 10, gerada por script): **quadrada 32 × 32 mm** para o case cúbico do render
(~36 mm externo), **montagem completa na JLCPCB (Standard, dois lados)**: ESP32-C3-MINI-1 + buck AP63203 (12 V → 3,3 V)
+ proteção (PPTC, TVS, SS34) + borne parafuso 12 V + JST p/ rabicho USB na ré; **MLX90640 110°×75°** (TO-39, THT) na
frente. Mesma pinagem do firmware (SDA 8 / SCL 9 / LED 10) + GPIO4 (corta o sensor) e GPIO0 (tensão do barco).
Pacote JLCPCB pronto (gerbers + BOM + CPL), esquemático com ERC 0 e netlist conferida contra a placa —
ver `hardware/pcb/README.md`. A versão redonda Ø41,4 (case escotilha, sensor 55°) ficou em `hardware/pcb/kicad/legado-redonda/`;
o corpo rev. D (ombro z=14) e `stl/espacador-pcb.stl` valem só para ela. Case cúbico em JSCAD: a fazer.
