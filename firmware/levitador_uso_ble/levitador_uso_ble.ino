// =====================================================================================================================
//  LEVITADOR PNEUMATICO - versao de uso (ESP32-C3) - limpa em 16/11/2026
//  Carretel v1 (10,14 g) num tubo, blower Delta 4 fios (PWM), sensor VL53L0X no topo, papel furado embaixo do retificador.
//  Versao anterior completa (ping-pong, PLA, carretel v2, sem papel, tacometro, cascata, observador):
//    versoes/levitador_uso_ble_modos_2026-11-16/
//
//  Placa: ESP32C3 Dev Module, USB CDC On Boot. Bibliotecas: VL53L0X (Pololu), NimBLE-Arduino 2.x. Core ESP32 3.x.
//
//  COMANDOS (serial 115200, Enter no fim). Liga DESLIGADO (PWM 0).
//    25            setpoint: posicao do centro do carretel em cm acima do repouso (2 a 46). "sp 25" tambem vale
//    0             desliga o blower                    | pwm 30   PWM manual (%)        | auto   volta ao controle
//    modo 1..7     1 P | 2 PI | 3 PID | 4 +Smith | 5 +Overdrive | 6 +Trajetoria | 7 completo (padrao). "modo" mostra
//    kp ki kd      ganhos | banda imax ulim rampa reset                       (PID)
//    traj tacel ffk fftau                                                      (trajetoria)
//    smith smk smtau smth | avanco avalfa                                      (Smith e overdrive)
//    ueq ueqauto ueqtau ueqi ffm                                               (feedforward de equilibrio)
//    udec decr decf toque decpd decalt                                         (decolagem)
//    alfa tb medir                                                             (sensor)
//    csv 1/0 | degrau A B ta tb | onda A B t                                   (ensaios)
//  Celular (BLE "Levitador", app Serial Bluetooth Terminal): so numero, 0, sp X, auto e modo.
// =====================================================================================================================

#include <Wire.h>
#include <VL53L0X.h>
#include <Preferences.h>

#define USAR_BLE 1
#define PWM_INVERTIDO 0   // 1 se o PWM do blower passar por um transistor que inverte

// ---------------------------------------------------------------------------------------------------------------------
//  HARDWARE
// ---------------------------------------------------------------------------------------------------------------------
#define PIN_PWM 10
#define PIN_SDA 8
#define PIN_SCL 9
const int PWM_FREQ = 25000;                 // padrao de ventoinha 4 fios
const int PWM_BITS = 10;
const int PWM_MAX  = (1 << PWM_BITS) - 1;

// ---------------------------------------------------------------------------------------------------------------------
//  GEOMETRIA E LIMITES
//  Internamente tudo e DISTANCIA do sensor ao topo do carretel (mm). Para o usuario: POSICAO do centro (cm, repouso = 0).
// ---------------------------------------------------------------------------------------------------------------------
const float DIST_MIN = 30, DIST_MAX = 600;  // mm, faixa aceita da leitura
const float TUBO_CM  = 50.0f;               // escala interna de altura: altura = 50 - distancia
const float DIST_FUNDO_CM = 57.8f;          // sensor -> retificador
const float H_OBJ_CM = 3.4f;                // altura do carretel
const float POS_ZERO_CM = DIST_FUNDO_CM - H_OBJ_CM;
const float POS_MIN = 2.0f, POS_MAX = 46.0f;   // setpoint aceito em voo (cm)

const float DIST_TOPO    = 50.0f;           // mm: mais perto do sensor que isso -> corta o blower
const float DIST_RELIGA  = 200.0f;          // mm: depois do corte, volta a controlar abaixo disso
const uint32_t WATCHDOG_MS = 300;           // sem resposta do sensor -> PWM de seguranca
const float FATOR_SEGURO = 0.9f;            // PWM de seguranca = 90% do equilibrio (desce devagar)
const int   FALHAS_MAX   = 15;              // leituras invalidas seguidas antes do PWM de seguranca

float altura_cm(float dist_mm) { return TUBO_CM - dist_mm / 10.0f; }
float posCentro(float dist_mm) { return max(0.0f, POS_ZERO_CM - dist_mm / 10.0f); }
float distDaPos(float pos)     { return (POS_ZERO_CM - pos) * 10.0f; }

// ---------------------------------------------------------------------------------------------------------------------
//  PARAMETROS DO CONTROLE (padroes medidos na bancada com o papel; todos ajustaveis pela serial)
// ---------------------------------------------------------------------------------------------------------------------
// PID  (unidades: %PWM/mm, %PWM/(mm.s), %PWM/(mm/s))
float Kp = 0.09f, Ki = 0.006f, Kd = 0.09f;
float BANDA_INT = 100.0f;                   // mm: integral so age com |erro| menor que isso
float I_MAX     = 15.0f;                    // %: limite do integral
float U_LIM     = 9.0f;                     // %: PWM limitado a feedforward +- U_LIM
float VEL_SP    = 20.0f;                    // mm/s: velocidade maxima do setpoint
const float BETA = 0.5f;                    // filtro da derivada
const float U_PISO = 0.0f, U_MAX = 100.0f;

// Reset do integral (PI-CI): ao cruzar o novo setpoint, descarta o que o integral acumulou no transitorio
float resetPr = 1.0f;                       // fracao descartada (0 = desligado)

// Trajetoria: setpoint com aceleracao limitada + PWM previsto pelo modelo (v + tau*a)/K
float trajAcel = 10.0f;                     // mm/s2
float ffK = 3.0f, ffTau = 0.45f;            // modelo do feedforward (cm/s/%, s)

// Preditor de Smith: compensa o atraso do blower (modelo K/(s(tau s+1)) com atraso theta)
float smK = 2.2f, smTau = 0.43f, smTheta = 0.60f;   // cm/s/%, s, s

// Overdrive: avanco de fase no PWM para o rotor do blower acelerar mais rapido
float avancoTf = 0.6f, avancoA = 0.4f;

