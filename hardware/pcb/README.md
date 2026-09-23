# SAFEBOAT TÉRMICA v1 — PCB (KiCad 10) · pacote JLCPCB (montagem completa)

Placa **quadrada 32 × 32 mm (cantos R2), 2 camadas, 1,6 mm**, para o case cúbico do render
(`safeboat-site/img/render-termica.jpg`: cubo com a lente descentrada). **Montagem completa na JLCPCB
(Standard PCBA, dois lados)**: 31 posições SMD + borne + JST no lado da ré (F) e o **sensor MLX90640
110°×75° (TO-39, THT) no lado da frente (B)**, virado para a janela de germânio. Chega prontinha: só
parafusar os 2 fios do cabo no borne e gravar o firmware.

Versão anterior (redonda Ø41,4 p/ o case escotilha, sensor 55°) guardada em `kicad/legado-redonda/`.

## O que está aqui

| Pasta / arquivo | Conteúdo |
|---|---|
| `kicad/safeboat-termica-v1.kicad_pcb` + `.kicad_pro` | placa roteada (abre no KiCad 10) — DRC: ver `kicad/drc.json` |
| `kicad/safeboat-termica-v1.kicad_sch` · `safeboat-termica-v1-esquematico.pdf` | **esquemático** (ERC 0 erros; netlist idêntica à PCB — `compare_netlist.py`: 0 diferenças) |
| `kicad/render-top.png` · `render-bottom.png` · `render-iso.png` · `layout-*.svg` | renders 3D e vistas 2D |
| `jlcpcb/safeboat-termica-v1-gerbers.zip` | gerbers + furação (RS-274X / Excellon) — upload no pedido |
| `jlcpcb/BOM-safeboat-termica-v1.csv` · `CPL-safeboat-termica-v1.csv` | BOM e posições p/ a PCBA (todas as peças; U3 = Bottom) |
| `make_board.py` | fase 1: contorno, footprints (sensor e borne com footprints próprios), **netlist pino a pino**, keepout da antena, planos, DSN |
| `finish_board.py` · `fix_drc.py` | fase 2: importa o SES do Freerouting, alarga potência, costura dos planos de GND, serigrafia + logo, `.kicad_pro`; pós-DRC |
| `gen_schematic.py` · `compare_netlist.py` | esquemático a partir da mesma netlist · conferência esquemático × PCB |
| `check_overlaps.py` · `export_jlcpcb.py` · `make_gerbers.sh` · `pipeline_final.sh` | courtyards reais · BOM/CPL · gerbers · pipeline completo |
| `lib/` | símbolo + footprint Espressif do ESP32-C3-MINI-1 (mesma lib do VIB) |

## Circuito (resumo — netlist completa em `make_board.py`)

- **Entrada 12 V do barco**: borne parafuso **J2 KF350 3,5 mm** (1 = +12V, pad quadrado · 2 = GND; aceita 0,75 mm²),
  fusível 1 A em linha no cabo → **F1** PPTC 0,5 A/60 V → **D1** TVS SMAJ26A (surtos do alternador) →
  **D2** SS34 em série (inversão de polaridade) → VIN.
- **Buck**: **U2 AP63203** (síncrono, 3,8–32 V, 3,3 V fixo, 2 A, 1,1 MHz, Iq 22 µA): EN ligado a VIN
  (datasheet: "attach to VIN"), FB direto no VOUT; C5 10 µF/50 V (1210) na entrada, **L1 4,7 µH SWPA4020S**,
  C6/C7 2×22 µF na saída, C8 100 nF de bootstrap (BST–SW).
- **USB de bancada**: **J1** JST-PH 4 vias (1 5V · 2 D− · 3 D+ · 4 GND) → **D3** SS14 → VIN. A placa liga só
  no USB; com 12 V presente o D3 fica bloqueado. Rabicho: cabo "USB-C fêmea → 4 fios PH 2,0 mm" (o breakout
  USB-C precisa ter os resistores CC de 5k1). O BLE do firmware 0.2.8 já é o "cabo sem fio" da Bancada.
- **MCU U1 ESP32-C3-MINI-1-N4**: mesma pinagem do firmware atual — **GPIO8 SDA · GPIO9 SCL · GPIO10 LED**;
  GPIO4 = SENS_OFF; GPIO0 = VSENSE (tensão do barco: R7 200k / R8 20k = VIN/11, + C4 100 nF); GPIO18/19 = USB;
  EN com R1 10k + C1 1 µF + SW2 RST; SW1 BOOT em GPIO9 (= SCL, pull-up R3); C9 10 µF + C10 100 nF.
  Antena rente à borda superior, keepout de cobre nas 2 camadas.
