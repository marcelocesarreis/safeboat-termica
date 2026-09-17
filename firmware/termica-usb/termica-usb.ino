/**
 * SAFEBOAT TÉRMICA — firmware de bancada "termica-usb" 0.1.0
 *
 * ESP32-C3 SuperMini + MLX90640 (I²C) → quadros térmicos pela USB nativa (CDC).
 * Objetivo: PRIMEIRA LUZ da câmera. Sem rede — só o sensor e o cabo USB (Wi-Fi: ver ../PLANO-WIFI.md).
 *
 * Protocolo (little-endian, 1546 bytes por quadro) — igual a public/serial-parser.js:
 *   A5 5A | ver=1 | flags | seq u16 | Ta i16×100 | 768 × i16×100 | soma u16
 *   flags: bit0 sensor OK · bit1 houve erro I²C neste quadro
 * Texto de diagnóstico sai em linhas iniciadas por "# ".
 *
 * Comandos pela serial (1 caractere):
 *   i → banner   ·   1 2 4 8 → quadros/s (o sensor roda no dobro: 2 subpáginas por quadro)
 *   6 → 16 quadros/s (sensor a 32 Hz, I²C a 1 MHz — experimental)
 *
 * Build/gravação: ver README.md ao lado.
 */
#include <Wire.h>
#include <Adafruit_MLX90640.h>

#define FW_VERSION  "0.1.2"
#define PIN_SDA     8            // ATENÇÃO: o LED onboard do SuperMini também é o GPIO8 — pisca com o I²C, é normal
#define PIN_SCL     9
#define PIN_LED     10           // LED de status do esquema elétrico (se montado)
#define MLX_ADDR    0x33
#define I2C_HZ      400000       // 400 kHz sustenta o sensor até 8 Hz (4 quadros/s)

Adafruit_MLX90640 mlx;
static float to[768];

struct __attribute__((packed)) Pkt {
  uint8_t  s0, s1, ver, flags;
  uint16_t seq;
  int16_t  ta;
  int16_t  t[768];
  uint16_t sum;
};
static Pkt pkt;

static bool     sensorOk = false;
static mlx90640_refreshrate_t rate = MLX90640_8_HZ;   // sensor 8 Hz = 4 quadros completos/s
static uint16_t seq = 0;
static uint32_t i2cErrors = 0, lastRetry = 0, dropped = 0;

static float rateHz(mlx90640_refreshrate_t r) { return 0.5f * (1 << (int)r); }   // 0.5,1,2,4,8,16,32,64

static void banner() {
  Serial.printf("# SAFEBOAT Termica termica-usb %s | MLX90640 @0x%02X %s | SDA=%d SCL=%d %lu kHz | sensor %.0f Hz = %.0f quadros/s | sn %04X%04X%04X | erros I2C %lu | descartados (USB cheia) %lu\n",
    FW_VERSION, MLX_ADDR, sensorOk ? "OK" : "NAO ENCONTRADO", PIN_SDA, PIN_SCL, (unsigned long)(Wire.getClock() / 1000),
    rateHz(rate), rateHz(rate) / 2, mlx.serialNumber[0], mlx.serialNumber[1], mlx.serialNumber[2], (unsigned long)i2cErrors, (unsigned long)dropped);
}

static bool initSensor() {
  if (!mlx.begin(MLX_ADDR, &Wire)) return false;   // lê a EEPROM de calibração e valida o sensor
  mlx.setMode(MLX90640_CHESS);                      // padrão xadrez: menor ruído entre subpáginas
  mlx.setResolution(MLX90640_ADC_18BIT);
  mlx.setRefreshRate(rate);
  return true;
}

void setup() {
  Serial.setTxBufferSize(4096);   // ANTES do begin: o padrão do HWCDC é 256 B — um quadro de 1546 B saía truncado
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);        // nunca trava o loop se ninguém estiver lendo a USB (lição do VIB)
  pinMode(PIN_LED, OUTPUT);
  Wire.begin(PIN_SDA, PIN_SCL, I2C_HZ);
  Wire.setTimeOut(50);
  delay(300);                      // o MLX90640 leva ~80 ms para acordar após a alimentação
  sensorOk = initSensor();
  pkt.s0 = 0xA5; pkt.s1 = 0x5A; pkt.ver = 1;
  banner();
}

static void handleCommand(int c) {
  uint32_t clk = I2C_HZ;
  switch (c) {
    case 'i': case 'I': banner(); return;
    case '1': rate = MLX90640_2_HZ;  break;
    case '2': rate = MLX90640_4_HZ;  break;
    case '4': rate = MLX90640_8_HZ;  break;
    case '8': rate = MLX90640_16_HZ; clk = 800000;  break;
    case '6': rate = MLX90640_32_HZ; clk = 1000000; break;
    default: return;
  }
  Wire.setClock(clk);
  if (sensorOk) mlx.setRefreshRate(rate);
  Serial.printf("# sensor %.0f Hz = %.0f quadros/s | I2C %lu kHz\n", rateHz(rate), rateHz(rate) / 2, (unsigned long)(clk / 1000));
}

static void sendFrame(uint8_t flags, float ta) {
  // quadro inteiro ou nada: com timeout 0, um write maior que o espaço livre sairia TRUNCADO
  if (Serial.availableForWrite() < (int)sizeof(Pkt)) { dropped++; return; }
  pkt.flags = flags;
  pkt.seq   = seq++;
  pkt.ta    = (ta < -100 || ta > 300 || isnan(ta)) ? 0x7FFF : (int16_t)lroundf(ta * 100.0f);
  for (int i = 0; i < 768; i++) {
    long v = lroundf(to[i] * 100.0f);
    pkt.t[i] = (int16_t)constrain(v, -32768L, 32767L);
  }
  const uint8_t* b = (const uint8_t*)&pkt;
  uint16_t s = 0;
  for (size_t k = 0; k < sizeof(Pkt) - 2; k++) s += b[k];
  pkt.sum = s;
  Serial.write(b, sizeof(Pkt));
}

void loop() {
  while (Serial.available()) handleCommand(Serial.read());

  if (!sensorOk) {                              // sensor ausente: tenta de novo a cada 2 s, LED pisca rápido
    digitalWrite(PIN_LED, (millis() / 100) & 1);
    if (millis() - lastRetry > 2000) {
      lastRetry = millis();
      sensorOk = initSensor();
      if (sensorOk) banner();
      else Serial.println("# ERRO: MLX90640 nao responde no I2C (confira 3V3, GND, SDA=8, SCL=9)");
    }
    delay(20);
    return;
  }

  // getFrame lê as 2 subpáginas (bloqueia até o sensor ter dados) e calcula os 768 píxeis em °C
  int status = mlx.getFrame(to);
  if (status != 0) {
    i2cErrors++;
    if ((i2cErrors & 7) == 1) Serial.printf("# aviso: erro I2C %d (total %lu)\n", status, (unsigned long)i2cErrors);
    if (i2cErrors % 50 == 0) { sensorOk = false; Serial.println("# reinicializando o sensor"); }
    delay(5);
    return;
  }
  digitalWrite(PIN_LED, seq & 1);
  sendFrame(0x01, mlx.getTa(false));           // Ta guardado pelo próprio getFrame — sem nova leitura I²C
}
