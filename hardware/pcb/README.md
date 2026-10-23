# SAFEBOAT TÉRMICA v2 — PCB (KiCad 10) · pacote JLCPCB (montagem completa)

Rev. 2 (reunião de equipe de 22/10/2026). Placa **40 × 40 mm, 4 camadas (F sinais · In1 plano GND · In2 plano 3V3 ·
B sinais), 1,6 mm**, cantos R2, **recortes laterais na antena**. **Montagem completa na JLCPCB (Standard PCBA, dois
lados)**: SMD + JST no lado da ré (F) e o **sensor MLX90640 110°×75° (TO-39, THT) no lado da frente (B)**. Chega
pronta: só soldar os 2 fios de alimentação nos pads e gravar o firmware.

Versões anteriores: redonda Ø41,4 (case escotilha, sensor 55°) em `kicad/legado-redonda/`; quadrada 32 × 32 de 2 camadas
(v1, 22/09) só no histórico do git.

## O que mudou na rev. 2 (pedidos da reunião)

| Pedido | O que foi feito |
|---|---|
| Nada metálico perto da antena | Indutor, botões, JST e diodos saíram do topo; acima de y = +14,35 só existe o módulo. Faixas laterais do módulo só com 0603/0805 e o SOT-23 do PMOS. |
| Diretrizes de layout da Espressif | Antena rente à borda **com recortes de 3,3 mm nos dois lados** ("cut out the base board on both sides of the antenna"), keep-out de cobre nas 4 camadas sob a antena e recortes, plano de GND sólido sob o módulo (In1), vias de GND, 10 µF + 100 nF no 3V3 junto ao pino, RC no EN, USB longe da antena (canto inferior esquerdo). |
| Trilhas a 90° nos pads | Roteador travado em **ninety_degree**: todas as trilhas são ortogonais, entram reto em todos os pads. |
| Menos voltas / mais planos | **4 camadas**: In1 = GND sólido, In2 = 3V3 sólido; o roteador não roteia nos planos (só fura para eles), então sobram poucas trilhas em F/B. |
| Clearance × limites JLC | Isolamento **0,2 mm** (JLC 4 camadas: ≥ 0,127), trilha 0,25, via 0,6/0,3 (JLC ≥ 0,45/0,2), cobre–borda 0,3, furo–furo ≥ 0,5; regras gravadas no `.kicad_pro`. |
| 4 furos de fixação longe da antena | **M2,5 (Ø2,7)** em (±17,5; +3) e (±17,5; −18): padrão 35 × 21 mm; os de cima ficam 11 mm abaixo do início da antena e 7,6 mm fora do recorte. Raio livre de 2,3 mm para a cabeça. |
| Fusível na entrada | Mantido: **F1 PPTC 0,5 A / 60 V** (SMD1812P050TF/60) + fusível 1 A em linha no cabo. |
| Alimentação 8–32 V | O AP63203 (32 V abs. max.) e o TVS de 26 V **saíram**. Entrou **MP4560** (3,8–55 V, 2 A, abs. max. 60 V), **TVS SMBJ33A** (standoff 33 V, clamp 53 V) e capacitores de entrada **4,7 µF/100 V**. Divisor de leitura da tensão virou 330k/15k (55 V → 2,4 V no ADC). |
| Sem conector de alimentação | Borne removido; **pads P1 (+VIN, quadrado) e P2 (GND)** Ø2,6 / furo 1,3 para soldar o fio direto. |

## O que está aqui

| Pasta / arquivo | Conteúdo |
|---|---|
| `kicad/safeboat-termica-v1.kicad_pcb` + `.kicad_pro` | placa roteada (abre no KiCad 10) — DRC: ver `kicad/drc.json` |
| `kicad/safeboat-termica-v1.kicad_sch` · `safeboat-termica-v1-esquematico.pdf` | **esquemático** (ERC; netlist conferida contra a PCB por `compare_netlist.py`) |
| `kicad/render-*.png` · `layout-*.svg` · `revisao/` | renders 3D (com modelos do sensor e dos pads), vistas 2D, pacote para revisão |
| `jlcpcb/safeboat-termica-v1-gerbers.zip` | gerbers 4 camadas + furação (RS-274X / Excellon) — upload no pedido |
| `jlcpcb/BOM-safeboat-termica-v1.csv` · `CPL-safeboat-termica-v1.csv` | BOM (todas as linhas com código LCSC) e posições (U3 = Bottom) |
| `make_board.py` | fase 1: contorno com recortes, furos, footprints próprios (sensor), **netlist pino a pino**, keep-out, planos, DSN a 90° |
| `finish_board.py` · `fix_drc.py` | fase 2: importa o SES do Freerouting, alarga potência, costura de GND, serigrafia + logo, `.kicad_pro`; pós-DRC |
| `gen_schematic.py` · `compare_netlist.py` | esquemático a partir da mesma netlist · conferência esquemático × PCB |
| `check_overlaps.py` · `export_jlcpcb.py` · `make_gerbers.sh` · `pipeline_final.sh` | courtyards reais, recortes, furos · BOM/CPL · gerbers · pipeline completo |
| `lib/` · `make_3d_models.cjs` · `add_models.py` | símbolo/footprint Espressif; modelos 3D próprios (VRML) do sensor |

