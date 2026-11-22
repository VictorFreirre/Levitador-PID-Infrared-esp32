// Controle de altura de um disco suspenso em um tubo por fluxo de ar (ESP32-C3, Wokwi)
// A planta (disco, ar e blower) e o sensor VL53L0X sao simulados dentro do proprio programa.
//
// Comandos pela serial:
//   25         setpoint em cm (volta ao PID)
//   pwm 410    PWM manual (0-100 = %, acima de 100 = valor bruto 0-2047)
//   auto       volta ao controle PID
//   kp/ki/kd 0.1   ganhos do PID
//   cfd 1.2    forca real = 1,2 x a prevista pelo CFD (o controle nao sabe disso)
//   ruido 0/1  desliga/liga ruido do sensor e descentramento do disco

#define TESTE_DEGRAUS 0   // 1 = degraus automaticos (se 0, use o terminal serial)

#define PIN_PWM 4

// ===== PWM =====
const int PWM_FREQ = 20000;
const int PWM_BITS = 11;                // 2048 niveis
const int PWM_MAX  = (1 << PWM_BITS) - 1;

// ===== Tubo: 0 a 500 mm, sensor no topo =====
const float DIST_MIN = 30;    // mm (minimo confiavel do VL53L0X)
const float DIST_MAX = 500;   // mm (fundo do tubo)

// =====================================================================
//  DADOS DO CFD (planilha levitador_calculo.xlsx)
// =====================================================================
const float MASSA      = 0.02889f;    // kg (28,89 g)
const float G          = 9.81f;
const float CFD_A      = 1.41737f;    // N/(m/s)^n   (ajuste log-log dos Runs 4, 5 e 6)
const float CFD_N      = 1.86633f;
const float CFD_REF_MM = 250.0f;      // posicao (distancia do sensor) dos Runs 4-6
const float CFD_SLOPE  = 0.0011765f;  // variacao relativa da forca por mm de distancia (Run 7)
const float AREA_TUBO  = 1.9635e-3f;  // m2 (tubo diam. 50 mm)

// Erro do CFD: a planta REAL tem forca = cfdErro x CFD. O controle (feedforward) NAO sabe disso.
// A planilha assume 20-30% de incerteza: teste 0.75 e 1.25 (comando serial: cfd 1.25).
float cfdErro = 1.0f;

// Fator de altura: 1 em 250 mm; cai ao subir (perto do sensor)
float fatorAltura(float d) { return constrain(1.0f + CFD_SLOPE * (d - CFD_REF_MM), 0.2f, 2.0f); }

// Velocidade do ar (m/s) que equilibra o disco na distancia d (mm), modelo nominal
float vEquilibrio(float d) { return powf(MASSA * G / (CFD_A * fatorAltura(d)), 1.0f / CFD_N); }

// Forca sobre o disco (N). vrel = velocidade do ar relativa ao disco, fe = fator de excentricidade
float forcaCFD(float vrel, float d, float fe) {
  return cfdErro * CFD_A * powf(vrel, CFD_N) * fatorAltura(d) * fe;
}

// Perda de forca com o disco descentrado (Runs 6, 8, 9, 10, 11)
//   0 mm -> 1,000 | 0,15 mm -> 0,857 (media de +y e -y) | 0,30 mm -> 0,811 | acima disso: extrapolado
float fatorExcentr(float y_mm) {
  float a = fabsf(y_mm);
  float f;
  if (a <= 0.15f) f = 1.0f - 0.143f * (a / 0.15f);
  else            f = 0.857f - 0.046f * (a - 0.15f) / 0.15f;
  return max(f, 0.5f);
}

// =====================================================================
//  BLOWER Delta BFB1012EH-AF00 (curva P-Q do datasheet, a 12 V)
// =====================================================================
const int   FAN_N = 8;
const float FAN_Q[FAN_N] = {0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.302};   // m3/min
const float FAN_P[FAN_N] = {71.48, 68, 59, 50, 40, 27, 10, 0};         // mmH2O

const float R_MAX     = 1.05f;   // rotacao maxima relativa (12,6 V / 12 V)
const float TAU_SOBE  = 0.3f;    // s (ESTIMATIVA: medir na bancada com um degrau de PWM)
const float TAU_DESCE = 0.6f;    // s (ESTIMATIVA: o rotor demora mais para desacelerar)
const float TAU_AR    = 0.05f;   // s (inercia do ar no tubo)

