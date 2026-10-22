/**
 * SAFEBOAT TÉRMICA — firmware "termica-expo" 0.3.0  (estande: rede própria + página com IA + WebSocket)
 *
 * Para o tótem do Boat Show: a câmera cria a PRÓPRIA rede Wi-Fi, serve a tela de exposição
 * (public/expo.html, embutida em expo_page.h por tools/build-expo.cjs) e transmite os quadros
 * por WebSocket. Um iPad dedicado entra na rede e abre http://192.168.4.1 — sem internet,
 * sem roteador, sem depender do Wi-Fi do pavilhão. Sem BLE e sem hub: rádio só para o estande.
 *
 *   rede   SAFEBOAT-THERMAL (WPA2) · 192.168.4.1          (nome/senha/canal trocáveis pela USB)
 *   :80    /            tela de exposição (gzip)
 *          /api/status  JSON de estado
 *          /manifest.json  p/ "Adicionar a Tela de Inicio" abrir em tela cheia no iPad
 *          qualquer outra rota responde "Success": o iOS acha que há internet e NÃO larga a rede
 *   :81    WebSocket — cada mensagem binária é um quadro de 1546 B, o MESMO da USB:
 *          A5 5A | ver | flags | seq | Ta×100 | 768×i16×100 | soma      (public/serial-parser.js)
 *          texto do cliente = comando de 1 caractere (1 2 4 8 6 = quadros/s)
 *
 * USB (inalterado, a Bancada continua funcionando): quadros binários + linhas "# ..." e "#J {json}"
 *   imediatos  i (minúsculo) = banner · 1 2 4 8 = quadros/s · 6 = 16 quadros/s
 *   linhas (campos separados por TAB):
 *     A <ssid> <senha>  nome e senha da rede da câmera (senha >= 8 caracteres; vazio = aberta)
 *     C <canal>         canal do ponto de acesso (1–13; use S para ver o mais vazio)
 *     P                 alterna potência TX reduzida/cheia (SuperMini: antena satura com potência cheia)
 *     I <sda> <scl>     pinos do sensor (padrão 8 9; ex. I 6 7) · D = diagnóstico elétrico do I²C
 *     S                 procura redes 2,4 GHz
 *     W <ssid> <senha>  TAMBÉM entra numa rede existente (bancada/teste); desiste sozinho se ela não existir
 *     X                 esquece a rede do W
 */
#include <Wire.h>
#include <WiFi.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <Preferences.h>
#include <Adafruit_MLX90640.h>
#include <lwip/sockets.h>
#include "mbedtls/sha1.h"
#include "mbedtls/base64.h"
#include <stdarg.h>
#include "expo_page.h"           // EXPO_PAGE_GZ[] / EXPO_PAGE_GZ_LEN — gerado: node tools/build-expo.cjs

#define FW_VERSION  "0.3.0-expo"
#define PIN_SDA     8            // também é o LED onboard do SuperMini — pisca com o I²C, normal
#define PIN_SCL     9
#define PIN_LED     10
#define MLX_ADDR    0x33
#define I2C_HZ      400000
#define AP_SSID     "SAFEBOAT-THERMAL"
#define AP_PASS     "safeboat2026"
#define AP_CHANNEL  6
#define WS_PORT     81
#define WS_MAX      4            // iPad + até 3 curiosos/testes
#define STA_TRY_MS  20000UL      // rede do W: tenta só no boot; não achou → desiste (varredura atrapalha o ponto de acesso)

Adafruit_MLX90640 mlx;
Preferences prefs;
WebServer http(80);
DNSServer dns;
WiFiServer wsSrv(WS_PORT);
static float to[768];

struct __attribute__((packed)) Pkt { uint8_t s0, s1, ver, flags; uint16_t seq; int16_t ta; int16_t t[768]; uint16_t sum; };
static Pkt pkt;