// Feedforward de equilibrio: PWM que segura o carretel parado, por altura (escala interna, cm)
// Medido em 12/11 (uso15_equilibrio_ambiente_novo). So a FORMA importa: o nivel vem do ueq (valor a 25 cm).
const int   FF_N = 12;
const float FF_H[FF_N] = {-4.4f, -0.4f, 5.6f, 11.6f, 17.6f, 23.6f, 27.6f, 31.6f, 35.6f, 39.6f, 41.6f, 43.6f};
const float FF_U[FF_N] = {41.6f, 41.64f, 41.59f, 42.01f, 42.11f, 41.84f, 41.39f, 41.02f, 41.12f, 42.00f, 42.69f, 42.9f};
float ueq     = 48.1f;                      // % a 25 cm (substituido pelo valor salvo na flash)
float ueqIncl = 0.0f;                       // %/cm extra (normalmente 0)
float ueqTau  = 30.0f;                      // s: constante do auto-ajuste do ueq
bool  ffMedida = true;                      // feedforward na altura medida (true) ou no setpoint
const float UEQ_MIN = 30.0f, UEQ_MAX = 70.0f;
#define CHAVE_UEQ "ueqR"                    // chave da flash (perfil com papel)

// Decolagem: no fundo o carretel gruda no retificador; o PWM sobe em rampa ate ele soltar
float uDecola    = 48.5f;                   // %: referencia do teto da rampa
float decRampa   = 0.3f;                    // %/s
float decFreio   = 0.5f;                    // %: o PID parte este tanto abaixo do PWM de soltura
float decAltFrac = 0.0f;                    // PID assume a esta fracao da altura do setpoint (0 = sempre 6 cm)
bool  decSemPD   = true;                    // na soltura o integral nao absorve P e D (o D freia a subida)
uint32_t toqueMs = 800;                     // ms: toque em voo mais curto que isso nao chama o retoque
const float ALT_DECOLA = 6.0f;              // cm acima do repouso: abaixo disso = "no fundo" (antes de decolar)
const float ALT_TOQUE  = 1.5f;              // cm acima do repouso: depois de decolar, so e fundo se encostar

// Sensor
float ALFA = 0.5f;                          // filtro da medida (1 = sem filtro)
uint32_t TB_US = 33000;                     // timing budget do VL53L0X (us)
const float CAL_C0 = -18.386522f, CAL_C1 = 1.003466f, CAL_C2 = -0.00037f, CAL_C3 = 0.0000007867f;   // calibracao (grau 3)

// ---------------------------------------------------------------------------------------------------------------------
//  CAMADAS LIGADAS (comando "modo")
// ---------------------------------------------------------------------------------------------------------------------
bool usaI = true, usaD = true;
bool smithOn  = true;
bool avancoOn = true;
bool trajOn   = true;
bool resetOn  = true;
bool ueqAuto  = true;

// ---------------------------------------------------------------------------------------------------------------------
//  ESTADO (variaveis internas)
// ---------------------------------------------------------------------------------------------------------------------
VL53L0X sensor;
Preferences prefs;

// controle
bool  modoManual = true;                    // liga em manual com PWM 0
float pwmManual = 0, u = 0, u_real = 0;     // %
float setpoint = 300, sp_ref = 300;         // mm (pedido e com rampa/trajetoria)
float integral = 0;                         // % de PWM
float dist_f = 0, dist_ant = 0, deriv_f = 0;
float m1 = 0, m2 = 0, m3 = 0;
bool  iniciado = false, transicao = false, transicaoDecola = false;
bool  emCorte = false, semSensor = false;
int   falhasSeguidas = 0;
uint32_t tUltimaResposta = 0;
float tsMedio = 0.0308f;                    // periodo medio entre medidas (s)

// reset do integral
float iAntesTroca = 0;
bool  aguardaCruzar = false;
int   sinalErroTroca = 0;

// trajetoria (historico da referencia para o integral comparar com a referencia atrasada de theta)
float vTraj = 0, aTraj = 0;
const int SPB_N = 64;
float spBuf[SPB_N];
int   spIdx = 0;

// Smith
const int SM_MAX = 64;
float smBufY[SM_MAX], smBufV[SM_MAX];
int   smIdx = 0;
float smY = 0, smV = 0, smUpd = 0;
uint32_t smUltimo = 0;

// overdrive
float avX = 0;
uint32_t avUltimo = 0;

// ueq automatico
float tNoAr = 0, ueqSalvo = -1, ueqMsg = -1;
uint32_t tUeqMsg = 0;

// decolagem
bool  decolou = false, noFundo = false;
float altRepouso = -4.4f;                   // cm (escala interna), aprendido com o blower desligado
float uDecAtual = 0;
uint32_t toqueT0 = 0, tPwmZero = 0, decT0 = 0, decUltimoPID = 0;

// ensaios
bool  saidaCSV = false;
bool  ondaAtiva = false;
float ondaA = 0, ondaB = 0;
uint32_t ondaMeioMs = 0, testeInicio = 0;
bool  degrauAtivo = false, degrauAplicado = false;
float degrauA = 0, degrauB = 0;
uint32_t degrauT0 = 0, degrauEsperaMs = 4000, degrauDuracaoMs = 4000;

// ---------------------------------------------------------------------------------------------------------------------
//  FUNCOES AUXILIARES
// ---------------------------------------------------------------------------------------------------------------------
float tabelaEq(float h) {
  if (h <= FF_H[0]) return FF_U[0];
  for (int i = 1; i < FF_N; i++)
    if (h <= FF_H[i]) return FF_U[i - 1] + (FF_U[i] - FF_U[i - 1]) * (h - FF_H[i - 1]) / (FF_H[i] - FF_H[i - 1]);
  return FF_U[FF_N - 1];
}

// PWM de equilibrio na distancia d (mm)
float feedforward(float d) {
  float h = altura_cm(d);
  return tabelaEq(h) + (ueq - tabelaEq(25.0f)) + ueqIncl * (h - 25.0f);
}

void salvarUeq() {                          // so com o blower desligado (gravar em voo ja travou a placa)
  if (fabsf(ueq - ueqSalvo) < 0.05f) return;
  prefs.putFloat(CHAVE_UEQ, ueq);
  ueqSalvo = ueq;
}

void smithReset() {
  smY = smV = smUpd = 0;
  for (int i = 0; i < SM_MAX; i++) { smBufY[i] = 0; smBufV[i] = 0; }
  smIdx = 0;
}

void marcarTrocaSetpoint() {
  iAntesTroca = integral;
  aguardaCruzar = (resetOn && usaI && resetPr > 0.001f);
  sinalErroTroca = 0;
}

void aplicarPWM() {
  int duty = (int)roundf(constrain(u, 0.0f, 100.0f) / 100.0f * PWM_MAX);
  u_real = duty * 100.0f / PWM_MAX;
#if PWM_INVERTIDO
  duty = PWM_MAX - duty;
#endif
  ledcWrite(PIN_PWM, duty);
}