float r_rot = 0;                 // rotacao relativa do blower (1 = 12 V)

// Pressao (Pa) do blower a vazao Q (m3/s) com rotacao relativa r (leis dos ventiladores: Q ~ N, P ~ N2)
float fanP(float Q, float r) {
  if (r <= 0.0f) return 0.0f;
  float q = max(Q * 60.0f / r, 0.0f);          // m3/min na curva de 12 V
  if (q >= FAN_Q[FAN_N - 1]) return 0.0f;
  int i = 0;
  while (q > FAN_Q[i + 1]) i++;
  float p = FAN_P[i] + (FAN_P[i + 1] - FAN_P[i]) * (q - FAN_Q[i]) / (FAN_Q[i + 1] - FAN_Q[i]);
  return p * 9.80665f * r * r;
}

// Velocidade do ar no tubo (m/s) = cruzamento da curva do blower com a queda de pressao no disco
float vOperacao(float r, float d, float fe) {
  if (r <= 0.0f) return 0.0f;
  float lo = 0.0f;
  float hi = min(r * FAN_Q[FAN_N - 1] / 60.0f / AREA_TUBO, 2.0f);
  for (int i = 0; i < 12; i++) {
    float v = 0.5f * (lo + hi);
    float pSis = forcaCFD(v, d, fe) / AREA_TUBO;
    if (fanP(v * AREA_TUBO, r) > pSis) lo = v; else hi = v;
  }
  return 0.5f * (lo + hi);
}

// Feedforward: PWM (%) que equilibra o disco em d, pelo modelo NOMINAL (cfdErro = 1, disco centrado)
float uFF(float d) {
  static float cacheD = -1, cacheU = 0;
  if (d == cacheD) return cacheU;
  float q   = vEquilibrio(d) * AREA_TUBO;
  float pEq = MASSA * G / AREA_TUBO;            // no equilibrio, queda de pressao = peso / area
  float lo = 0.01f, hi = R_MAX;
  for (int i = 0; i < 14; i++) {
    float r = 0.5f * (lo + hi);
    if (fanP(q, r) < pEq) lo = r; else hi = r;
  }
  cacheD = d;
  cacheU = 100.0f * 0.5f * (lo + hi);
  return cacheU;
}

// =====================================================================
//  SENSOR VL53L0X (modelo na simulacao)
// =====================================================================
const uint32_t SENSOR_PERIODO_MS = 33;     // timing budget padrao do VL53L0X (~33 ms)
const float SENSOR_SIGMA0   = 1.0f;        // mm (ESTIMATIVA: trocar pelo desvio medido na calibracao)
const float SENSOR_SIGMA_K  = 0.008f;      // mm de desvio por mm de distancia (disco impresso, pouco refletivo)
const float SENSOR_OFFSET   = 0.0f;        // mm (erro sistematico residual da calibracao)
const float SENSOR_P_FALHA  = 0.005f;      // 0,5% das leituras dao timeout (NAN)
const float SENSOR_P_SPIKE  = 0.003f;      // 0,3% das leituras saem com erro grande (20-120 mm)
bool ruidoLigado = true;                   // comando serial: ruido 0 / ruido 1

// =====================================================================
//  PID e controle manual
// =====================================================================
float Kp = 0.10, Ki = 0.03, Kd = 0.03;
float setpoint = 300;          // mm (distancia REAL sensor -> objeto)
float integral = 0, dist_ant = 0, dist_f = 0;
const float dt = 0.03;         // 30 ms
const float U_MIN = 0, U_MAX = 100;

bool modoManual = false;
float pwmManual = 0.0f;        // %

// =====================================================================
//  Planta simulada
// =====================================================================
float h = DIST_MAX;            // mm: o disco comeca parado no fundo do tubo
float vd = 0;                  // mm/s (+ = desce)
float v_ar = 0;                // m/s
float h_atras = DIST_MAX;      // posicao de 1 ciclo atras (atraso do sensor)
float y_exc = 0;               // mm: descentramento lateral do disco