static bool     sensorOk = false;
static mlx90640_refreshrate_t rate = MLX90640_16_HZ;  // sensor 16 Hz = 8 quadros/s
static uint16_t seq = 0;
static uint32_t i2cErrors = 0, lastRetry = 0, dropped = 0, lastStatus = 0, fpsT0 = 0, fpsN = 0;
static float    fMin = 0, fMax = 0, fMean = 0, fTa = NAN, fps = 0;
static bool     statusDue = true;
static uint8_t  sensorTries = 0;
static int      pinSda = PIN_SDA, pinScl = PIN_SCL;   // trocáveis pela USB (comando I) e guardados na NVS: GPIO8 já queimou em duas placas

static String   apSsid, apPass, cfgSsid, cfgPass, devId;
static uint8_t  apChan = AP_CHANNEL; static bool txLow = true;
enum SState { ST_OFF, ST_TENTANDO, ST_OK, ST_DESISTIU };
static SState   sst = ST_OFF; static uint32_t sT0 = 0;

// ---------------- WebSocket mínimo (sem biblioteca) ----------------
// Envio NÃO bloqueante direto no socket: um iPad travado ou fora de alcance nunca segura o sensor.
// Quadro que não coube fica pendente; enquanto houver pendência os quadros novos daquele cliente são pulados.
struct WsCli {
  WiFiClient c; uint8_t st;                    // 0 livre · 1 aguardando o handshake · 2 aberto
  uint32_t t0, lastTx, sent, skipped;
  char hdr[700]; uint16_t hn;
  uint8_t rx[140]; uint8_t rn;
  uint8_t out[sizeof(Pkt) + 4]; uint16_t outLen, outPos;
};
static WsCli ws[WS_MAX];

static void say(const char* fmt, ...) {
  char b[760]; va_list ap; va_start(ap, fmt); int n = vsnprintf(b, sizeof b, fmt, ap); va_end(ap);
  if (n <= 0) return;
  if (n >= (int)sizeof b) n = sizeof b - 1;
  Serial.write((const uint8_t*)b, n);
}

static uint8_t wsCount() { uint8_t n = 0; for (auto& k : ws) if (k.st == 2) n++; return n; }
static void wsDrop(WsCli& k) { k.c.stop(); k.st = 0; statusDue = true; }

static const char* findHeader(const char* h, const char* nameLower) {     // busca sem diferenciar maiúsculas; devolve o início do valor
  size_t n = strlen(nameLower);
  for (const char* p = h; *p; p++) {
    size_t i = 0; while (i < n && p[i] && (char)tolower((unsigned char)p[i]) == nameLower[i]) i++;
    if (i == n) { p += n; while (*p == ' ') p++; return p; }
  }
  return NULL;
}

static void wsHandshake(WsCli& k) {
  const char* v = findHeader(k.hdr, "sec-websocket-key:");
  if (!v) { k.c.print("HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n"); wsDrop(k); return; }
  char cat[128]; size_t i = 0;
  while (v[i] && v[i] != '\r' && v[i] != '\n' && v[i] != ' ' && i < 60) { cat[i] = v[i]; i++; }
  strcpy(cat + i, "258EAFA5-E914-47DA-95CA-C5AB0DC85B11");
  uint8_t sha[20]; char acc[40]; size_t an = 0;
  mbedtls_sha1((const uint8_t*)cat, strlen(cat), sha);
  mbedtls_base64_encode((uint8_t*)acc, sizeof acc - 1, &an, sha, 20); acc[an] = 0;
  k.c.printf("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: %s\r\n\r\n", acc);
  k.st = 2; k.rn = 0; k.outLen = k.outPos = 0; k.sent = k.skipped = 0; k.lastTx = millis(); statusDue = true;
  say("# ws: cliente %s conectado (%u no total)\n", k.c.remoteIP().toString().c_str(), wsCount());
}

static void wsFlush(WsCli& k) {
  if (k.st != 2 || k.outPos >= k.outLen) return;
  int r = send(k.c.fd(), k.out + k.outPos, k.outLen - k.outPos, MSG_DONTWAIT);
  if (r > 0) { k.outPos += r; k.lastTx = millis(); if (k.outPos >= k.outLen) k.sent++; }
  else if (r < 0 && errno != EAGAIN && errno != EWOULDBLOCK) { wsDrop(k); return; }
  if (k.outPos < k.outLen && millis() - k.lastTx > 4000) { say("# ws: cliente parado ha 4 s — derrubado\n"); wsDrop(k); }
}