const char* motivoReset() {
  switch (esp_reset_reason()) {
    case ESP_RST_POWERON:  return "energia ligada";
    case ESP_RST_SW:       return "reset por software";
    case ESP_RST_PANIC:    return "PANIC (erro/excecao)";
    case ESP_RST_INT_WDT:  return "watchdog de interrupcao";
    case ESP_RST_TASK_WDT: return "watchdog do loop (travou)";
    case ESP_RST_WDT:      return "outro watchdog";
    case ESP_RST_BROWNOUT: return "BROWNOUT (queda de tensao)";
    case ESP_RST_USB:      return "USB (porta reaberta/RTS)";
    default:               return "outro";
  }
}

// ---------------------------------------------------------------------------------------------------------------------
//  MODOS DE CONTROLE: cada modo liga uma camada a mais (ganhos iguais em todos)
//  Sempre ligados: feedforward de equilibrio, decolagem e protecoes.
// ---------------------------------------------------------------------------------------------------------------------
const int MODO_N = 7;
const char* MODO_NOME[MODO_N + 1] = { "personalizado", "P", "PI", "PID", "PID + Smith", "PID + Smith + Overdrive",
                                      "PID + Smith + Overdrive + Trajetoria",
                                      "COMPLETO (PID + Smith + Overdrive + Trajetoria + Reset do I + ueq auto)" };
// nome curto SEM espacos (vai na linha da serial e no celular)
const char* MODO_CURTO[MODO_N + 1] = { "Personalizado", "P", "PI", "PID", "PID+Smith", "PID+Smith+Overdrive",
                                       "PID+Smith+OD+Trajetoria", "Completo" };

bool temAv()    { return avancoOn && avancoTf > 0.01f; }
bool temReset() { return resetOn && resetPr > 0.001f && usaI; }

int modoAtual() {                           // 0 = combinacao avulsa
  bool sm = smithOn, av = temAv(), tr = trajOn, rs = temReset(), ua = ueqAuto, i = usaI, d = usaD;
  if (sm && av && tr && rs && ua && i && d)    return 7;
  if (sm && av && tr && !rs && !ua && i && d)  return 6;
  if (tr || rs || ua)                          return 0;
  if (!i && !d && !sm && !av)                  return 1;
  if (i && !d && !sm && !av)                   return 2;
  if (i && d && !sm && !av)                    return 3;
  if (i && d && sm && !av)                     return 4;
  if (i && d && sm && av)                      return 5;
  return 0;
}

String nomeControle() {                     // nome montado das chaves reais
  String s = "P";
  if (usaI) s += "I";
  if (usaD) s += "D";
  if (smithOn) s += " + Smith";
  if (temAv()) s += " + Overdrive";
  if (trajOn) s += " + Trajetoria";
  if (temReset()) s += " + Reset do I";
  if (ueqAuto) s += " + ueq auto";
  return s;
}

void mostrarModo() {
  int m = modoAtual();
  if (m > 0) Serial.printf("# CONTROLE = modo %d - %s\n", m, MODO_NOME[m]);
  else       Serial.printf("# CONTROLE = personalizado - %s\n", nomeControle().c_str());
}

void aplicarModo(int m) {
  bool tinhaSmith = smithOn;
  usaI     = (m >= 2);
  usaD     = (m >= 3);
  smithOn  = (m >= 4);
  avancoOn = (m >= 5);
  trajOn   = (m >= 6);
  resetOn  = (m >= 7);
  ueqAuto  = (m >= 7);
  if (!usaI) integral = 0;
  if (!trajOn) { vTraj = 0; aTraj = 0; }
  if (!resetOn) aguardaCruzar = false;
  if (smithOn && !tinhaSmith) smithReset();
}

// ---------------------------------------------------------------------------------------------------------------------
//  BLUETOOTH LE (Nordic UART): o celular manda setpoint/modo e recebe SP | Pos | PWM | modo 2x por segundo
// ---------------------------------------------------------------------------------------------------------------------
#if USAR_BLE
#include <NimBLEDevice.h>
#define NUS_SERVICE "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define NUS_RX      "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
#define NUS_TX      "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
NimBLECharacteristic* bleTx = nullptr;
char bleBuf[48];
volatile bool bleTemCmd = false, bleConectado = false;
uint32_t bleCmds = 0, bleRecusados = 0;

// o callback roda na task do Bluetooth: so copia o texto; quem executa e o loop()
class BleRxCallback : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* c, NimBLEConnInfo& info) override {
    if (bleTemCmd) return;
    NimBLEAttValue v = c->getValue();
    size_t n = v.length();
    if (n > sizeof(bleBuf) - 1) n = sizeof(bleBuf) - 1;
    memcpy(bleBuf, v.data(), n);
    bleBuf[n] = 0;
    bleTemCmd = true;
  }
};
class BleServerCallback : public NimBLEServerCallbacks {
  void onConnect(NimBLEServer* s, NimBLEConnInfo& info) override { bleConectado = true; }
  void onDisconnect(NimBLEServer* s, NimBLEConnInfo& info, int reason) override { bleConectado = false; }
};

void bleEnviar(const char* txt) {
  if (!bleConectado || !bleTx) return;
  bleTx->setValue((const uint8_t*)txt, strlen(txt));
  bleTx->notify();
}

void iniciarBLE() {
  NimBLEDevice::init("Levitador");
  NimBLEServer* srv = NimBLEDevice::createServer();
  srv->setCallbacks(new BleServerCallback());
  srv->advertiseOnDisconnect(true);
  NimBLEService* svc = srv->createService(NUS_SERVICE);
  NimBLECharacteristic* rx = svc->createCharacteristic(NUS_RX, NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::WRITE_NR);
  rx->setCallbacks(new BleRxCallback());
  bleTx = svc->createCharacteristic(NUS_TX, NIMBLE_PROPERTY::NOTIFY);
  svc->start();
  NimBLEAdvertising* adv = NimBLEDevice::getAdvertising();
  NimBLEAdvertisementData advData, scanData;
  advData.setFlags(BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP);
  advData.addServiceUUID(NimBLEUUID(NUS_SERVICE));
  scanData.setName("Levitador");            // nome na resposta ao scan (nao cabe junto com o UUID)
  adv->setAdvertisementData(advData);
  adv->setScanResponseData(scanData);
  adv->start();
}

bool permitidoBLE(const String& c) {        // pelo celular so comandos seguros
  if (c.length() == 0) return false;
  return isDigit(c[0]) || c[0] == '.' || c.startsWith("sp ") || c == "auto" || c == "modo" || c.startsWith("modo ");
}
#endif

