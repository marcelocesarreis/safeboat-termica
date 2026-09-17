# termica-usb — firmware de bancada (primeira luz)

ESP32-C3 SuperMini + MLX90640 → quadros térmicos pela USB nativa. Sem Wi-Fi.

## Ligações
| MLX90640 | ESP32-C3 SuperMini |
|---|---|
| VIN | 3V3 |
| GND | GND |
| SDA | GPIO8 (é também o LED onboard — pisca com o I²C, normal) |
| SCL | GPIO9 |

## Build e gravação (arduino-cli, receita do VIB)
```
arduino-cli lib install "Adafruit MLX90640"
arduino-cli compile --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc,PartitionScheme=min_spiffs --output-dir firmware/build-termica-usb-0.1.0 firmware/termica-usb
arduino-cli upload  -p COM26 --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc,PartitionScheme=min_spiffs --input-dir firmware/build-termica-usb-0.1.0 firmware/termica-usb
```

## Ver a câmera
- **Navegador**: `http://localhost:8097/bancada.html` → **Conectar USB** (Chrome/Edge no PC, Web Serial).
- **Terminal**: `python tools/serial-dump.py COM26 --ascii`

## Protocolo
1546 bytes/quadro: `A5 5A | ver=1 | flags | seq u16 | Ta i16×100 | 768×i16×100 | soma u16`.
Texto de diagnóstico em linhas `# ...`. Comandos: `i` info · `1 2 4 8` Hz · `6` = 16 Hz (I²C 800 kHz).
Definição única em `public/serial-parser.js` (navegador + Node) e `tools/serial-dump.py`.

## Se o sensor não aparecer
O banner diz `MLX90640 NAO ENCONTRADO` e a placa tenta de novo a cada 2 s.
Confira 3V3/GND, SDA=8/SCL=9 e se o módulo tem pull-ups (os GY-MCU90640 têm).
