# SAFEBOAT Térmica — quanto cobrar por câmera (pesquisa de precificação)

Data: 22/09/2026 · Padrão de referência: o modelo do VIB no sistema de propostas (`safeboat-proposta/index.html`).

## 1. O padrão do VIB (o que já está no ar)

| Item | VIB (B2C) | VIB Frota (B2B) | Câmera de segurança (Intelbras) | Kit base SAFEBOAT |
|---|---|---|---|---|
| Implementação | **R$ 600 por máquina** (cobre o hardware) | R$ 600 | preço unitário + 15 % (R$ 472,93) | conforme a rede |
| Assinatura mensal | **R$ 49,90 / máquina** | R$ 39,90 (gestor revende a R$ 49,90) | R$ 29,90 / câmera | R$ 249 |
| Assinatura anual | R$ 499 (regra dos 10 meses) | R$ 399 | R$ 299 | R$ 2.490 |
| Vendido avulso? | sim (#VIBSOLO) | — | não (exige kit) | — |

Regras que a Térmica deve herdar para caber no mesmo gerador de propostas e nos mesmos planos do Mercado Pago:
implementação única por unidade que cobre o hardware · assinatura por unidade · anual = 10 mensalidades · B2B com
desconto de ~20 % e revenda ao preço B2C · marcador `#TER=n` na composição do kit, como `#VIB=n` e `#CAM=n`.

## 2. Custo da nossa câmera (BOM da página do projeto, `public/index.html` § Compras)

| Componente | Custo estimado |
|---|---|
| Sensor MLX90640-BAB (módulo I²C) | R$ 400–600 no Brasil · R$ 200–350 no AliExpress (US$ 79–98 em 09/2026) |
| ESP32-C3 SuperMini | R$ 25–40 |
| Alimentação (buck MP1584 + TVS) | R$ 15 |
| Janela de germânio Ø25 mm AR/DLC | US$ 30–60 (≈ R$ 160–330 posto) — único item importado sem opção nacional |
| Vedação (prensa-cabo, SP13, O-ring, Sikaflex, sílica) | R$ 160 |
| Fixação, cabo marítimo 10 m, fusível, VHB | R$ 105 |
| Impressão ASA + epóxi + verniz (rateado) | R$ 30 |
| **Total por câmera** | **R$ 650–850** (sensor nacional + germânio) · **R$ 400–600** com sensor do AliExpress |

Fora da BOM: 1–2 h de instalação a bordo por câmera (cabo até o circuito pós-chave, fixação, mira, desenho das
zonas no app) e o hub, que o kit base já leva. Comparando com o VIB (hardware ≈ R$ 150–250 dentro de uma
implementação de R$ 600), a Térmica custa **3–4× mais em material**: a implementação de R$ 600 não cobre.

## 3. O que o mercado cobra

### 3.1 A régua direta: câmera térmica fixa para praça de máquinas
- **FLIR MTMS (AX8 marítima, E70321)** — 80×60 px, alarme por limiar, mostra no chartplotter Garmin/Raymarine.
  MSRP **US$ 1.359,99**; varejo US$ 1.197–1.240 ([ShipSound](https://shipsound.com/products/flir-mtms-maritime-thermal-monitoring-system-e70321),
  [International Marine Service](https://internationalmarineservice.com/products/flir-mtms-maritime-thermal-monitoring-system-e70321),
  [FLIR](https://marine.flir.com/en-us/marine-cameras/monitoring/flir-mtms)). Chegando ao Brasil com câmbio ≈ R$ 5,4 e
  imposto de importação + ICMS (≈ 60–90 % sobre o valor), **R$ 11–14 mil por câmera**, sem instalação, sem IA, sem
  aprendizado de baseline, sem app nem nuvem — só "acima de X °C, apita". Fora da náutica, o AX8 industrial custa
  ≈ € 1.099 ([RS Italia](https://it.rs-online.com/web/p/termocamere/8938489)).
- **Sistemas de detecção/supressão de incêndio para iates**: US$ 10–30 mil só a integração da praça de máquinas
  ([Dockside Pros](https://docksidepros.com/boat-maintenance/yacht-fire-detection-systems/)). Detectam o fogo; não o antecipam.

### 3.2 Manutenção preditiva industrial (o que a Térmica + VIB entregam, em escala de fábrica)
- **Augury**: US$ 50–150 por máquina por mês + sensor US$ 500–1.200 + instalação US$ 200–500 por ponto
  ([MachineCDN, 2026](https://www.machinecdn.com/blog/augury-pricing-2026/)). Em reais: **R$ 270–810/mês por ponto**.
- **Tractian**: preço de sensor sob consulta; o CMMS vai de R$ 306 a R$ 510 por usuário/mês
  ([Comparar Software](https://www.compararsoftware.com.br/tractian-es)); a própria Tractian vende "payback em 3 meses"
  ([Tractian](https://tractian.com/en/solutions/condition-monitoring/vibration-sensor/pricing)).
- É o argumento que a página do VIB já usa: "mesma classe de análise, sem mensalidade industrial por ponto".

### 3.3 Monitoramento de barco por assinatura (teto de aceitação do dono de lancha)
| Serviço | Hardware | Assinatura | O que monitora |
|---|---|---|---|
| Siren Marine | — | US$ 22/mês ou US$ 225/ano ([Siren](https://sirenmarine.com/products/monthly-subscription)) | bateria, porão, GPS, geofence |
| Garmin OnDeck | ≈ US$ 500 | US$ 12,99/mês (anual) ou US$ 19,99 avulso ([Garmin](https://www.garmin.com/en-US/blog/marine/connect-to-your-boat-from-virtually-anywhere-with-garmin-ondeck/)) | idem + 5 relés |
| Boat Command | US$ 299 + US$ 29/sensor | US$ 9/mês ([SAIL](https://sailmagazine.com/diy/boat-monitoring-system/)) | idem |
| Sentinel Marine | US$ 449 | US$ 149/ano ([SAIL](https://sailmagazine.com/diy/boat-monitoring-system/)) | idem |

Nenhum deles enxerga o motor. O mercado náutico de consumo aceita **US$ 9–22/mês (R$ 50–120)** por monitoramento
básico; o kit SAFEBOAT a R$ 249/mês já está acima disso porque entrega mais. Um adicional na casa dos R$ 50 por
"sentido" novo fica dentro do que o dono já reconhece como preço de assinatura náutica.

### 3.4 O tamanho do problema que a câmera evita
- **55 % dos incêndios a bordo são elétricos e 24 % são superaquecimento de motor/transmissão** (análise de sinistros
  BoatUS/Seaworthy — [Vessel Vanguard](https://vesselvanguard.com/analyzing-electrical-fires-on-boats/),
  [BoatUS](https://www.boatus.com/expert-advice/expert-advice-archive/2021/february/analyzing-onboard-fire-claims)): **~80 % dos
  incêndios têm um precursor térmico** que uma câmera na praça de máquinas e outra no quadro elétrico veriam antes.
  86 % dos incêndios em barcos começam no compartimento do motor
  ([Ecosafety](https://ecosafety.com.br/sistema-de-incendio-para-lanchas/)).
- **Seguro de lancha no Brasil custa 0,6–2 % do valor do casco por ano**
  ([Bombarco](https://www.bombarco.com.br/editorial/noticias/quanto-custa-o-seguro-de-uma-lancha/)): numa lancha de
  R$ 600 mil, R$ 3,6–12 mil/ano. A Térmica a R$ 499/ano é **4–14 % do prêmio** — e é argumento para negociar franquia
  e prêmio com a seguradora (dado de manutenção auditável, mesma tese do VIB).
- Custos de reparo (turbina, coletor de escape, alternador) não foram obtidos com fonte pública confiável nesta pesquisa
  (Mercado Livre bloqueia leitura automática); usar os valores das notas de oficina dos clientes da SAFEBOAT.

## 4. Recomendação

### 4.1 Preço por câmera (mesmo padrão do VIB)

| | Térmica (B2C) | Térmica Frota (B2B) |
|---|---|---|
| **Implementação** | **R$ 1.190 por câmera** (cobre hardware R$ 650–850 + instalação + margem) · kit 2 câmeras R$ 2.190 · kit 3 câmeras R$ 2.990 | idem (instalação em lote pode dar R$ 990) |
| **Assinatura mensal** | **R$ 49,90 a 1ª câmera + R$ 25,00 cada adicional** → 1 = R$ 49,90 · 2 = R$ 74,90 · 3 = R$ 99,90 | R$ 39,90 + R$ 20,00 (revende a 49,90 + 25,00) |
| **Assinatura anual** | 10 mensalidades: R$ 499 · R$ 749 · R$ 999 | R$ 399 · R$ 599 · R$ 799 |
| Vendida avulsa? | sim, como o VIB (#TERSOLO): implementação + assinatura das câmeras, sem o kit base | — |

Por que assim:
1. **R$ 49,90 é o número que a SAFEBOAT já ensinou** (flyer do Boat Show: "R$ 49,90/mês o VIB por motor"). "Cada sentido
   a bordo custa R$ 49,90" é uma frase só para o vendedor — Térmica vê, VIB sente.
2. **Degressivo na 2ª e 3ª câmera** porque o valor para o cliente está no barco coberto (motor + quadro elétrico +
   gerador/baterias), não na câmera isolada; cobrar R$ 150/mês por três câmeras trava a venda do kit, e o custo marginal
   de nuvem por câmera é desprezível (a câmera manda resumos de 0,3 kB/min, não vídeo).
3. **Acima da câmera de segurança (R$ 29,90)** porque há IA e diagnóstico, e no mesmo patamar do VIB porque é o mesmo
   tipo de entrega (alerta preditivo por máquina).
4. **Implementação de R$ 1.190** segue a regra do VIB (hardware + ~R$ 400 de instalação/margem): com sensor nacional e
   germânio a margem bruta fica em R$ 340–540 por câmera; com sensor do AliExpress, R$ 590–790. Não vender a
   implementação a R$ 600: com a BOM atual daria prejuízo em material.
5. **Ancoragem**: 1 câmera instalada e com 1 ano de IA custa R$ 1.689 — cerca de **1/7 de uma FLIR MTMS posta no
   Brasil**, que não tem IA nem app. Três câmeras com 1 ano: R$ 3.989, ainda abaixo de meia FLIR.

### 4.2 Unit economics por barco (2 câmeras, B2C, mensal)
- Receita ano 1: R$ 2.190 + 12 × R$ 74,90 = **R$ 3.089**; anos seguintes R$ 899/ano.
- Custo direto: hardware R$ 1.300–1.700 + instalação ≈ R$ 300 + nuvem/suporte ≈ R$ 5/mês por câmera.
- Margem de contribuição ano 1 ≈ R$ 1.000–1.400; LTV de 3 anos ≈ R$ 4.900 com margem ≈ R$ 2.700–3.100.
- Ponto de atenção: o **germânio** (US$ 30–60, 2–6 semanas do AliExpress) é o item que pode furar o custo; travar
  fornecedor e comprar em lote de 20 antes de abrir a venda.

### 4.3 Oferta de lançamento (Boat Show)
- "Térmica Solo": implementação **R$ 990** (em vez de R$ 1.190) para as primeiras 20 câmeras, assinatura normal.
  Mantém margem se o sensor vier do AliExpress; serve para fechar no estande e gerar os primeiros baselines reais.
- Combo "Motor completo" (Térmica + VIB na mesma máquina): R$ 89,90/mês (R$ 10 de desconto no par).

### 4.4 Alternativas consideradas
- **A. R$ 49,90 fixo por câmera, sem degressivo** — mais simples, idêntico ao VIB; rejeitada porque o kit de 3 câmeras
  vai a R$ 399/mês com o base, e o dono de lancha compara com Siren/Garmin (R$ 70–120/mês total).
- **B. Preço por barco (R$ 99,90 até 3 câmeras)** — simples para o cliente, mas quem tem 1 câmera paga o mesmo que 3 e
  não incentiva o upgrade; possível como "plano Praça de Máquinas" no futuro.
- **C. Cobrar só assinatura e dar a câmera em comodato** (modelo Augury/Tractian) — exige caixa para R$ 700–850 por
  câmera antecipados e prende 18–24 meses de contrato; não combina com o estágio atual.

## 5. Próximos passos
1. Validar a BOM real com as 3 primeiras câmeras montadas (custo do germânio posto, tempo de instalação a bordo).
2. Incluir `#TER=n` / `#TERSOLO` no gerador de propostas com as constantes acima e criar os planos de recorrência
   no Mercado Pago (49,90 · 74,90 · 99,90 e os múltiplos por máquina + câmera).
3. Levantar 3 notas reais de reparo por superaquecimento (turbina, coletor, alternador) com clientes para o argumento de ROI.
4. Depois de 6 meses de campo: revisar o degressivo com base em quantas câmeras por barco os clientes de fato instalam.