// ---------------------------------------------------------------------------------------------------------------------
//  SENSOR VL53L0X
// ---------------------------------------------------------------------------------------------------------------------
float calibrar(float m) { return CAL_C0 + m * (CAL_C1 + m * (CAL_C2 + m * CAL_C3)); }

// Destrava o I2C (ate 9 clocks com SDA preso + STOP) e deixa o Wire a 100 kHz
void destravarI2C() {
  Wire.end();
  pinMode(PIN_SDA, INPUT_PULLUP);
  pinMode(PIN_SCL, OUTPUT_OPEN_DRAIN);
  digitalWrite(PIN_SCL, HIGH); delayMicroseconds(10);
  for (int i = 0; i < 9 && digitalRead(PIN_SDA) == LOW; i++) {
    digitalWrite(PIN_SCL, LOW);  delayMicroseconds(10);
    digitalWrite(PIN_SCL, HIGH); delayMicroseconds(10);
  }
  pinMode(PIN_SDA, OUTPUT_OPEN_DRAIN);
  digitalWrite(PIN_SDA, LOW);  delayMicroseconds(10);
  digitalWrite(PIN_SCL, HIGH); delayMicroseconds(10);
  digitalWrite(PIN_SDA, HIGH); delayMicroseconds(10);
  pinMode(PIN_SDA, INPUT_PULLUP);
  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClock(100000);
}

void softResetSensor() {
  sensor.setTimeout(50);
  sensor.writeReg(0xBF, 0x00); delay(2);
  sensor.writeReg(0xBF, 0x01); delay(5);
}

bool reiniciarSensor() {
  destravarI2C();
  sensor.setTimeout(100);
  if (!sensor.init()) return false;
  sensor.setMeasurementTimingBudget(TB_US);
  sensor.startContinuous();
  Wire.setClock(400000);
  return true;
}

// true quando ha medida NOVA (mm, ou NAN se invalida)
bool novaMedida(float &mm) {
  if ((sensor.readReg(VL53L0X::RESULT_INTERRUPT_STATUS) & 0x07) == 0) return false;
  uint16_t r = sensor.readRangeContinuousMillimeters();
  if (sensor.timeoutOccurred() || r >= 2000) mm = NAN;
  else mm = constrain(calibrar((float)r), DIST_MIN, DIST_MAX);
  return true;
}

// ---------------------------------------------------------------------------------------------------------------------
//  COMANDOS
// ---------------------------------------------------------------------------------------------------------------------
void desligar() {
  modoManual = true; degrauAtivo = false; ondaAtiva = false;
  pwmManual = 0; u = 0;
  aplicarPWM();
  salvarUeq();
}

void ligarControle() {                      // manual -> controle: a referencia parte de onde o carretel esta
  if (modoManual) { transicao = true; sp_ref = dist_f; aguardaCruzar = false; }
  modoManual = false;
}

void cmdSetpoint(float pedido) {
  ondaAtiva = false;
  if (pedido <= 0.0f) {
    desligar();
    Serial.printf("# setpoint 0: blower DESLIGADO | ueq %.2f%%\n", ueq);
    return;
  }
  float pos = constrain(pedido, POS_MIN, POS_MAX);
  setpoint = distDaPos(pos);
  if (modoManual) ligarControle();
  else marcarTrocaSetpoint();
  if (pos != pedido) Serial.printf("# fora do limite: use 0 (desliga) ou %.0f a %.0f\n", POS_MIN, POS_MAX);
  Serial.printf("# setpoint = %.1f cm | ueq %.2f%%%s\n", pos, ueq, ueqAuto ? " (auto)" : "");
  mostrarModo();
}

void cmdModo(String a) {
  a.trim();
  int m = -1;
  if (a.length() && isDigit(a[0])) m = a.toInt();
  else if (a == "p") m = 1;
  else if (a == "pi") m = 2;
  else if (a == "pid") m = 3;
  else if (a == "smith") m = 4;
  else if (a == "od" || a == "overdrive") m = 5;
  else if (a == "traj" || a == "trajetoria") m = 6;
  else if (a == "completo") m = 7;
  if (m >= 1 && m <= MODO_N) aplicarModo(m);
  else {
    if (a.length()) Serial.println("# modo invalido");
    for (int i = 1; i <= MODO_N; i++) Serial.printf("#   modo %d = %s\n", i, MODO_NOME[i]);
    Serial.println("#   (todos com feedforward de equilibrio, decolagem e protecoes; ganhos iguais)");
  }
  mostrarModo();
}

void cmdMedir(int n) {                      // diagnostico: n leituras brutas do sensor
  int ok = 0; float s = 0, mn = 1e9, mx = -1e9;
  for (int i = 0; i < n; i++) {
    uint16_t r = sensor.readRangeContinuousMillimeters();
    if (sensor.timeoutOccurred() || r >= 2000) continue;
    ok++; s += r; mn = min(mn, (float)r); mx = max(mx, (float)r);
  }
  tUltimaResposta = millis();               // a leitura bloqueia o loop: nao e falha do sensor
  if (ok) Serial.printf("# medir: %d leituras | bruto %.1f mm (%.0f a %.0f) | calibrado %.1f mm | posicao %.2f cm\n",
                        ok, s / ok, mn, mx, calibrar(s / ok), posCentro(calibrar(s / ok)));
  else Serial.println("# medir: sem leituras validas");
}

void cmdDegrau(const char* args) {          // degrau A B [espera_s] [duracao_s], em malha aberta
  float a1 = 0, a2 = 0, a3 = 0, a4 = 0;
  int n = sscanf(args, "%f %f %f %f", &a1, &a2, &a3, &a4);
  if (n < 2) { degrauAtivo = false; Serial.println("# uso: degrau 30 36 4 4"); return; }
  degrauA = constrain(a1, 0.0f, 100.0f);
  degrauB = constrain(a2, 0.0f, 100.0f);
  degrauEsperaMs  = (uint32_t)((n >= 3 && a3 > 0) ? a3 * 1000 : 4000);
  degrauDuracaoMs = (uint32_t)((n >= 4 && a4 > 0) ? a4 * 1000 : 4000);
  ondaAtiva = false; modoManual = true;
  pwmManual = u = degrauA;
  degrauT0 = millis(); degrauAplicado = false; degrauAtivo = true;
  Serial.printf("# DEGRAU: %.1f%% por %.1f s, %.1f%% por %.1f s, volta a %.1f%%\n",
                degrauA, degrauEsperaMs / 1000.0f, degrauB, degrauDuracaoMs / 1000.0f, degrauA);
}