static void wsQueueFrame(const uint8_t* b, size_t n) {
  for (auto& k : ws) {
    if (k.st != 2) continue;
    if (k.outPos < k.outLen) { k.skipped++; wsFlush(k); continue; }
    k.out[0] = 0x82; k.out[1] = 126; k.out[2] = (uint8_t)(n >> 8); k.out[3] = (uint8_t)n;   // binário, FIN, sem máscara
    memcpy(k.out + 4, b, n); k.outLen = n + 4; k.outPos = 0;
    wsFlush(k);
  }
}

static void setRate(int c);
static void wsRead(WsCli& k) {                   // só quadros curtos do cliente: fechar, ping e comando de 1 caractere
  while (k.c.available() && k.rn < sizeof k.rx) k.rx[k.rn++] = (uint8_t)k.c.read();
  while (k.rn >= 2) {
    uint8_t op = k.rx[0] & 0x0F, len = k.rx[1] & 0x7F; bool masked = k.rx[1] & 0x80;
    if (len >= 126) { wsDrop(k); return; }
    uint8_t need = 2 + (masked ? 4 : 0) + len;
    if (k.rn < need) return;
    uint8_t* p = k.rx + 2 + (masked ? 4 : 0);
    if (masked) for (uint8_t i = 0; i < len; i++) p[i] ^= k.rx[2 + (i & 3)];
    if (op == 0x8) { wsDrop(k); return; }
    if (op == 0x9 && k.outPos >= k.outLen) { uint8_t h[2] = { 0x8A, len }; k.c.write(h, 2); k.c.write(p, len); }
    if (op == 0x1 && len >= 1 && strchr("12486", p[0])) setRate(p[0]);
    memmove(k.rx, k.rx + need, k.rn - need); k.rn -= need;
  }
}

static void wsPoll() {
  WiFiClient n = wsSrv.accept();
  if (n) {
    WsCli* slot = NULL;
    for (auto& k : ws) if (k.st == 0 || !k.c.connected()) { slot = &k; break; }
    if (!slot) n.stop();
    else { slot->c.stop(); slot->c = n; slot->c.setNoDelay(true); slot->st = 1; slot->t0 = millis(); slot->hn = 0; }
  }
  for (auto& k : ws) {
    if (k.st == 0) continue;
    if (!k.c.connected()) { wsDrop(k); continue; }
    if (k.st == 1) {
      while (k.c.available() && k.hn < sizeof k.hdr - 1) k.hdr[k.hn++] = (char)k.c.read();
      k.hdr[k.hn] = 0;
      if (strstr(k.hdr, "\r\n\r\n")) wsHandshake(k);
      else if (millis() - k.t0 > 3000 || k.hn >= sizeof k.hdr - 1) wsDrop(k);
    } else { wsRead(k); wsFlush(k); }
  }
}

// ---------------- HTTP ----------------
static float rateHz(mlx90640_refreshrate_t r) { return 0.5f * (1 << (int)r); }
static String jsonEsc(const String& s) {
  String o; o.reserve(s.length() + 4);
  for (size_t i = 0; i < s.length(); i++) { char c = s[i]; if (c == '"' || c == '\\') o += '\\'; if ((uint8_t)c >= 32) o += c; }
  return o;
}
static const char* sName() { switch (sst) { case ST_OFF: return "sem_rede"; case ST_TENTANDO: return "conectando"; case ST_OK: return "ok"; default: return "falhou"; } }

