/**
 * SAFEBOAT TÉRMICA — firmware "termica" 0.2.3  (USB + Wi-Fi + Bluetooth LE)
 *
 * Etapa 0.2 do firmware/PLANO-WIFI.md: tudo do termica-usb (quadros binários pela USB,
 * a Bancada continua funcionando) + Wi-Fi com credenciais na NVS, batimento por HTTP ao
 * hub e sonda de internet. Receita do VIB: sem MQTT, falha de Wi-Fi NUNCA para o sensor.
 *
 * USB → host (inalterado): quadro de 1546 B  A5 5A | ver | flags | seq | Ta×100 | 768×i16×100 | soma
 *   texto de diagnóstico em linhas "# ...";  estado p/ a interface em linhas  "#J {json}"
 *
 * host → placa:
 *   imediatos (1 caractere)  i = banner · 1 2 4 8 = quadros/s · 6 = 16 quadros/s
 *   linhas (terminadas em \n, campos separados por TAB — SSID pode ter espaço):
 *     S                 procura redes 2,4 GHz
 *     W <ssid> <senha>  grava na NVS e conecta   (a senha NUNCA é ecoada)
 *     X                 esquece a rede
 *     H <url>           hub de teste, ex. http://192.168.0.148:8097
 *     T                 batimento + sonda de internet agora
 *
 * Bluetooth LE (0.2.3) — "cabo sem fio": o MESMO fluxo de bytes da USB (quadros + texto) sai
 * em notificações, fatiado pela MTU; o celular usa o mesmo parser da Bancada (Web Bluetooth).
 *   serviço 5afe0001-…  ·  DATA 5afe0002 (notify)  ·  CTRL 5afe0003 (write: os comandos acima)
 *   Sem pareamento o enlace NÃO é cifrado: W, X e H são RECUSADOS pelo BLE (senha só pela USB).
 *   Wi-Fi + BLE dividem o mesmo rádio: o modem-sleep do Wi-Fi fica LIGADO (exigência do chip).
 */
#include <Wire.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <Adafruit_MLX90640.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include "host/ble_hs.h"           // NimBLE cru: notify com retorno (controle de fluxo — receita do VIB)
#include <stdarg.h>

#define FW_VERSION  "0.2.3"
#define PIN_SDA     8            // também é o LED onboard do SuperMini — pisca com o I²C, normal
#define PIN_SCL     9
#define PIN_LED     10
#define MLX_ADDR    0x33
#define I2C_HZ      400000
#define BEAT_MS     15000UL      // bancada: 15 s (produção: resumo 60 s / batimento 600 s)
#define PROBE_MS    60000UL      // sonda de internet
#define PROBE_URL   "https://hub.safeboat.tech/fw/status"   // GET inofensivo: prova DNS + TLS + rota

Adafruit_MLX90640 mlx;
Preferences prefs;
static float to[768];

struct __attribute__((packed)) Pkt { uint8_t s0, s1, ver, flags; uint16_t seq; int16_t ta; int16_t t[768]; uint16_t sum; };
static Pkt pkt;

static bool     sensorOk = false;
static mlx90640_refreshrate_t rate = MLX90640_8_HZ;   // sensor 8 Hz = 4 quadros/s
static uint16_t seq = 0;
static uint32_t i2cErrors = 0, lastRetry = 0, dropped = 0;
static float    fMin = 0, fMax = 0, fMean = 0, fTa = NAN; static int hotIdx = 0;

// ---------------- Wi-Fi ----------------
enum WState { WS_SEM_REDE, WS_CONECTANDO, WS_CONECTADO, WS_RECUO };
static WState   wst = WS_SEM_REDE;
static String   cfgSsid, cfgPass, cfgHub, devId;
static uint32_t wT0 = 0, lastBeat = 0, lastProbe = 0, lastStatus = 0;
static uint16_t wFails = 0;
static bool     txLow = false, beatDue = false, probeDue = false, statusDue = true;
static int      hubCode = 0, netCode = 0; static uint32_t hubMs = 0, netMs = 0, beats = 0, hubFails = 0;

