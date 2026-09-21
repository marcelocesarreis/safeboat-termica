# Térmica — plano do firmware Wi-Fi (receita do VIB, sem MQTT)

Decisão de 17/09/2026: **a câmera analisa a bordo e envia só resumos e alertas por
HTTPS**, no mesmo caminho que o VIB já usa em produção. Nada de broker.

## Por que não MQTT

- O stack da SAFEBOAT não tem broker: seria um serviço novo para subir, proteger e manter.
- O VIB já resolveu o problema por HTTP e está em produção: sensor → `hub.safeboat.tech`
  → `POST /api/internal/vib/summaries` (segredo no header) → Postgres/alertas/FCM.
- O app consulta a API a cada 30 s: o "tempo real" do MQTT não chegaria ao usuário.
- Mandar 4 quadros/s crus para a nuvem é desperdício; o que importa é o alerta.

## Arquitetura

```
MLX90640 ──I²C──> ESP32-C3 (detector a bordo)
                     │  HTTPS POST (keep-alive), JSON
                     ▼
              hub.safeboat.tech        POST /api/v1/thermal/ingest
                     │  X-Thermal-Hub-Secret, idempotente por (vehicle_id, hub_event_id)
                     ▼
              api.safeboat.ai          POST /api/internal/thermal/summaries
                     │
                     ▼
        Postgres · alerta `temperatura_anormal` · push FCM com deeplink
```

O detector é o mesmo de `public/engine.js` (baseline por pixel com Welford → Δ e
z-score → blobs → persistência → zona/severidade), portado para C. Custo: média +
variância de 768 píxeis = 6 kB de RAM por baseline; a 4 Hz a CPU fica ociosa.

## O que a câmera envia

| Mensagem | Quando | Conteúdo | Tamanho |
|---|---|---|---|
| **resumo** | a cada 60 s | `dev, fw, seq, up, ta, min, max, med, p95, hot{x,y,t}, estado, blobs, rssi` | ~0,3 kB |
| **alerta** | blob confirmado (3 quadros) e a cada mudança de severidade | `ev_id, severidade, zona, cx, cy, maxT, maxD` + **quadro anexado** (768 × i16 em base64) | ~2,3 kB |
| **batimento** | a cada 600 s sem outra mensagem (valor do VIB) | `dev, fw, up, rssi, erros_i2c` | ~0,1 kB |

- `ev_id` = contador de boot + sequência → o hub deduplica reenvios (mesma ideia do `hub_event_id`).
- A **resposta** do hub carrega configuração: zonas da câmera (retângulos + nome do
  equipamento), limiares e, quando existir, o regime do motor.
- Sob demanda (resposta com `"quadro":1`), a câmera anexa um quadro ao próximo resumo —
  é o que alimenta uma miniatura no app sem fluxo contínuo.

## Consumo (estimado por datasheet — A MEDIR)

| Estado | a 12 V | Potência |
|---|---|---|
| Rádio em rajadas (resumo/min + alertas), sensor lendo | ~22–30 mA | ~0,3 W |
| Fluxo contínuo de quadros por Wi-Fi (o plano antigo) | ~45–65 mA | ~0,55–0,8 W |
| ESP em deep sleep, sensor alimentado | ~10–12 mA | ~0,13 W |
| Deep sleep + alimentação do sensor cortada (exige MOSFET) | ~1–2 mA | — |

Alimentar a câmera pelo **circuito pós-chave**: ela só tem o que ver com o motor ligado,
quando o alternador está carregando. Com isso o consumo parado deixa de existir.

## Etapas

| Versão | Entrega | Como se prova |
|---|---|---|
| **0.1.2** ✔ | USB: quadros binários + Bancada | 10 quadros reais, 0 perdidos; teste de regressão com os bytes da placa |
| **0.2** | Wi-Fi + portal de provisionamento + batimento ao hub | câmera aparece em `/fw/status` do hub |
| **0.3** | Detector a bordo (porte do `engine.js` para C) | mesmos quadros gravados → **mesmos blobs** no JS e no C (teste cruzado com fixtures) |
| **0.4** | Rota `thermal/ingest` no hub + `thermal/summaries` na API + flag `temperatura_anormal` | alerta injetado na bancada chega como push no app |
| **0.5** | OTA pelo hub + endurecimento | 1.x → 1.y pela rede, com validação pós-OTA |

## Lições do VIB que entram desde o primeiro commit

1. **Resposta HTTP pode vir `chunked`** (proxy reescreve): o dreno da resposta trata
   Content-Length **e** chunked, senão sobra lixo no socket keep-alive ("perda de Wi-Fi" que não era).
2. **POST montado direto no socket**, sem `String` — RAM previsível.
3. **OTA fora da missão**: a primeira tentativa do VIB falhou por falta de RAM no meio da análise.
4. **Falha de Wi-Fi não pode matar o sensor**: 3 falhas seguidas → recua e tenta de novo, nunca dorme para sempre.
5. **USB**: buffer TX de 4 kB e só quadro inteiro (o padrão de 256 B truncava — já corrigido na 0.1.1).

## Em aberto

- **Regime do motor.** O baseline por regime precisa saber lenta × cruzeiro. O RPM viria do
  hub, mas o bloco NMEA `motores` ainda não aparece nas leituras. Plano B sem RPM: a câmera
  só aprende/monitora com a cena **termicamente estabilizada** (média da cena parada por N minutos).
- **Zonas por câmera**: onde o instalador desenha os retângulos (app? página do hub?).
- **Medir o consumo real** — tudo acima é datasheet.