const float TAU_Y    = 0.5f;   // s (escala de tempo do balanco lateral)
const float SIGMA_Y  = 0.12f;  // mm (ESTIMATIVA: desvio do descentramento)
const float FOLGA_MM = 0.75f;  // folga radial disco-tubo
const float REST_TETO = 0.3f;  // coeficiente de restituicao ao bater no topo

float randn() {                // ~N(0,1), soma de 12 uniformes
  float s = 0;
  for (int i = 0; i < 12; i++) s += random(0, 10000) / 10000.0f;
  return s - 6.0f;
}

// ===== Comandos pela serial =====
String entrada;

void processarComando(String cmd) {
  cmd.trim();
  cmd.toLowerCase();
  if (cmd.length() == 0) return;

  if (isDigit(cmd[0]) || cmd[0] == '.') {          // setpoint em cm
    float cm = constrain(cmd.toFloat(), 5.0f, 45.0f);
    setpoint = cm * 10.0f;
    modoManual = false;
    Serial.printf("# setpoint = %.1f cm (Modo PID Ativo)\n", cm);
    return;
  }

  int sp = cmd.indexOf(' ');
  if (sp > 0) {
    String nome = cmd.substring(0, sp);
    float val = cmd.substring(sp + 1).toFloat();
    if (nome == "kp") Kp = val;
    else if (nome == "ki") Ki = val;
    else if (nome == "kd") Kd = val;
    else if (nome == "cfd" && val > 0.2 && val < 3) {
      cfdErro = val;
      Serial.printf("# planta real = %.2f x CFD\n", cfdErro);
      return;
    }
    else if (nome == "ruido") {
      ruidoLigado = (val != 0);
      Serial.printf("# ruido do sensor e disturbios: %s\n", ruidoLigado ? "ligado" : "desligado");
      return;
    }
    else if (nome == "pwm" && val >= 0) {
      if (val > 100) {                              // valor bruto do registrador (0..2047)
        val = constrain(val, 0.0f, (float)PWM_MAX);
        pwmManual = (val / (float)PWM_MAX) * 100.0f;
      } else {
        pwmManual = constrain(val, 0.0f, 100.0f);
      }
      modoManual = true;
      Serial.printf("# MODO MANUAL -> PWM Bruto: %.0f (%.1f%%)\n", (pwmManual / 100.0f) * PWM_MAX, pwmManual);
      return;
    }
    else { Serial.println("# comando invalido"); return; }
    integral = 0;
    Serial.printf("# Kp=%.3f Ki=%.3f Kd=%.3f\n", Kp, Ki, Kd);
    return;
  }

  if (cmd == "pid" || cmd == "auto") {
    modoManual = false;
    Serial.println("# Retornado ao controle PID automatico");
    return;
  }

  Serial.println("# use: 25 (setpoint cm) | pwm 410 (manual) | auto | kp 0.1 | cfd 1.2 | ruido 0/1");
}

void lerSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') { processarComando(entrada); entrada = ""; }
    else entrada += c;
  }
}

// ===== Leitura simulada do sensor (distancia em mm, NAN se falhar) =====
float lerDistancia() {
  // O VL53L0X so entrega uma medida nova a cada ~33 ms (o laco roda a cada 30 ms): as vezes repete a anterior.
  static uint32_t tAmostra = 0;
  static float bruto = h_atras;
  static bool falha = false;
  if (millis() - tAmostra >= SENSOR_PERIODO_MS) {
    tAmostra = millis();
    falha = false;
    float x = h_atras + SENSOR_OFFSET;              // medida atrasada (tempo de integracao do sensor)
    if (ruidoLigado) {
      float sigma = SENSOR_SIGMA0 + SENSOR_SIGMA_K * x;
      x += sigma * randn();
      float sorteio = random(0, 100000) / 100000.0f;
      if (sorteio < SENSOR_P_FALHA) falha = true;
      else if (sorteio < SENSOR_P_FALHA + SENSOR_P_SPIKE)
        x += (random(0, 2) ? 1 : -1) * (20.0f + random(0, 100));
    }
    bruto = roundf(x);                              // o sensor devolve mm inteiros
  }
  if (falha) return NAN;
  return constrain(bruto, DIST_MIN, DIST_MAX);
}