// Motivo REAL da queda, capturado no evento do driver: WiFi.status() sozinho só diz "falhou".
// Guarda o PRIMEIRO motivo de cada tentativa (8 = ASSOC_LEAVE é o nosso próprio disconnect).
static volatile uint8_t wReason = 0; static volatile bool wAssoc = false, wGotIp = false;
static const char* reasonName(uint8_t r) {
  switch (r) {
    case 0:   return "-";
    case 2:   return "AUTH_EXPIRE: o AP nao respondeu a autenticacao";
    case 4:   return "ASSOC_EXPIRE: inatividade na associacao";
    case 5:   return "ASSOC_TOOMANY: o roteador RECUSOU por excesso de clientes no radio/SSID (nem chegou a testar a senha)";
    case 6:   return "NOT_AUTHED";
    case 15:  return "4WAY_HANDSHAKE_TIMEOUT: senha recusada ou PMF/WPA3 incompativel";
    case 23:  return "802_1X_AUTH_FAILED";
    case 39:  return "TIMEOUT";
    case 200: return "BEACON_TIMEOUT: sinal perdido";
    case 201: return "NO_AP_FOUND: a placa nao enxerga esse SSID";
    case 202: return "AUTH_FAIL: o AP recusou a autenticacao (senha, filtro de MAC ou limite de clientes)";
    case 203: return "ASSOC_FAIL: o AP recusou a associacao";
    case 204: return "HANDSHAKE_TIMEOUT: senha recusada";
    case 205: return "CONNECTION_FAIL";
    case 210: return "NO_AP_FOUND_W_COMPATIBLE_SECURITY: seguranca do AP incompativel";
    case 211: return "NO_AP_FOUND_IN_AUTHMODE_THRESHOLD: AP abaixo do minimo WPA2";
    case 212: return "NO_AP_FOUND_IN_RSSI_THRESHOLD";
    default:  return "outro (ver tabela wifi_err_reason_t)";
  }
}
static void onWifiEvent(WiFiEvent_t ev, WiFiEventInfo_t info) {
  if (ev == ARDUINO_EVENT_WIFI_STA_CONNECTED) wAssoc = true;
  else if (ev == ARDUINO_EVENT_WIFI_STA_GOT_IP) wGotIp = true;
  else if (ev == ARDUINO_EVENT_WIFI_STA_DISCONNECTED) {
    uint8_t r = info.wifi_sta_disconnected.reason;
    if (r != 8 && wReason == 0) wReason = r;
  }
}
static const char* authName(wifi_auth_mode_t a) {
  switch (a) {
    case WIFI_AUTH_OPEN: return "aberta";       case WIFI_AUTH_WEP: return "WEP";
    case WIFI_AUTH_WPA_PSK: return "WPA";       case WIFI_AUTH_WPA2_PSK: return "WPA2";
    case WIFI_AUTH_WPA_WPA2_PSK: return "WPA/WPA2"; case WIFI_AUTH_WPA2_ENTERPRISE: return "WPA2-ENT";
    case WIFI_AUTH_WPA3_PSK: return "WPA3";     case WIFI_AUTH_WPA2_WPA3_PSK: return "WPA2/WPA3";
    default: return "outra";
  }
}

// ---------------- Bluetooth LE ----------------
#define UUID_SVC  "5afe0001-5445-524d-4943-410000000001"
#define UUID_DATA "5afe0002-5445-524d-4943-410000000001"
#define UUID_CTRL "5afe0003-5445-524d-4943-410000000001"
static BLEServer* bleSrv = NULL; static BLECharacteristic *chData = NULL, *chCtrl = NULL;
static volatile bool bleConn = false, bleSub = false; static volatile uint16_t bleHandle = 0xFFFF;
static uint16_t bleMtu = 23; static uint32_t bleFrames = 0, bleDrops = 0, bleRetries = 0;
static String bleCmd = "";          // comando recebido: executa no loop (fora da tarefa do host BLE)
static volatile bool bleCmdDue = false;