static size_t statusJson(char* b, size_t n) {
  return snprintf(b, n, "{\"dev\":\"%s\",\"fw\":\"%s\",\"ap\":\"%s\",\"apip\":\"%s\",\"ch\":%d,\"txlow\":%d,\"sta\":%u,\"ws\":%u,"
    "\"wifi\":\"%s\",\"ssid\":\"%s\",\"ip\":\"%s\",\"rssi\":%d,\"sensor\":%d,\"fps\":%.1f,\"ta\":%.2f,\"min\":%.2f,\"max\":%.2f,\"med\":%.2f,"
    "\"erros_i2c\":%lu,\"up\":%lu,\"heap\":%lu,\"chip\":%.1f,\"mhz\":%u}",
    devId.c_str(), FW_VERSION, jsonEsc(apSsid).c_str(), WiFi.softAPIP().toString().c_str(), WiFi.channel(), txLow ? 1 : 0, (unsigned)WiFi.softAPgetStationNum(), (unsigned)wsCount(),
    sName(), jsonEsc(cfgSsid).c_str(), sst == ST_OK ? WiFi.localIP().toString().c_str() : "", sst == ST_OK ? WiFi.RSSI() : 0,
    sensorOk ? 1 : 0, fps, isnan(fTa) ? 0.0f : fTa, fMin, fMax, fMean, (unsigned long)i2cErrors, (unsigned long)(millis() / 1000), (unsigned long)ESP.getFreeHeap(), temperatureRead(), (unsigned)getCpuFrequencyMhz());   // chip = sensor interno do ESP32-C3, termômetro do interior do case
}

static void httpInit() {
  http.on("/", []() {
    http.sendHeader("Content-Encoding", "gzip");
    http.sendHeader("Cache-Control", "no-store");
    http.send_P(200, "text/html; charset=utf-8", (const char*)EXPO_PAGE_GZ, EXPO_PAGE_GZ_LEN);
  });
  http.on("/api/status", []() {
    char b[640]; statusJson(b, sizeof b);
    http.sendHeader("Access-Control-Allow-Origin", "*"); http.sendHeader("Cache-Control", "no-store");
    http.send(200, "application/json", b);
  });
  http.on("/manifest.json", []() {   // iPadOS 16.4+: só abre em tela cheia pela Tela de Inicio se houver manifesto
    http.sendHeader("Cache-Control", "no-store");
    http.send(200, "application/manifest+json", "{\"name\":\"SAFEBOAT T\u00e9rmica\",\"short_name\":\"T\u00e9rmica\",\"start_url\":\"/\",\"scope\":\"/\",\"display\":\"fullscreen\",\"orientation\":\"landscape\",\"background_color\":\"#070c16\",\"theme_color\":\"#070c16\"}");
  });
  http.on("/generate_204", []() { http.send(204, "text/plain", ""); });
  // sondas de portal cativo (captive.apple.com/hotspot-detect.html etc.): "Success" = o iPad considera a rede boa e fica nela
  http.onNotFound([]() { http.send(200, "text/html", "<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>"); });
  http.begin();
}

// ---------------- Wi-Fi ----------------
static void apStart() {
  WiFi.mode(WIFI_AP_STA);                      // STA ociosa não varre; existe só para o S e para o W
  WiFi.setSleep(false);                        // sem BLE: rádio inteiro para o estande
  bool ok = WiFi.softAP(apSsid.c_str(), apPass.length() >= 8 ? apPass.c_str() : NULL, apChan, 0, WS_MAX + 2);
  WiFi.setTxPower(txLow ? WIFI_POWER_8_5dBm : WIFI_POWER_19_5dBm);
  dns.setErrorReplyCode(DNSReplyCode::NoError);
  dns.start(53, "*", WiFi.softAPIP());
  say("# ap: %s '%s' %s | canal %d | http://%s | potencia TX %s\n", ok ? "NO AR" : "FALHOU", apSsid.c_str(), apPass.length() >= 8 ? "WPA2" : "ABERTA", apChan,
    WiFi.softAPIP().toString().c_str(), txLow ? "reduzida" : "cheia");
}

static void staStart() {
  if (!cfgSsid.length()) { sst = ST_OFF; return; }
  WiFi.setAutoReconnect(true);
  WiFi.begin(cfgSsid.c_str(), cfgPass.c_str());
  sst = ST_TENTANDO; sT0 = millis(); statusDue = true;
  say("# wifi: tentando tambem a rede '%s' (desiste em %lu s)\n", cfgSsid.c_str(), STA_TRY_MS / 1000);
}