## Circuito (resumo — netlist completa em `make_board.py`)

- **Entrada 8–32 V**: P1/P2 (fio soldado; fusível 1 A no cabo) → F1 PPTC 0,5 A/60 V → D1 TVS SMBJ33A → D2 SS34 em série
  (inversão de polaridade) → VIN.
- **Buck U2 MP4560** (não síncrono, 2 A): **FREQ R11 200k → 488 kHz**; FB 0,8 V com **R9 47k / R10 15k → 3,31 V**
  (valores básicos da JLC); COMP **R12 68k + C12 1 nF**; BST C8 100 nF; entrada C5 + C11 4,7 µF/100 V; **L1 10 µH
  SWPA5040S** (2,1 A); roda livre **D4 SS36** (60 V); saída C6/C7 2×22 µF. **EN fica flutuante (= ligado)**: o pino tem
  máximo absoluto de 5 V e não pode ir ao VIN.
- **USB de bancada**: J1 JST-PH 4 vias (1 5V · 2 D− · 3 D+ · 4 GND) → D3 SS14 → VIN. Liga só no USB; com o barco ligado o D3 bloqueia.
- **MCU U1 ESP32-C3-MINI-1-N4**: GPIO8 SDA · GPIO9 SCL (+ BOOT SW1) · GPIO10 LED · GPIO4 SENS_OFF · GPIO0 VSENSE
  (R7 330k / R8 15k + C4) · GPIO18/19 USB · EN com R1 10k + C1 1 µF + SW2 RST · C9 10 µF + C10 100 nF.
- **Sensor U3 MLX90640ESF-BAA** (110°; 1 SDA · 2 VDD · 3 GND · 4 SCL) em VDD_MLX = 3V3 via Q1 SI2301 (ligado por
  padrão; GPIO4 alto desliga); C2 100 nF + C3 10 µF; pull-ups R2/R3 2k2 para VDD_MLX.

## Mecânica

- Lente do sensor em (0; −12) da placa (descentrada: o módulo de 16,6 mm ocupa o topo). Lata Ø9,3 × 5,7 mm na frente;
  decisão de 13/10: **lata exposta** pelo furo do case com anel de vedação em volta, sem janela de germânio.
- Ré: JST 6 mm + plugue, indutor 4 mm, botões 2 mm. Case externo ≈ 44 × 44 × 28 mm com paredes de 2 mm.
- Furos M2,5 em (±17,5; +3) e (±17,5; −18) — postes de Ø5 no case, cabeça ≤ Ø4,6.

## Pedido na JLCPCB

1. **PCB**: upload de `jlcpcb/safeboat-termica-v1-gerbers.zip` — **4 camadas**, 1,6 mm, stack-up padrão JLC04161H, HASL ou
   ENIG, 5 unidades.
2. **PCBA Standard, "Both sides"**: upload de `BOM-safeboat-termica-v1.csv` + `CPL-safeboat-termica-v1.csv`. U3 aparece
   com Layer = Bottom; confirmar no viewer que o sensor está do lado oposto ao módulo.
3. **Códigos LCSC** (todas as linhas): U1 C2934569 · U2 **C40133** (MP4560, US$ 4,45) · U3 **C17380659** (MLX90640 110°,
   ~US$ 28, estoque LCSC 34 un. em 13/10) · Q1 C10487 · D1 **C173526** (SMBJ33A) · D2 C8678 · D3 C2480 · D4 **C360444**
   (SS36A) · L1 **C84608** (SWPA5040S-100) · F1 C462518 · J1 C131334 · SW1/SW2 C72443 · LED1 C157740 · C5/C11
   **C337978** (4,7 µF 100 V) · C6/C7 C45783 · C9 C15850 · C3 C19702 · C1 C15849 · 100 nF C14663 · C12 C1588 ·
   R1 C25804 · R2/R3 C4190 · R4/R6 C21190 · R5 C25803 · R7 C23137 · R8/R10 C22809 · R9 C25819 · R11 C25811 · R12 C23231.
   Os de R9/R11/R12/C12/R7/R8 vieram do guia de básicos da JLC — conferir no carrinho (editar peça desmarca a linha).
4. Depois de chegar: soldar os 2 fios nos pads (+VIN no quadrado), gravar o firmware pelo rabicho USB (BOOT + RST).

## Pendências

- Case cúbico em JSCAD (furo da lata + anel, postes M2,5, prensa-cabo na ré).
- Bancada: consumo em 8/12/24/32 V, ripple no VDD do sensor, aquecimento do MP4560, teste de surto.
- Firmware: GPIO4 e GPIO0; engine com FOV 110°.