// notify com controle de fluxo: o notify() da biblioteca engole o erro de mbuf cheio (no VIB 32 % sumia)
static bool bleNotify(const uint8_t* p, size_t n) {
  for (int k = 0; k < 100; k++) {                   // <= ~300 ms por fatia
    if (!bleConn || !bleSub) return false;
    os_mbuf* om = ble_hs_mbuf_from_flat(p, n);
    if (om) {
      int rc = ble_gatts_notify_custom(bleHandle, chData->getHandle(), om);   // consome o om sempre
      if (rc == 0) return true;
      if (rc != BLE_HS_ENOMEM && rc != BLE_HS_EBUSY && rc != BLE_HS_EAGAIN) return false;
    }
    bleRetries++; delay(3);
  }
  return false;
}
static bool bleWrite(const uint8_t* p, size_t n) {   // fatia pela MTU; falso = abandonou no meio (o parser ressincroniza pela soma)
  if (!bleConn || !bleSub) return false;
  { uint16_t m = bleSrv->getPeerMTU(bleHandle); if (m >= 23) bleMtu = m; }
  size_t step = (bleMtu > 512 ? 512 : bleMtu) - 3;
  for (size_t o = 0; o < n; o += step) if (!bleNotify(p + o, (n - o < step) ? n - o : step)) return false;
  return true;
}
// todo texto de diagnóstico sai pela USB E pelo BLE
static void say(const char* fmt, ...) {
  char b[700]; va_list ap; va_start(ap, fmt); int n = vsnprintf(b, sizeof b, fmt, ap); va_end(ap);
  if (n <= 0) return;
  if (n >= (int)sizeof b) n = sizeof b - 1;
  Serial.write((const uint8_t*)b, n);
  bleWrite((const uint8_t*)b, n);
}
class SrvCb : public BLEServerCallbacks {
  void onConnect(BLEServer* s) { bleHandle = s->getConnId(); bleSub = false; bleMtu = 23; bleConn = true; }
  void onDisconnect(BLEServer* s) { bleConn = false; bleSub = false; BLEDevice::startAdvertising(); }
};
class DataCb : public BLECharacteristicCallbacks {
  void onSubscribe(BLECharacteristic* c, ble_gap_conn_desc* desc, uint16_t subValue) {
    bleSub = subValue != 0;
    // intervalo curto (7,5–15 ms) SÓ depois da descoberta: pedido no onConnect, o Windows abortava a descoberta
    if (bleSub) BLEDevice::getServer()->updateConnParams(bleHandle, 6, 12, 0, 400);
  }
};
class CtrlCb : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic* c) { if (!bleCmdDue) { bleCmd = c->getValue(); bleCmdDue = true; } }
};

static float rateHz(mlx90640_refreshrate_t r) { return 0.5f * (1 << (int)r); }

static String jsonEsc(const String& s) {
  String o; o.reserve(s.length() + 4);
  for (size_t i = 0; i < s.length(); i++) { char c = s[i]; if (c == '"' || c == '\\') o += '\\'; if ((uint8_t)c >= 32) o += c; }
  return o;
}
static const char* wName() { switch (wst) { case WS_SEM_REDE: return "sem_rede"; case WS_CONECTANDO: return "conectando"; case WS_CONECTADO: return "ok"; default: return "falhou"; } }

static void banner() {
  say("# SAFEBOAT Termica termica %s | %s | MLX90640 @0x%02X %s | SDA=%d SCL=%d %lu kHz | sensor %.0f Hz = %.0f quadros/s | sn %04X%04X%04X | erros I2C %lu | descartados (USB cheia) %lu\n",
    FW_VERSION, devId.c_str(), MLX_ADDR, sensorOk ? "OK" : "NAO ENCONTRADO", PIN_SDA, PIN_SCL, (unsigned long)(Wire.getClock() / 1000),
    rateHz(rate), rateHz(rate) / 2, mlx.serialNumber[0], mlx.serialNumber[1], mlx.serialNumber[2], (unsigned long)i2cErrors, (unsigned long)dropped);
  statusDue = true;
}