void cmdOnda(const char* args) {            // onda A B t: setpoint alterna entre A e B a cada t s (sem rampa)
  float a1 = 0, a2 = 0, a3 = 0;
  if (sscanf(args, "%f %f %f", &a1, &a2, &a3) == 3 && a3 >= 1) {
    a1 = constrain(a1, POS_MIN, POS_MAX);
    a2 = constrain(a2, POS_MIN, POS_MAX);
    ondaA = distDaPos(a1); ondaB = distDaPos(a2);
    ondaMeioMs = (uint32_t)(a3 * 1000);
    testeInicio = millis();
    ligarControle();
    ondaAtiva = true;
    Serial.printf("# ONDA: %.0f <-> %.0f a cada %.1f s\n", a1, a2, a3);
  } else { ondaAtiva = false; Serial.println("# onda desligada (uso: onda 20 30 6)"); }
}

void cmdPwm(float val) {
  pwmManual = (val > 100) ? constrain(val, 0.0f, (float)PWM_MAX) / PWM_MAX * 100.0f   // >100 = valor bruto 0..1023
                          : constrain(val, 0.0f, 100.0f);
  modoManual = true; ondaAtiva = false; degrauAtivo = false;
  u = pwmManual;
  if (pwmManual <= 0) { aplicarPWM(); salvarUeq(); }
  Serial.printf("# MANUAL: PWM %.1f%%\n", pwmManual);
}

// Parametros "nome valor". Devolve false se o nome nao existir ou o valor estiver fora da faixa.
bool cmdParametro(const String& nome, float v) {
  bool on = (v != 0);
  // --- PID ---
  if      (nome == "kp") Kp = v;
  else if (nome == "ki") Ki = v;
  else if (nome == "kd") Kd = v;
  else if (nome == "banda"  && v >= 5 && v <= 400)   BANDA_INT = v;
  else if (nome == "imax"   && v >= 0.5 && v <= 30)  I_MAX = v;
  else if (nome == "ulim"   && v >= 0 && v <= 50)    U_LIM = v;
  else if (nome == "rampa"  && v >= 5 && v <= 2000)  VEL_SP = v;
  else if (nome == "reset"  && v >= 0 && v <= 1)   { resetPr = v; resetOn = (v > 0.001f); }
  // --- trajetoria ---
  else if (nome == "traj")                         { trajOn = on; vTraj = 0; aTraj = 0; }
  else if (nome == "tacel"  && v >= 2 && v <= 2000)  trajAcel = v;
  else if (nome == "ffk"    && v >= 0 && v < 50)     ffK = v;
  else if (nome == "fftau"  && v >= 0 && v < 5)      ffTau = v;
  // --- Smith e overdrive ---
  else if (nome == "smith")                        { smithOn = on; smithReset(); }
  else if (nome == "smk"    && v > 0.1 && v < 50)    smK = v;
  else if (nome == "smtau"  && v > 0.01 && v < 5)    smTau = v;
  else if (nome == "smth"   && v > 0.02 && v < 1.9){ smTheta = v; smithReset(); }
  else if (nome == "avanco" && v >= 0 && v < 3)    { avancoTf = v; avancoOn = (v > 0.01f); }
  else if (nome == "avalfa" && v >= 0.1 && v <= 0.9) avancoA = v;
  // --- feedforward de equilibrio ---
  else if (nome == "ueq"    && v >= UEQ_MIN && v <= UEQ_MAX) { ueq = v; salvarUeq(); }
  else if (nome == "ueqauto")                        ueqAuto = on;
  else if (nome == "ueqtau" && v >= 3 && v <= 600)   ueqTau = v;
  else if (nome == "ueqi"   && v > -1 && v < 1)      ueqIncl = v;
  else if (nome == "ffm")                            ffMedida = on;
  // --- decolagem ---
  else if (nome == "udec"   && v >= 0 && v <= 100)   uDecola = v;
  else if (nome == "decr"   && v >= 0 && v <= 20)    decRampa = v;
  else if (nome == "decf"   && v >= 0 && v <= 10)    decFreio = v;
  else if (nome == "toque"  && v >= 0 && v <= 5000){ toqueMs = (uint32_t)v; toqueT0 = 0; }
  else if (nome == "decpd")                          decSemPD = on;
  else if (nome == "decalt" && v >= 0 && v <= 1)     decAltFrac = v;
  // --- sensor ---
  else if (nome == "alfa"   && v >= 0.1 && v <= 1.0) ALFA = v;
  else if (nome == "tb"     && v >= 20 && v <= 200) {
    TB_US = (uint32_t)(v * 1000);
    sensor.stopContinuous(); sensor.setMeasurementTimingBudget(TB_US); sensor.startContinuous();
  }
  else return false;
  return true;
}

void processarComando(String cmd) {
  cmd.trim();
  cmd.toLowerCase();
  if (cmd.length() == 0) return;

  if (isDigit(cmd[0]) || cmd[0] == '.') { cmdSetpoint(cmd.toFloat()); return; }
  if (cmd.startsWith("sp "))            { cmdSetpoint(cmd.substring(3).toFloat()); return; }
  if (cmd == "modo" || cmd.startsWith("modo ")) { cmdModo(cmd.length() > 5 ? cmd.substring(5) : String("")); return; }
  if (cmd == "auto" || cmd == "pid")    { ligarControle(); Serial.println("# controle automatico"); mostrarModo(); return; }
  if (cmd.startsWith("degrau"))         { cmdDegrau(cmd.c_str() + 6); return; }
  if (cmd.startsWith("onda"))           { cmdOnda(cmd.c_str() + 4); return; }
  if (cmd.startsWith("csv ")) {
    saidaCSV = cmd.substring(4).toInt() != 0;
    if (saidaCSV) {
      Serial.printf("# boot ha %lu s | ultimo reset: %s\n", millis() / 1000, motivoReset());
      Serial.println("t_ms,setpoint,posicao,pwm");
    }
    return;
  }

  int esp = cmd.indexOf(' ');
  if (esp > 0) {
    String nome = cmd.substring(0, esp);
    float val = cmd.substring(esp + 1).toFloat();
    if (nome == "pwm")   { cmdPwm(val); return; }
    if (nome == "medir") { cmdMedir(constrain((int)val, 5, 300)); return; }
    if (cmdParametro(nome, val)) {
      Serial.printf("# %s = %g\n", nome.c_str(), val);
      if (nome == "kp" || nome == "ki" || nome == "kd") Serial.printf("# Kp=%.3f Ki=%.4f Kd=%.3f\n", Kp, Ki, Kd);
      return;
    }
    Serial.println("# comando invalido ou valor fora da faixa");
    return;
  }
  Serial.println("# use: 25 (setpoint) | 0 (desliga) | modo | pwm 30 | auto | kp/ki/kd (lista no topo do .ino)");
}