static void staPoll() {
  if (sst == ST_TENTANDO) {
    if (WiFi.status() == WL_CONNECTED) { sst = ST_OK; statusDue = true; say("# wifi: CONECTADO a '%s' | http://%s | rssi %d dBm | canal %d (o ponto de acesso acompanha este canal)\n", cfgSsid.c_str(), WiFi.localIP().toString().c_str(), WiFi.RSSI(), WiFi.channel()); }
    else if (millis() - sT0 > STA_TRY_MS) { WiFi.setAutoReconnect(false); WiFi.disconnect(false); sst = ST_DESISTIU; statusDue = true; say("# wifi: '%s' nao apareceu — sigo so com a rede propria\n", cfgSsid.c_str()); }
  } else if (sst == ST_OK && WiFi.status() != WL_CONNECTED && millis() - sT0 > 5000) { sT0 = millis(); statusDue = true; }   // o driver reconecta sozinho
}

static const char* authName(wifi_auth_mode_t a) {
  switch (a) {
    case WIFI_AUTH_OPEN: return "aberta";       case WIFI_AUTH_WPA_PSK: return "WPA";
    case WIFI_AUTH_WPA2_PSK: return "WPA2";     case WIFI_AUTH_WPA_WPA2_PSK: return "WPA/WPA2";
    case WIFI_AUTH_WPA3_PSK: return "WPA3";     case WIFI_AUTH_WPA2_WPA3_PSK: return "WPA2/WPA3";
    default: return "outra";
  }
}
static void scanNets() {
  say("# wifi-scan: inicio (imagem e rede pausam ~3 s)\n");
  int n = WiFi.scanNetworks(); int porCanal[14] = { 0 };
  for (int i = 0; i < n; i++) { say("# ap %d %d %s %s\n", WiFi.RSSI(i), WiFi.channel(i), authName(WiFi.encryptionType(i)), WiFi.SSID(i).c_str()); if (WiFi.channel(i) <= 13) porCanal[WiFi.channel(i)]++; }
  say("# wifi-scan: fim, %d redes | por canal: 1=%d 6=%d 11=%d (use C <canal> para mudar o da camera)\n", n < 0 ? 0 : n, porCanal[1], porCanal[6], porCanal[11]);
  WiFi.scanDelete();
}

// ---------------- comandos ----------------
static void banner() {
  say("# SAFEBOAT Termica termica-expo %s | %s | MLX90640 @0x%02X %s SDA=%d SCL=%d | sensor %.0f Hz = %.0f quadros/s | sn %04X%04X%04X | erros I2C %lu | rede '%s' http://%s | pagina %u B gzip\n",
    FW_VERSION, devId.c_str(), MLX_ADDR, sensorOk ? "OK" : "NAO ENCONTRADO", pinSda, pinScl, rateHz(rate), rateHz(rate) / 2,
    mlx.serialNumber[0], mlx.serialNumber[1], mlx.serialNumber[2], (unsigned long)i2cErrors, apSsid.c_str(), WiFi.softAPIP().toString().c_str(), (unsigned)EXPO_PAGE_GZ_LEN);
  statusDue = true;
}

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