static void statusLine() {
  bool ok = (wst == WS_CONECTADO);
  say("#J {\"dev\":\"%s\",\"fw\":\"%s\",\"wifi\":\"%s\",\"ssid\":\"%s\",\"ip\":\"%s\",\"rssi\":%d,\"ch\":%d,\"txlow\":%d,\"fails\":%u,\"reason\":%u,\"assoc\":%d,"
                "\"hub\":\"%s\",\"hubCode\":%d,\"hubMs\":%lu,\"beats\":%lu,\"hubFails\":%lu,\"netCode\":%d,\"netMs\":%lu,\"up\":%lu,"
                "\"ble\":%d,\"mtu\":%u,\"bleq\":%lu,\"bled\":%lu,\"heap\":%lu}\n",
    devId.c_str(), FW_VERSION, wName(), jsonEsc(cfgSsid).c_str(), ok ? WiFi.localIP().toString().c_str() : "", ok ? WiFi.RSSI() : 0, ok ? WiFi.channel() : 0,
    txLow ? 1 : 0, wFails, (unsigned)wReason, wAssoc ? 1 : 0, jsonEsc(cfgHub).c_str(), hubCode, (unsigned long)hubMs, (unsigned long)beats, (unsigned long)hubFails, netCode, (unsigned long)netMs,
    (unsigned long)(millis() / 1000),
    bleSub ? 2 : bleConn ? 1 : 0, (unsigned)bleMtu, (unsigned long)bleFrames, (unsigned long)bleDrops, (unsigned long)ESP.getFreeHeap());
  lastStatus = millis(); statusDue = false;
}

static void wifiStart() {
  if (!cfgSsid.length()) { wst = WS_SEM_REDE; statusDue = true; return; }
  WiFi.disconnect(true); delay(50);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(true);                          // OBRIGATÓRIO com BLE ligado: Wi-Fi e BLE dividem o rádio (sem modem-sleep o chip aborta)
  wReason = 0; wAssoc = false; wGotIp = false;
  WiFi.begin(cfgSsid.c_str(), cfgPass.c_str());
  if (txLow) WiFi.setTxPower(WIFI_POWER_8_5dBm); // SuperMini: antena fraca satura com potência cheia
  wst = WS_CONECTANDO; wT0 = millis(); statusDue = true;
  say("# wifi: conectando a '%s'%s (tentativa %u)\n", cfgSsid.c_str(), txLow ? " com potencia reduzida" : "", wFails + 1);
}

static void wifiPoll() {
  switch (wst) {
    case WS_CONECTANDO:
      if (WiFi.status() == WL_CONNECTED) {
        wst = WS_CONECTADO; wFails = 0; beatDue = probeDue = statusDue = true;
        say("# wifi: CONECTADO | ip %s | rssi %d dBm | canal %d | gw %s\n", WiFi.localIP().toString().c_str(), WiFi.RSSI(), WiFi.channel(), WiFi.gatewayIP().toString().c_str());
      } else if (millis() - wT0 > 15000) {
        int st = WiFi.status(); wFails++;
        say("# wifi: FALHOU status=%d | motivo %u = %s | associou=%d ip=%d | potencia TX %s | senha gravada com %u caracteres\n",
          st, (unsigned)wReason, reasonName(wReason), wAssoc ? 1 : 0, wGotIp ? 1 : 0, txLow ? "reduzida" : "cheia", (unsigned)cfgPass.length());
        if (wAssoc && !wGotIp) say("# wifi: ASSOCIOU mas nao recebeu IP — o problema e o DHCP do roteador, nao a senha\n");
        txLow = !txLow;   // alterna cheia/reduzida: a antena do SuperMini costuma so conectar com potencia baixa
        WiFi.disconnect(true); wst = WS_RECUO; wT0 = millis(); statusDue = true;
      }
      break;
    case WS_CONECTADO:
      if (WiFi.status() != WL_CONNECTED) { say("# wifi: caiu — reconectando\n"); wst = WS_RECUO; wT0 = millis(); statusDue = true; }
      break;
    case WS_RECUO:
      if (millis() - wT0 > 5000) wifiStart();     // recua e tenta de novo, para sempre: o sensor segue lendo
      break;
    default: break;
  }
}