String entrada;
void lerSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') { processarComando(entrada); entrada = ""; }
    else entrada += c;
  }
}

// =====================================================================================================================
//  CONTROLE - roda a cada medida valida nova, com o dt real
// =====================================================================================================================
float mediana3(float a, float b, float c) {
  float t;
  if (a > b) { t = a; a = b; b = t; }
  if (b > c) { t = b; b = c; c = t; }
  if (a > b) { t = a; a = b; b = t; }
  return b;
}

void controlar(float dist, float dtc) {
  if (!iniciado) {
    m1 = m2 = m3 = dist;
    dist_f = dist_ant = dist;
    deriv_f = 0;
    sp_ref = dist;
    iniciado = true;
  }

  // ---- 1. Filtro: mediana de 3 -> passa-baixa -> derivada filtrada ----
  m1 = m2; m2 = m3; m3 = dist;
  float med = mediana3(m1, m2, m3);
  dist_f += ALFA * (med - dist_f);
  float derivBruta = (dist_f - dist_ant) / dtc;
  dist_ant = dist_f;
  deriv_f += BETA * (derivBruta - deriv_f);

  // ---- 2. Referencia: trajetoria (aceleracao limitada) ou rampa linear; na onda, degrau puro ----
  if (trajOn && !ondaAtiva) {
    float dif = setpoint - sp_ref;
    float vDes = (dif > 0 ? 1.0f : -1.0f) * min(VEL_SP, sqrtf(2.0f * trajAcel * fabsf(dif)));
    float dv = constrain(vDes - vTraj, -trajAcel * dtc, trajAcel * dtc);
    aTraj = dv / dtc;
    vTraj += dv;
    sp_ref += vTraj * dtc;
    if (fabsf(setpoint - sp_ref) < 0.5f && fabsf(vTraj) < 3.0f) { sp_ref = setpoint; vTraj = 0; aTraj = 0; }
  } else {
    vTraj = 0; aTraj = 0;
    float passo = ondaAtiva ? 1e6f : VEL_SP * dtc;
    float dif = setpoint - sp_ref;
    if (fabsf(dif) <= passo) sp_ref = setpoint;
    else sp_ref += (dif > 0) ? passo : -passo;
  }
  spBuf[spIdx] = sp_ref; spIdx = (spIdx + 1) % SPB_N;

  // ---- 3. Manual: so corte no topo e aprendizado do repouso ----
  if (modoManual) {
    if (med < DIST_TOPO && pwmManual > 0) {
      pwmManual = 0; degrauAtivo = false;
      Serial.println("# CORTE: carretel perto do sensor, blower desligado");
    }
    if (pwmManual <= 0.0f) {                // blower desligado ha > 2 s: a altura medida e o repouso
      if (tPwmZero == 0) tPwmZero = millis();
      else if (millis() - tPwmZero > 2000) altRepouso += 0.05f * (altura_cm(med) - altRepouso);
    } else tPwmZero = 0;
    u = pwmManual;
    vTraj = 0; aTraj = 0;
    decolou = false; tNoAr = 0;
    return;
  }
  tPwmZero = 0;

  // ---- 4. Corte de seguranca no topo ----
  if (emCorte) {
    u = 0; integral = 0; tNoAr = 0;
    if (dist_f > DIST_RELIGA) { emCorte = false; sp_ref = dist_f; Serial.println("# carretel desceu: controle reativado"); }
    return;
  }
  if (med < DIST_TOPO) {
    emCorte = true; u = 0; integral = 0;
    Serial.println("# CORTE: carretel perto do sensor, blower desligado ate ele descer");
    return;
  }

  // ---- 5. Decolagem: no fundo o PWM sobe em rampa ate o carretel soltar ----
  float altDec = (decAltFrac > 0.01f) ? constrain(decAltFrac * posCentro(setpoint), 2.0f, ALT_DECOLA) : ALT_DECOLA;
  bool zonaFundo = uDecola > 0 && altura_cm(med) < altRepouso + (decolou ? ALT_TOQUE : altDec);
  if (zonaFundo && decolou && !noFundo && toqueMs > 0) {      // toque curto em voo: o controle continua
    if (toqueT0 == 0) toqueT0 = millis();
    if (millis() - toqueT0 < toqueMs) zonaFundo = false;
  } else if (!zonaFundo) toqueT0 = 0;

  if (zonaFundo) {
    tNoAr = 0;
    if (!noFundo) {
      noFundo = true;
      if (decolou && toqueMs > 0)               { uDecAtual = feedforward(sp_ref) - 0.3f; decT0 = millis() - 3000; }  // preso em voo
      else if (millis() - decUltimoPID < 1500)  { uDecAtual = max(u, feedforward(sp_ref) - 0.3f); decT0 = millis() - 3000; }
      else                                      { uDecAtual = feedforward(sp_ref) - 1.0f; decT0 = millis(); }          // do repouso
    }
    if (decRampa > 0) {
      // 3 s logo abaixo do equilibrio (pre-gira o rotor), depois rampa lenta ate soltar
      if (millis() - decT0 > 3000) uDecAtual = min(uDecAtual + decRampa * dtc, max(uDecola + 2.0f, feedforward(sp_ref) + 3.0f));
      u = uDecAtual;
      avX = u; avUltimo = millis();         // overdrive acompanha: ao soltar, a queda do PWM vira freio
    } else u = uDecola;
    integral = 0;
    sp_ref = dist_f;
    vTraj = 0; aTraj = 0;
    return;
  }
  if (noFundo) {                            // acabou de soltar
    noFundo = false;
    decolou = true;
    if (decRampa > 0) { u = uDecAtual - decFreio; transicao = true; transicaoDecola = true; }
  }
  decUltimoPID = millis();

  // ---- 6. Termos do controle ----
  float kp = Kp;
  float ki = usaI ? Ki : 0.0f;
  float kd = usaD ? Kd : 0.0f;
  if (!usaI) integral = 0;

  float erro = dist_f - sp_ref;             // distancia maior = carretel mais baixo = precisa de mais PWM
  float uTraj = 0;
  if (trajOn) {
    // integral compara com a referencia de theta segundos atras; uTraj = PWM previsto para seguir a trajetoria
    int Nr = constrain((int)roundf(smTheta / tsMedio), 0, SPB_N - 2);
    erro = dist_f - spBuf[(spIdx - 1 - Nr + 2 * SPB_N) % SPB_N];
    float Kf = (ffK > 0.01f) ? ffK : smK, Tf = (ffTau > 0.001f) ? ffTau : smTau;
    uTraj = -(vTraj + Tf * aTraj) / (10.0f * Kf);
  }
  float u_ff = feedforward(ffMedida ? dist_f : sp_ref);

  // Smith: P e D enxergam a posicao prevista para daqui a theta
  float dh = 0, dvel = 0;
  if (smithOn) {
    if (millis() - smUltimo > 300) smithReset();
    smUltimo = millis();
    int N = constrain((int)roundf(smTheta / tsMedio), 1, SM_MAX - 1);
    smV += dtc / smTau * (10.0f * smK * smUpd - smV);
    smY += dtc * smV;
    int iOld = (smIdx - N + SM_MAX) % SM_MAX;
    dh = smY - smBufY[iOld];
    dvel = smV - smBufV[iOld];
    smBufY[smIdx] = smY; smBufV[smIdx] = smV;
    smIdx = (smIdx + 1) % SM_MAX;
    if (fabsf(smY) > 1000) {                // recentra (so as diferencas importam)
      float o = smY; smY = 0;
      for (int i = 0; i < SM_MAX; i++) smBufY[i] -= o;
    }
  }
  float termoP = kp * ((dist_f - dh) - sp_ref);
  float termoD = kd * ((deriv_f - dvel) - vTraj);   // com trajetoria: erro de velocidade
  smUpd = termoP + termoD + uTraj;

  if (transicao) {                          // entrada no controle sem tranco
    if (transicaoDecola && decSemPD) integral = constrain(u - u_ff, -I_MAX, I_MAX);
    else integral = constrain(u - u_ff - termoP - termoD - uTraj, -I_MAX, I_MAX);
    transicao = false; transicaoDecola = false;
  }

  // Reset do integral: no 1o cruzamento do novo setpoint (posicao prevista)
  if (aguardaCruzar) {
    int sinal = ((dist_f - dh) - setpoint > 0) ? 1 : -1;
    if (sinalErroTroca == 0) sinalErroTroca = sinal;
    else if (sinal != sinalErroTroca) {
      integral = iAntesTroca + (1.0f - resetPr) * (integral - iAntesTroca);
      aguardaCruzar = false;
    }
  }

  // ---- 7. Soma e limites ----
  float u_bruto = u_ff + termoP + integral + termoD + uTraj;
  float uMin = U_PISO, uMax = U_MAX;
  if (U_LIM > 0.01f) { uMin = max(uMin, u_ff - U_LIM); uMax = min(uMax, u_ff + U_LIM); }
  u = constrain(u_bruto, uMin, uMax);

  // ---- 8. ueq automatico: media lenta de (u - u_ff), transferida do integral ----
  tNoAr += dtc;
  if (ueqAuto && tNoAr > 3.0f && (!trajOn || fabsf(vTraj) < 1.0f)) {
    float uq0 = ueq;
    ueq = constrain(ueq + dtc / ueqTau * (u - u_ff), UEQ_MIN, UEQ_MAX);
    integral = constrain(integral - (ueq - uq0), -I_MAX, I_MAX);
  }

  // ---- 9. Overdrive: L(s) = (Tf s + 1)/(a Tf s + 1) no PWM ----
  if (temAv()) {
    if (millis() - avUltimo > 300) avX = u;
    avUltimo = millis();
    avX += dtc / (avancoA * avancoTf) * (u - avX);
    u = constrain(u / avancoA - (1.0f / avancoA - 1.0f) * avX, U_PISO, U_MAX);
  }

  // ---- 10. Integral: so perto do setpoint, sem insistir com o PWM saturado ----
  bool satAlto  = (u_bruto > uMax && erro > 0);
  bool satBaixo = (u_bruto < uMin && erro < 0);
  if (fabsf(erro) < BANDA_INT) { if (!satAlto && !satBaixo) integral += ki * erro * dtc; }
  else integral *= 0.98f;
  integral = constrain(integral, -I_MAX, I_MAX);
}