- **Sensor U3 MLX90640ESF-BAA** (110°×75°; TO-39: 1 SDA · 2 VDD · 3 GND · 4 SCL): alimentado por VDD_MLX = 3V3
  via **Q1 SI2301** (PMOS, ligado por padrão: R5 100k gate→GND; GPIO4 alto = sensor desligado, para o modo
  de baixo consumo futuro). C2 100 nF + C3 10 µF junto ao VDD. Pull-ups **R2/R3 2k2 para VDD_MLX**.
  Firmware: o 0.2.8 lê qualquer FOV (a calibração vem da EEPROM do sensor); a página/engine assume 55°×35°
  nas zonas — ajustar quando o 110° estiver na bancada.
- **LED1** âmbar em GPIO10 via R4 1k.

## Mecânica (case cúbico — a desenhar a partir desta placa)

- Placa 32 × 32; **lente do sensor 9,5 mm abaixo do centro** (o módulo Wi-Fi de 16,6 mm não deixa o sensor no
  centro de uma placa de 32 — coincide com o render, que tem a lente descentrada). Sem furos de fixação:
  prender por trilhos/ranhura de 1,7 mm nas 4 bordas do case ou por 2 clipes nos cantos superiores.
- Lata do 110°: Ø9,3 × **5,8 mm** (bem mais baixa que a do 55°, 11,25). Frente da placa até a janela ≥ 6,5 mm;
  a abertura precisa de FOV 110°×75°: com a lente a 6,5 mm da janela, furo ≥ Ø24 (ou janela de germânio Ø25 rente).
- Ré: borne 7,3 mm + JST 6 mm + plugue; profundidade interna total ≈ 22–26 mm → **case externo ≈ 36 × 36 × 30 mm**
  com paredes de 2 mm (o render "3×3×3" fica em 3,6 por causa do módulo Wi-Fi).
- Serigrafia da frente: rótulos SDA/VDD/GND/SCL ao lado de cada furo e a aba do TO-39 desenhada (aba entre SCL
  e SDA, como na vista de baixo do datasheet). O footprint TO-39-4 do KiCad (Ø5,08) NÃO serve: pinos em Ø5,84.

## Pedido na JLCPCB (passo a passo)

1. **PCB**: upload de `jlcpcb/safeboat-termica-v1-gerbers.zip` — 2 camadas, 1,6 mm, HASL ou ENIG,
   cor a gosto (verde sai mais rápido). Quantidade mínima 5.
2. **PCBA Standard, "Both sides"** (Economic não monta THT nem os dois lados): upload de
   `BOM-safeboat-termica-v1.csv` + `CPL-safeboat-termica-v1.csv`. O sensor U3 aparece com Layer = Bottom
   (lado da frente) e os THT (U3 borne J2, JST J1) entram na montagem — confirmar no viewer que o sensor
   está do lado oposto ao módulo.
3. **Códigos LCSC verificados em 22/09/2026**: U1 C2934569 · U2 C780769 · U3 **C17380659** (MLX90640ESF-BAA,
   ~US$ 22) · Q1 C10487 · D1 C132945 · L1 C48427 · F1 C462518 · J1 C131334 · J2 C474892 · SW1/SW2 C72443 ·
   LED1 C157740.
4. **Marcados VERIFICAR** na BOM (escolher no diálogo *Edit Part* pelo valor, conferindo encapsulamento):
   D2 SS34 (SMA), D3 SS14 (SMA), C5 10 µF **50 V** 1210, C6/C7 22 µF 10 V 0805, C9 10 µF 0805,
   R2/R3 2k2, R7 200k, R8 20k (básicos 0603 por valor).
5. Ao editar uma peça a linha desmarca — **remarcar o checkbox** (armadilha do site). O pedido são sempre
   2 linhas (PCB + PCBA) — não apagar a linha "PCB prototype".
6. Depois de chegar: parafusar os 2 fios no borne (+12V no pad quadrado), gravar o firmware pelo rabicho USB
   (BOOT + RST na placa) — ou pelo BLE/OTA quando existir.

## Pendências / rev 2

- Case cúbico em JSCAD a partir desta placa (trilhos, janela Ø25, prensa-cabo na ré, emblema).
- Medir na bancada: consumo em 12 V, aquecimento do buck, ripple no VDD do sensor.
- Firmware: GPIO4 (sensor OFF) e GPIO0 (tensão do barco) ainda não existem no 0.2.8; engine com FOV 110°.
- USB-C vertical na placa (em vez do rabicho JST) se aparecer um conector com footprint confiável.
- 24 V: o AP63203 aguenta 32 V; com o TVS de 26 V a placa é para **barcos de 12 V**.