static void sendBeat() {
  lastBeat = millis(); beatDue = false;
  if (wst != WS_CONECTADO || !cfgHub.length()) return;
  char body[420];
  snprintf(body, sizeof body,
    "{\"dev\":\"%s\",\"fw\":\"%s\",\"tipo\":\"batimento\",\"seq\":%lu,\"up\":%lu,\"rssi\":%d,\"ta\":%.2f,\"min\":%.2f,\"max\":%.2f,\"med\":%.2f,"
    "\"hot\":{\"x\":%d,\"y\":%d,\"t\":%.2f},\"quadros\":%u,\"erros_i2c\":%lu,\"sensor\":%d}",
    devId.c_str(), FW_VERSION, (unsigned long)beats, (unsigned long)(millis() / 1000), WiFi.RSSI(), isnan(fTa) ? 0.0f : fTa, fMin, fMax, fMean,
    hotIdx % 32, hotIdx / 32, fMax, seq, (unsigned long)i2cErrors, sensorOk ? 1 : 0);
  WiFiClient c; HTTPClient http;
  http.setConnectTimeout(2000); http.setTimeout(3000);
  uint32_t t0 = millis();
  if (http.begin(c, cfgHub + "/api/v1/thermal/ingest")) {
    http.addHeader("Content-Type", "application/json");
    hubCode = http.POST((uint8_t*)body, strlen(body));
    http.end();
  } else hubCode = -100;
  hubMs = millis() - t0;
  if (hubCode == 200) beats++; else hubFails++;
  say("# hub: POST %s/api/v1/thermal/ingest -> %d em %lu ms\n", cfgHub.c_str(), hubCode, (unsigned long)hubMs);
  statusDue = true;
}

static void probeNet() {
  lastProbe = millis(); probeDue = false;
  if (wst != WS_CONECTADO) return;
  WiFiClientSecure tls; tls.setInsecure();      // sonda GET sem segredo; pinagem de certificado entra com o ingest real (mesma pendência do VIB)
  HTTPClient http; http.setConnectTimeout(4000); http.setTimeout(5000);
  uint32_t t0 = millis();
  if (http.begin(tls, PROBE_URL)) { netCode = http.GET(); http.end(); } else netCode = -100;
  netMs = millis() - t0;
  say("# internet: GET %s -> %d em %lu ms\n", PROBE_URL, netCode, (unsigned long)netMs);
  statusDue = true;
}

static void scanNets() {
  say("# wifi-scan: inicio (o sensor pausa ~3 s)\n");
  int n = WiFi.scanNetworks();
  for (int i = 0; i < n; i++)
  {
    say("# ap %d %d %s %s\n", WiFi.RSSI(i), WiFi.channel(i), authName(WiFi.encryptionType(i)), WiFi.SSID(i).c_str());
    if (cfgSsid.length() && WiFi.SSID(i) == cfgSsid) say("# alvo: '%s' bssid %s canal %d %s %d dBm\n", cfgSsid.c_str(), WiFi.BSSIDstr(i).c_str(), WiFi.channel(i), authName(WiFi.encryptionType(i)), WiFi.RSSI(i));
  }
  say("# wifi-scan: fim, %d redes em 2,4 GHz\n", n < 0 ? 0 : n);
  WiFi.scanDelete();
}

// ---------------- comandos ----------------
static void setRate(int c) {
  uint32_t clk = I2C_HZ;
  switch (c) {
    case '1': rate = MLX90640_2_HZ;  break;
    case '2': rate = MLX90640_4_HZ;  break;
    case '4': rate = MLX90640_8_HZ;  break;
    case '8': rate = MLX90640_16_HZ; clk = 800000;  break;
    case '6': rate = MLX90640_32_HZ; clk = 1000000; break;
    default: return;
  }
  Wire.setClock(clk);
  if (sensorOk) mlx.setRefreshRate(rate);
  say("# sensor %.0f Hz = %.0f quadros/s | I2C %lu kHz\n", rateHz(rate), rateHz(rate) / 2, (unsigned long)(clk / 1000));
}