// =====================================================================================================================
//  SETUP
// =====================================================================================================================
void setup() {
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);                 // USB parada nao segura o loop
  bool pwmOk = ledcAttach(PIN_PWM, PWM_FREQ, PWM_BITS);
  u = 0;
  aplicarPWM();                             // blower desligado antes de qualquer espera
  delay(1500);
  if (!pwmOk) {
    Serial.println("# ERRO: PWM nao configurou. Parando.");
    while (true) delay(1000);
  }
  sp_ref = setpoint;

  prefs.begin("levitador", false);          // ueq aprendido no ultimo uso
  float uqF = prefs.getFloat(CHAVE_UEQ, NAN);
  if (!isnan(uqF) && uqF >= UEQ_MIN && uqF <= UEQ_MAX) ueq = uqF;
  ueqSalvo = ueq;

  // Sensor: destrava o I2C e faz soft reset antes de cada tentativa (um reset do ESP nao reinicia o VL53L0X)
  delay(100);
  for (int tent = 1; ; tent++) {
    destravarI2C();
    softResetSensor();
    sensor.setTimeout(500);
    if (sensor.init()) break;
    Serial.printf("# VL53L0X nao iniciou (tentativa %d): confira SDA/SCL e alimentacao\n", tent);
    u = 0; aplicarPWM();
    delay(tent < 10 ? 300 : 1000);
  }
  sensor.setTimeout(100);
  Wire.setClock(400000);
  sensor.setMeasurementTimingBudget(TB_US);
  sensor.startContinuous();

  Serial.printf("# LEVITADOR | carretel v1 com papel | Kp=%.3f Ki=%.4f Kd=%.3f | ueq %.2f%% (%s)\n",
                Kp, Ki, Kd, ueq, isnan(uqF) ? "padrao" : "da flash");
  Serial.printf("# Posicao = centro do carretel em cm acima do repouso. Setpoint %.0f a %.0f | 0 = desliga\n", POS_MIN, POS_MAX);
  mostrarModo();
  Serial.println("# \"modo\" lista: 1 P | 2 PI | 3 PID | 4 +Smith | 5 +Overdrive | 6 +Trajetoria | 7 completo");
  tUltimaResposta = millis();