void setup() {
  Serial.begin(115200);
  ledcAttach(PIN_PWM, PWM_FREQ, PWM_BITS);       // Arduino-ESP32 3.x

  float d = lerDistancia();
  dist_f = isnan(d) ? setpoint : d;
  dist_ant = dist_f;
  Serial.println("# Comandos: [cm] setpoint | pwm [0-2047] manual | auto | kp/ki/kd | cfd | ruido");
  Serial.printf("# modelo: equilibrio a 250 mm = PWM %.1f%% | a 300 mm = %.1f%% | a 100 mm = %.1f%%\n",
                uFF(250), uFF(300), uFF(100));
  Serial.printf("# modelo: a 100%% o ar sobe a %.2f m/s no tubo\n", vOperacao(R_MAX, 250, 1.0f));
}

void loop() {
  lerSerial();

  static uint32_t t0 = millis();
  if (millis() - t0 < dt * 1000) return;
  t0 = millis();

#if TESTE_DEGRAUS
  float t = millis() / 1000.0f;
  if (!modoManual) {
    if (t > 40)      setpoint = 400;
    else if (t > 20) setpoint = 200;
  }
#endif

  // ---------- Controle ----------
  static float u = 0;                            // mantem o ultimo PWM se a leitura falhar
  float dist = lerDistancia();

  if (!isnan(dist)) {
    dist_f = 0.7 * dist_f + 0.3 * dist;          // filtro passa-baixa

    if (modoManual) {
      u = pwmManual;
    } else {
      // Sensor no topo: distancia maior = objeto mais baixo = mais PWM
      float erro  = dist_f - setpoint;
      float deriv = (dist_f - dist_ant) / dt;    // derivada na medicao
      dist_ant = dist_f;

      float u_ff = uFF(setpoint);                // feedforward pela curva do blower + CFD nominal

      float u_bruto = u_ff + Kp * erro + Ki * integral + Kd * deriv;
      u = constrain(u_bruto, U_MIN, U_MAX);
      if (u == u_bruto) integral += erro * dt;   // anti-windup
    }
  }

  int duty = (int)roundf(u / 100.0f * PWM_MAX);
  ledcWrite(PIN_PWM, duty);
  float u_real = duty * 100.0f / PWM_MAX;        // com a quantizacao do PWM

  // ---------- Planta simulada ----------
  h_atras = h;                                   // o sensor enxerga a posicao de 1 ciclo atras

  // Blower: a rotacao segue a tensao media com atraso (sobe mais rapido do que desce)
  float r_cmd = constrain(u_real / 100.0f, 0.0f, R_MAX);
  r_rot += (r_cmd - r_rot) * dt / (r_cmd > r_rot ? TAU_SOBE : TAU_DESCE);

  // Descentramento lateral do disco (processo de Ornstein-Uhlenbeck limitado pela folga)
  if (ruidoLigado) {
    y_exc += -y_exc / TAU_Y * dt + SIGMA_Y * sqrtf(2.0f * dt / TAU_Y) * randn();
    y_exc = constrain(y_exc, -FOLGA_MM, FOLGA_MM);
  } else y_exc = 0;
  float fe = fatorExcentr(y_exc);

  // Vazao: cruzamento da curva P-Q do blower com a perda de pressao no disco
  float v_alvo = vOperacao(r_rot, h, fe);

  // Dinamica do disco
  for (int i = 0; i < 10; i++) {                 // 10 subpassos
    float hs = dt / 10.0f;
    v_ar += (v_alvo - v_ar) * hs / TAU_AR;
    float vrel = max(v_ar + vd / 1000.0f, 0.0f); // ar relativo ao disco (vd + = desce)
    float F = forcaCFD(vrel, h, fe);
    float a = (G - F / MASSA) * 1000.0f;         // mm/s2, + = desce
    vd += a * hs;
    h  += vd * hs;
    if (h >= DIST_MAX) { h = DIST_MAX; if (vd > 0) vd = 0; }                        // repousa no fundo
    else if (h <= DIST_MIN) { h = DIST_MIN; if (vd < 0) vd = -vd * REST_TETO; }     // bate no topo
  }

  // Saida para o grafico serial
  Serial.printf("setpoint_cm:%.1f,medida_cm:%.1f,real_cm:%.1f,pwm_pct:%.1f,min:0,max:50\n",
                setpoint / 10.0f, dist_f / 10.0f, h / 10.0f, u_real);
}