static void handleLine(char* ln, bool viaBle) {
  char cmd = ln[0];
  if (viaBle && (cmd == 'W' || cmd == 'X' || cmd == 'H')) { say("# ble: comando %c recusado — rede e hub so pela USB (enlace BLE sem cifra)\n", cmd); return; }
  char* a = strchr(ln, '\t'); char* b = NULL;
  if (a) { *a++ = 0; b = strchr(a, '\t'); if (b) *b++ = 0; }
  switch (cmd) {
    case 'S': scanNets(); break;
    case 'W':
      if (!a || !*a) { say("# wifi: faltou o SSID\n"); break; }
      cfgSsid = a; cfgPass = b ? b : "";
      prefs.begin("termica", false); prefs.putString("ssid", cfgSsid); prefs.putString("pass", cfgPass); prefs.end();
      say("# wifi: credenciais gravadas (ssid '%s', senha de %u caracteres)\n", cfgSsid.c_str(), (unsigned)cfgPass.length());
      wFails = 0; txLow = false; wifiStart();
      break;
    case 'X':
      cfgSsid = ""; cfgPass = "";
      prefs.begin("termica", false); prefs.remove("ssid"); prefs.remove("pass"); prefs.end();
      WiFi.disconnect(true, true); wst = WS_SEM_REDE; statusDue = true;
      say("# wifi: rede esquecida\n");
      break;
    case 'H':
      cfgHub = a ? a : ""; while (cfgHub.endsWith("/")) cfgHub.remove(cfgHub.length() - 1);
      prefs.begin("termica", false); prefs.putString("hub", cfgHub); prefs.end();
      say("# hub de teste: %s\n", cfgHub.length() ? cfgHub.c_str() : "(nenhum)");
      beatDue = true; statusDue = true;
      break;
    case 'T': beatDue = probeDue = true; say("# teste: batimento + sonda agora\n"); break;
    default: say("# comando desconhecido: %c\n", cmd);
  }
}

static void readCommands() {
  static char buf[200]; static size_t n = 0;
  while (Serial.available()) {
    int c = Serial.read();
    if (n == 0 && (c == 'i' || c == 'I')) { banner(); continue; }
    if (n == 0 && strchr("12486", c)) { setRate(c); continue; }
    if (c == '\n' || c == '\r') { if (n) { buf[n] = 0; handleLine(buf, false); n = 0; } continue; }
    if (n < sizeof(buf) - 1) buf[n++] = (char)c;
  }
}

static void bleCommands() {
  if (!bleCmdDue) return;
  String v = bleCmd; bleCmdDue = false; v.trim();
  if (!v.length()) return;
  if (v.length() == 1 && (v[0] == 'i' || v[0] == 'I')) { banner(); return; }
  if (v.length() == 1 && strchr("12486", v[0])) { setRate(v[0]); return; }
  char b[200]; strncpy(b, v.c_str(), sizeof b - 1); b[sizeof b - 1] = 0;
  handleLine(b, true);
}