static void handleLine(char* ln) {
  char cmd = ln[0];
  char* a = strchr(ln, '\t'); char* b = NULL;
  if (a) { *a++ = 0; b = strchr(a, '\t'); if (b) *b++ = 0; }
  switch (cmd) {
    case 'A':
      if (!a || !*a) { say("# ap: faltou o nome da rede\n"); break; }
      if (b && *b && strlen(b) < 8) { say("# ap: a senha precisa de 8 caracteres ou mais (ou vazio para rede aberta)\n"); break; }
      apSsid = a; apPass = b ? b : "";
      prefs.begin("expo", false); prefs.putString("ssid", apSsid); prefs.putString("pass", apPass); prefs.end();
      say("# ap: gravado — reiniciando a rede\n"); apStart(); break;
    case 'C': {
      int ch = a ? atoi(a) : 0;
      if (ch < 1 || ch > 13) { say("# ap: canal de 1 a 13\n"); break; }
      apChan = ch; prefs.begin("expo", false); prefs.putUChar("ch", apChan); prefs.end(); apStart(); break; }
    case 'P':
      txLow = !txLow; prefs.begin("expo", false); prefs.putBool("txlow", txLow); prefs.end();
      WiFi.setTxPower(txLow ? WIFI_POWER_8_5dBm : WIFI_POWER_19_5dBm);
      say("# ap: potencia TX %s\n", txLow ? "reduzida (8,5 dBm)" : "cheia (19,5 dBm)"); statusDue = true; break;
    case 'S': scanNets(); break;
    case 'F': {   // F 80 | F 160: clock da CPU (80 MHz esquenta menos — o case fechado chegou a 69 C no chip)
      int m = a ? atoi(a) : 160; if (m != 80 && m != 160) { say("# cpu: use F 80 ou F 160\n"); break; }
      prefs.begin("expo", false); prefs.putUChar("mhz", m); prefs.end(); setCpuFrequencyMhz(m);
      say("# cpu: %d MHz (gravado)\n", getCpuFrequencyMhz()); statusDue = true; break; }
    case 'I': {   // I <sda> <scl>: muda os pinos do sensor (ex. I 6 7) e grava; sem argumentos volta ao padrão 8/9
      int a1 = a ? atoi(a) : PIN_SDA, b1 = b ? atoi(b) : PIN_SCL;
      if (a1 < 0 || a1 > 21 || b1 < 0 || b1 > 21 || a1 == b1) { say("# sensor: pinos invalidos (0-21, diferentes)\n"); break; }
      pinSda = a1; pinScl = b1; prefs.begin("expo", false); prefs.putChar("sda", a1); prefs.putChar("scl", b1); prefs.end();
      sensorOk = false; sensorTries = 0; lastRetry = 0; say("# sensor: procurando o MLX90640 em SDA=%d SCL=%d (gravado)\n", pinSda, pinScl); break; }
    case 'R': {   // destravamento agressivo do barramento: SCL lento por 64 ciclos, SCL preso em 0 por 40 ms, STOP, e sonda
      Wire.end();
      pinMode(pinSda, INPUT_PULLUP); pinMode(pinScl, OUTPUT_OPEN_DRAIN); digitalWrite(pinScl, HIGH); delay(2);
      say("# recup: antes SDA=%d\n", digitalRead(pinSda));
      for (int k = 0; k < 64; k++) { digitalWrite(pinScl, LOW); delayMicroseconds(100); digitalWrite(pinScl, HIGH); delayMicroseconds(100); if (digitalRead(pinSda)) { say("# recup: SDA soltou no pulso %d\n", k + 1); break; } }
      if (!digitalRead(pinSda)) { digitalWrite(pinScl, LOW); delay(40); digitalWrite(pinScl, HIGH); delay(2); say("# recup: apos SCL preso 40 ms SDA=%d\n", digitalRead(pinSda)); }
      pinMode(pinSda, OUTPUT_OPEN_DRAIN); digitalWrite(pinSda, LOW); delayMicroseconds(100); digitalWrite(pinSda, HIGH); delayMicroseconds(100);   // STOP
      pinMode(pinSda, INPUT_PULLUP); delay(2);
      Wire.begin(pinSda, pinScl, 100000); Wire.setTimeOut(20); Wire.beginTransmission(MLX_ADDR); int rc = Wire.endTransmission();
      say("# recup: depois SDA=%d | sonda 0x33 -> %d (0 = respondeu)\n", digitalRead(pinSda), rc);
      sensorOk = false; sensorTries = 0; lastRetry = 0; break; }
    case 'D': {   // diagnóstico elétrico do I²C: nível das linhas soltas/puxadas + varredura de endereços
      Wire.end();
      int pins[2] = { pinSda, pinScl }; const char* nm[2] = { "SDA", "SCL" };
      for (int i = 0; i < 2; i++) {
        pinMode(pins[i], INPUT); delay(5); int solto = digitalRead(pins[i]);
        pinMode(pins[i], INPUT_PULLDOWN); delay(5); int baixo = digitalRead(pins[i]);
        pinMode(pins[i], INPUT_PULLUP); delay(5); int alto = digitalRead(pins[i]);
        // forçado: o pino empurra 3,3 V por 20 us e lê o próprio pad. 1 = o pad funciona e o que segura a linha é fraco (driver de
        // um chip); 0 = curto duro com GND (ponte de solda, fio prensado) ou pad morto
        pinMode(pins[i], OUTPUT); digitalWrite(pins[i], HIGH); delayMicroseconds(20); int forcado = digitalRead(pins[i]); pinMode(pins[i], INPUT_PULLUP);
        say("# diag: %s GPIO%d | solto=%d | com pull-down interno=%d | com pull-up interno=%d | forcado a 1 le=%d | %s\n", nm[i], pins[i], solto, baixo, alto, forcado,
          !alto ? "PRESA EM 0: curto com GND ou sensor segurando a linha" : baixo ? "ha pull-up externo energizado (modulo ligado ao 3V3)" : "SEM pull-up externo: fio solto, VIN sem 3V3 ou modulo sem resistores");
      }
      Wire.begin(pinSda, pinScl, 100000); Wire.setTimeOut(20); int n = 0;
      for (uint8_t a = 8; a < 120; a++) { Wire.beginTransmission(a); if (Wire.endTransmission() == 0) { say("# diag: dispositivo em 0x%02X\n", a); n++; } }
      say("# diag: %d dispositivo(s) no barramento (o MLX90640 e o 0x33)\n", n);
      sensorOk = false; break; }
    case 'W':
      if (!a || !*a) { say("# wifi: faltou o SSID\n"); break; }
      cfgSsid = a; cfgPass = b ? b : "";
      prefs.begin("termica", false); prefs.putString("ssid", cfgSsid); prefs.putString("pass", cfgPass); prefs.end();
      say("# wifi: credenciais gravadas (ssid '%s', senha de %u caracteres)\n", cfgSsid.c_str(), (unsigned)cfgPass.length());
      staStart(); break;
    case 'X':
      cfgSsid = ""; cfgPass = "";
      prefs.begin("termica", false); prefs.remove("ssid"); prefs.remove("pass"); prefs.end();
      WiFi.setAutoReconnect(false); WiFi.disconnect(false); sst = ST_OFF; statusDue = true;
      say("# wifi: rede esquecida — so a rede propria\n"); break;
    default: say("# comando desconhecido: %c\n", cmd);
  }
}