#if USAR_BLE
  iniciarBLE();
  Serial.println("# Bluetooth LE ligado: \"Levitador\"");
#endif
  enableLoopWDT();                          // loop travado > 5 s -> reinicia (PWM volta a 0)
  Serial.println("# Inicia DESLIGADO. Digite o setpoint e Enter (ex.: 25).");
}

// =====================================================================================================================
//  LOOP
// =====================================================================================================================
uint32_t hbT0 = 0, hbLoops = 0, hbMaxUs = 0, hbMedidas = 0, hbReinit = 0, hbUltLoop = 0;

void loop() {
  // ---- diagnostico (so no modo CSV): batimento a cada 10 s ----
  uint32_t agoraUs = micros();
  if (hbUltLoop) hbMaxUs = max(hbMaxUs, agoraUs - hbUltLoop);
  hbUltLoop = agoraUs; hbLoops++;
  if (millis() - hbT0 >= 10000) {
    if (saidaCSV && hbT0) Serial.printf("# hb %lu s | loops/s %lu | maior loop %lu ms | medidas/s %.1f | reinicios do sensor %lu\n",
                                        millis() / 1000, hbLoops / 10, hbMaxUs / 1000, hbMedidas / 10.0f, hbReinit);
    hbT0 = millis(); hbLoops = 0; hbMaxUs = 0; hbMedidas = 0;
  }

  // ---- comandos ----
  lerSerial();
#if USAR_BLE
  if (bleTemCmd) {
    String c(bleBuf);
    bleTemCmd = false;
    c.trim(); c.toLowerCase();
    char r[64];
    if (permitidoBLE(c)) {
      bleCmds++;
      Serial.printf("# [BLE] %s\n", c.c_str());
      processarComando(c);
      snprintf(r, sizeof(r), "> ok: %s\n", c.c_str());
      bleEnviar(r);
      if (c.startsWith("modo")) {
        int m = modoAtual();
        snprintf(r, sizeof(r), "> controle: %s\n", m > 0 ? MODO_CURTO[m] : nomeControle().c_str());
        bleEnviar(r);
      }
    } else {
      bleRecusados++;
      bleEnviar("> pelo celular: numero (setpoint), 0 (desliga), sp X, auto ou modo 1-7\n");
    }
  }
#endif

  // ---- ensaios: onda de setpoint e degrau de PWM ----
  if (ondaAtiva && !modoManual) setpoint = (((millis() - testeInicio) / ondaMeioMs) % 2) ? ondaB : ondaA;
  if (degrauAtivo) {
    uint32_t dtD = millis() - degrauT0;
    if (!modoManual) degrauAtivo = false;
    else if (!degrauAplicado && dtD >= degrauEsperaMs) { degrauAplicado = true; pwmManual = u = degrauB; aplicarPWM(); }
    else if (degrauAplicado && dtD >= degrauEsperaMs + degrauDuracaoMs) {
      degrauAtivo = false; pwmManual = u = degrauA; aplicarPWM();
      Serial.println("# fim do degrau");
    }
  }

  if (saidaCSV && millis() - tUeqMsg > 10000) {   // ueq aprendido (aviso no CSV)
    tUeqMsg = millis();
    if (fabsf(ueq - ueqMsg) >= 0.02f) { ueqMsg = ueq; Serial.printf("# ueq auto = %.2f%%\n", ueq); }
  }

  // ---- sensor: so age quando ha medida nova; watchdog se ele parar ----
  float dist;
  if (!novaMedida(dist)) {
    if (!semSensor && millis() - tUltimaResposta > WATCHDOG_MS) {
      semSensor = true;
      if (!modoManual && !emCorte) u = FATOR_SEGURO * feedforward(sp_ref);
      else if (modoManual) { pwmManual = 0; u = 0; degrauAtivo = false; }
      aplicarPWM();
      Serial.println("# ERRO: sensor parou de responder, PWM de seguranca");
    }
    static uint32_t tReinit = 0;
    if (semSensor && millis() - tReinit > 1000) {
      tReinit = millis(); hbReinit++;
      if (reiniciarSensor()) { tUltimaResposta = millis(); Serial.println("# sensor reiniciado"); }
    }
    return;
  }
  tUltimaResposta = millis(); hbMedidas++;
  if (semSensor) { semSensor = false; Serial.println("# sensor voltou"); }

  static uint32_t tUltimo = micros();
  uint32_t agora = micros();
  float dtc = constrain((agora - tUltimo) * 1e-6f, 0.015f, 0.2f);
  tUltimo = agora;
  if (dtc < 0.1f) tsMedio += 0.02f * (dtc - tsMedio);

  // ---- controle ----
  if (isnan(dist)) {
    falhasSeguidas++;
    if (falhasSeguidas > FALHAS_MAX && !modoManual && !emCorte) u = FATOR_SEGURO * feedforward(sp_ref);
  } else {
    falhasSeguidas = 0;
    controlar(dist, dtc);
  }
  aplicarPWM();

  // ---- saida ----
  float spMostra  = modoManual ? 0.0f : posCentro(setpoint);
  float posMostra = posCentro(dist_f);
  int   modo      = modoAtual();
#if USAR_BLE
  static uint32_t tBle = 0;
  if (bleConectado && millis() - tBle >= 500) {
    tBle = millis();
    char b[72];
    snprintf(b, sizeof(b), "SP %.1f | Pos %.1f | PWM %.0f | %s\n", spMostra, posMostra, u_real, MODO_CURTO[modo]);
    bleEnviar(b);
  }
#endif
  if (saidaCSV) {
    Serial.printf("%lu,%.1f,%.1f,%.1f\n", (unsigned long)millis(), spMostra, isnan(dist) ? NAN : posMostra, u_real);
    return;
  }
  static uint32_t tModoMsg = 0;             // lembrete do controle ativo a cada 10 s (sem ":" para o Plotter)
  if (millis() - tModoMsg >= 10000) {
    tModoMsg = millis();
    if (modo > 0) Serial.printf("# controle ativo = modo %d (%s)\n", modo, MODO_CURTO[modo]);
    else          Serial.printf("# controle ativo = %s\n", nomeControle().c_str());
  }
  // Serial Monitor: "Nome:valor" separados por TAB; o controle ativo vai por nome (ex.: Controle:PID+Smith)
  Serial.printf("Setpoint:%.1f\tPosicao:%.1f\tPWM:%.1f\tControle:%s\n", spMostra, posMostra, u_real, MODO_CURTO[modo]);
}