static void bleInit() {
  BLEDevice::init(devId.c_str());
  BLEDevice::setMTU(517);
  bleSrv = BLEDevice::createServer(); bleSrv->setCallbacks(new SrvCb());
  BLEService* svc = bleSrv->createService(UUID_SVC);
  chData = svc->createCharacteristic(UUID_DATA, BLECharacteristic::PROPERTY_NOTIFY);
  chData->addDescriptor(new BLE2902()); chData->setCallbacks(new DataCb());
  chCtrl = svc->createCharacteristic(UUID_CTRL, BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  chCtrl->setCallbacks(new CtrlCb());
  svc->start();
  BLEAdvertising* adv = BLEDevice::getAdvertising();
  adv->addServiceUUID(UUID_SVC); adv->setScanResponse(true);
  adv->setMinPreferred(0x06); adv->setMaxPreferred(0x0C);
  BLEDevice::startAdvertising();
  say("# ble: anunciando como '%s' | heap livre %lu B\n", devId.c_str(), (unsigned long)ESP.getFreeHeap());
}

// ---------------- sensor / USB / BLE ----------------
static bool initSensor() {
  if (!mlx.begin(MLX_ADDR, &Wire)) return false;
  mlx.setMode(MLX90640_CHESS);
  mlx.setResolution(MLX90640_ADC_18BIT);
  mlx.setRefreshRate(rate);
  return true;
}

static void sendFrame(uint8_t flags, float ta) {
  float lo = 1e9, hi = -1e9, sum = 0; int im = 0;
  for (int i = 0; i < 768; i++) { float v = to[i]; if (v < lo) lo = v; if (v > hi) { hi = v; im = i; } sum += v; }
  fMin = lo; fMax = hi; fMean = sum / 768.0f; hotIdx = im; fTa = ta;       // resumo p/ o batimento
  seq++;
  bool usbOk = Serial.availableForWrite() >= (int)sizeof(Pkt);               // quadro inteiro ou nada
  if (!usbOk) dropped++;
  if (!usbOk && !bleSub) return;
  pkt.flags = flags; pkt.seq = seq - 1;
  pkt.ta = (ta < -100 || ta > 300 || isnan(ta)) ? 0x7FFF : (int16_t)lroundf(ta * 100.0f);
  for (int i = 0; i < 768; i++) { long v = lroundf(to[i] * 100.0f); pkt.t[i] = (int16_t)constrain(v, -32768L, 32767L); }
  const uint8_t* b = (const uint8_t*)&pkt; uint16_t s = 0;
  for (size_t k = 0; k < sizeof(Pkt) - 2; k++) s += b[k];
  pkt.sum = s;
  if (usbOk) Serial.write(b, sizeof(Pkt));
  if (bleSub) { if (bleWrite(b, sizeof(Pkt))) bleFrames++; else bleDrops++; }
}

void setup() {
  Serial.setTxBufferSize(4096);   // ANTES do begin: o padrão de 256 B truncava os quadros
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);
  pinMode(PIN_LED, OUTPUT);
  Wire.begin(PIN_SDA, PIN_SCL, I2C_HZ); Wire.setTimeOut(50);
  delay(300);

  uint8_t mac[6]; WiFi.mode(WIFI_STA); WiFi.macAddress(mac);
  char id[20]; snprintf(id, sizeof id, "termica-%02x%02x", mac[4], mac[5]); devId = id;
  prefs.begin("termica", true);
  cfgSsid = prefs.getString("ssid", ""); cfgPass = prefs.getString("pass", ""); cfgHub = prefs.getString("hub", "");
  prefs.end();

  sensorOk = initSensor();
  pkt.s0 = 0xA5; pkt.s1 = 0x5A; pkt.ver = 1;
  WiFi.onEvent(onWifiEvent);
  bleInit();
  banner();
  wifiStart();
}

void loop() {
  readCommands();
  bleCommands();
  wifiPoll();
  if (wst == WS_CONECTADO) {
    if (beatDue  || millis() - lastBeat  > BEAT_MS)  sendBeat();
    if (probeDue || millis() - lastProbe > PROBE_MS) probeNet();
  }
  if (statusDue || millis() - lastStatus > 5000) statusLine();

  if (!sensorOk) {
    digitalWrite(PIN_LED, (millis() / 100) & 1);
    if (millis() - lastRetry > 2000) {
      lastRetry = millis(); sensorOk = initSensor();
      if (sensorOk) banner(); else say("# ERRO: MLX90640 nao responde no I2C (confira 3V3, GND, SDA=8, SCL=9)\n");
    }
    delay(20);
    return;
  }
  int status = mlx.getFrame(to);
  if (status != 0) {
    i2cErrors++;
    if ((i2cErrors & 7) == 1) say("# aviso: erro I2C %d (total %lu)\n", status, (unsigned long)i2cErrors);
    if (i2cErrors % 50 == 0) { sensorOk = false; say("# reinicializando o sensor\n"); }
    delay(5);
    return;
  }
  digitalWrite(PIN_LED, seq & 1);
  sendFrame(0x01, mlx.getTa(false));
}