static void readCommands() {
  static char buf[200]; static size_t n = 0;
  while (Serial.available()) {
    int c = Serial.read();
    if (n == 0 && c == 'i') { banner(); continue; }   // só minúsculo: 'I' maiúsculo é o comando de pinos
    if (n == 0 && strchr("12486", c)) { setRate(c); continue; }
    if (c == '\n' || c == '\r') { if (n) { buf[n] = 0; handleLine(buf); n = 0; } continue; }
    if (n < sizeof(buf) - 1) buf[n++] = (char)c;
  }
}

// ---------------- sensor ----------------
// 1ª tentativa = caminho já provado (Wire.begin + mlx.begin, igual ao termica 0.2.8). Nas seguintes, se a SDA estiver
// presa em 0 (sensor parado no meio de uma leitura porque a placa reiniciou), 18 pulsos em SCL + STOP soltam a linha.
static bool initSensor() {
  Wire.end();
  if (sensorTries++ > 0) {
    pinMode(pinSda, INPUT_PULLUP); delay(2);
    if (!digitalRead(pinSda)) {
      pinMode(pinScl, OUTPUT_OPEN_DRAIN);
      for (int i = 0; i < 18; i++) { digitalWrite(pinScl, LOW); delayMicroseconds(40); digitalWrite(pinScl, HIGH); delayMicroseconds(40); }
      pinMode(pinSda, OUTPUT_OPEN_DRAIN); digitalWrite(pinSda, LOW); delayMicroseconds(40); digitalWrite(pinSda, HIGH); delayMicroseconds(40);
    }
  }
  Wire.begin(pinSda, pinScl, I2C_HZ); Wire.setTimeOut(50);
  if (!mlx.begin(MLX_ADDR, &Wire)) return false;
  mlx.setMode(MLX90640_CHESS);
  mlx.setResolution(MLX90640_ADC_18BIT);
  mlx.setRefreshRate(rate);
  return true;
}

static void sendFrame(uint8_t flags, float ta) {
  float lo = 1e9, hi = -1e9, sum = 0;
  for (int i = 0; i < 768; i++) { float v = to[i]; if (v < lo) lo = v; if (v > hi) hi = v; sum += v; }
  fMin = lo; fMax = hi; fMean = sum / 768.0f; fTa = ta;
  seq++; fpsN++;
  if (millis() - fpsT0 >= 2000) { fps = fpsN * 1000.0f / (millis() - fpsT0); fpsT0 = millis(); fpsN = 0; }
  bool usbOk = Serial.availableForWrite() >= (int)sizeof(Pkt);               // quadro inteiro ou nada
  if (!usbOk) dropped++;
  if (!usbOk && !wsCount()) return;
  pkt.flags = flags; pkt.seq = seq - 1;
  pkt.ta = (ta < -100 || ta > 300 || isnan(ta)) ? 0x7FFF : (int16_t)lroundf(ta * 100.0f);
  for (int i = 0; i < 768; i++) { long v = lroundf(to[i] * 100.0f); pkt.t[i] = (int16_t)constrain(v, -32768L, 32767L); }
  const uint8_t* b = (const uint8_t*)&pkt; uint16_t s = 0;
  for (size_t k = 0; k < sizeof(Pkt) - 2; k++) s += b[k];
  pkt.sum = s;
  if (usbOk) Serial.write(b, sizeof(Pkt));
  wsQueueFrame(b, sizeof(Pkt));
}

static void led(bool on) { if (pinSda != PIN_LED && pinScl != PIN_LED) { pinMode(PIN_LED, OUTPUT); digitalWrite(PIN_LED, on); } }
static void netPoll() { dns.processNextRequest(); http.handleClient(); wsPoll(); staPoll(); }

void setup() {
  Serial.setTxBufferSize(4096);   // ANTES do begin: o padrão de 256 B truncava os quadros
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);
  delay(300);

  uint8_t mac[6]; WiFi.mode(WIFI_AP_STA); WiFi.macAddress(mac);
  char id[20]; snprintf(id, sizeof id, "termica-%02x%02x", mac[4], mac[5]); devId = id;
  prefs.begin("expo", true);
  apSsid = prefs.getString("ssid", AP_SSID); apPass = prefs.getString("pass", AP_PASS);
  apChan = prefs.getUChar("ch", AP_CHANNEL); txLow = prefs.getBool("txlow", true);
  pinSda = prefs.getChar("sda", PIN_SDA); pinScl = prefs.getChar("scl", PIN_SCL);
  { uint8_t m = prefs.getUChar("mhz", 160); if (m == 80) setCpuFrequencyMhz(80); }
  prefs.end();
  prefs.begin("termica", true);   // mesma rede que o firmware "termica" já guardou pela Bancada
  cfgSsid = prefs.getString("ssid", ""); cfgPass = prefs.getString("pass", "");
  prefs.end();

  sensorOk = initSensor();
  pkt.s0 = 0xA5; pkt.s1 = 0x5A; pkt.ver = 1;
  apStart();
  httpInit();
  wsSrv.begin(); wsSrv.setNoDelay(true);
  setRate(getCpuFrequencyMhz() >= 160 ? '8' : '4');
  banner();
  staStart();
}

void loop() {
  readCommands();
  netPoll();
  if (statusDue || millis() - lastStatus > 5000) { char b[640]; statusJson(b, sizeof b); say("#J %s\n", b); lastStatus = millis(); statusDue = false; }

  if (!sensorOk) {
    led((millis() / 100) & 1);
    if (millis() - lastRetry > 2000) {
      lastRetry = millis(); sensorOk = initSensor();
      if (sensorOk) { setRate(getCpuFrequencyMhz() >= 160 ? '8' : '4'); banner(); } else say("# ERRO: MLX90640 nao responde no I2C (confira 3V3, GND, SDA=8, SCL=9)\n");
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
  led(seq & 1);
  sendFrame(0x01, mlx.getTa(false));
}
