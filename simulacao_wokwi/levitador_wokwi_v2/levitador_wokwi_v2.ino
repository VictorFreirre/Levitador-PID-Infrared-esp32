// =====================================================================================================================
//  LEVITADOR - SIMULACAO NO WOKWI (ESP32-C3), versao 2 (21/11/2026)
//  A planta e simulada dentro do proprio programa; o controle e o mesmo do firmware final (modo 7, ja em voo).
//
//  Planta (passo de 2 ms):
//    PWM -> atraso puro de 0,48 s -> rotor do blower (1a ordem, 1,5 s)        [identificacao na bancada]
//    -> velocidade do ar na entrada v_ar = v_eq + KV (PWM_ef + perturbacao - 42,4 %)
//    -> forca no carretel F = a (v_ar - v_carretel)^n, a = 0,921, n = 1,75    [SimScale, carretel v1]
//    -> m z'' = F - m g (m = 10,14 g)
//  Sensor: uma medida a cada 30,8 ms, ruido de 0,8 mm (desvio medido com o carretel parado).
//  Perturbacao do escoamento: ruido lento (1a ordem, 1 s) de 0,1 % de PWM equivalente.
//
//  Saida serial (CSV): t_s,setpoint_cm,posicao_medida_cm,posicao_real_cm,pwm_pct
//  O tempo e o tempo SIMULADO (o programa nao espera o relogio).
// =====================================================================================================================
#include <math.h>

// ---------------- roteiro do ensaio ----------------
const float T_FIM = 130.0f;                          // s
const float ROT_T[] = {10, 40, 70, 100};             // instantes das trocas (s)
const float ROT_SP[] = {33, 15, 33, 15};             // novas referencias (cm, centro do carretel acima do repouso)
const int ROT_N = 4;
const float SP_INICIAL = 15.0f;
const int SAIDA_CADA = 2;                            // imprime 1 de cada 2 amostras (~16 Hz)

// ---------------- planta ----------------
const float M = 0.01014f, G = 9.81f;                 // kg, m/s2
const float A_F = 0.921f, N_F = 1.75f;               // F = A_F v^N_F (SimScale)
const float U_EQ0 = 42.4f;                           // % (equilibrio identificado)
const float KV = 0.08f;                              // m/s de ar por % de PWM (=> 8 cm/s/% no carretel)
const float THETA = 0.48f, TAU = 1.50f;              // s (identificacao)
const float SIG_P = 0.10f, TAU_P = 1.0f;             // perturbacao: % de PWM, s
const float RUIDO_MM = 0.8f;
const float DT = 0.002f;                             // passo da planta (s)
const int   NPERT = 5;                               // a perturbacao e sorteada a cada NPERT passos (10 ms)
const float TS = 0.0308f;                            // periodo do sensor (s)
const float POS_ZERO_CM = 54.4f;                     // sensor -> centro do carretel em repouso (cm)
const int NATRASO = 240;                             // THETA / DT

float V_EQ;                                          // velocidade do ar no equilibrio (calculada no setup)
float z = 0.15f, zd = 0;                             // m, m/s
float w = U_EQ0, pert = 0;
float atraso[NATRASO];
int ia = 0;

// ---------------- controle (mesmo do firmware) ----------------
float Kp = 0.09f, Ki = 0.006f, Kd = 0.09f;           // %/mm, %/(mm s), %/(mm/s)
const float BANDA_INT = 100, I_MAX = 15, U_LIM = 9, VEL_SP = 20, ALFA = 0.5f, BETA = 0.5f;
const float trajAcel = 10, ffK = 3.0f, ffTau = 0.45f;
const float smK = 2.2f, smTau = 0.43f, smTheta = 0.60f;
const float avancoTf = 0.6f, avancoA = 0.4f, ueqTau = 30, resetPr = 1.0f;

float u = U_EQ0, ueq = U_EQ0, integral = 0;
float setpoint, sp_ref, vTraj = 0, aTraj = 0;
float dist_f, dist_ant, deriv_f = 0, m1, m2, m3;
const int NB = 64;
float spBuf[NB], smBufY[NB], smBufV[NB];
int spIdx = 0, smIdx = 0;
float smY = 0, smV = 0, smUpd = 0, avX = U_EQ0, tNoAr = 0;
float iAntesTroca = 0; bool aguardaCruzar = false; int sinalErroTroca = 0;

// ---------------- numeros aleatorios (LCG + Box-Muller, repetivel) ----------------
uint32_t semente = 12345;
float unif() { semente = semente * 1664525u + 1013904223u; return ((semente >> 8) + 0.5f) / 16777216.0f; }
float gauss() { return sqrtf(-2.0f * logf(unif())) * cosf(6.2831853f * unif()); }

float mediana3(float a, float b, float c) {
  float t;
  if (a > b) { t = a; a = b; b = t; }
  if (b > c) { t = b; b = c; c = t; }
  if (a > b) { t = a; a = b; b = t; }
  return b;
}
float lim(float x, float a, float b) { return x < a ? a : (x > b ? b : x); }

// ---------------- planta: um passo de 1 ms ----------------
void passoPlanta() {
  float ud = atraso[ia]; atraso[ia] = u; ia = (ia + 1) % NATRASO;
  w += DT / TAU * (ud - w);
  static int np = 0;
  if (++np >= NPERT) { np = 0; const float dp = NPERT * DT; pert += dp / TAU_P * (-pert) + SIG_P * sqrtf(2.0f * dp / TAU_P) * gauss(); }
  float v_ar = V_EQ + KV * (w + pert - U_EQ0);
  float vrel = v_ar - zd;
  float F = (vrel >= 0 ? 1.0f : -1.0f) * A_F * powf(fabsf(vrel), N_F);
  zd += (F - M * G) / M * DT;
  z += zd * DT;
  if (z <= 0 && zd < 0) { z = 0; zd = 0; }
}

// ---------------- controle: igual ao firmware (passos 1, 2, 6 a 10) ----------------
void controlar(float dist) {
  const float dtc = TS;
  m1 = m2; m2 = m3; m3 = dist;
  float med = mediana3(m1, m2, m3);
  dist_f += ALFA * (med - dist_f);
  float derivBruta = (dist_f - dist_ant) / dtc;
  dist_ant = dist_f;
  deriv_f += BETA * (derivBruta - deriv_f);

  float dif = setpoint - sp_ref;
  float vDes = (dif > 0 ? 1.0f : -1.0f) * fminf(VEL_SP, sqrtf(2.0f * trajAcel * fabsf(dif)));
  float dv = lim(vDes - vTraj, -trajAcel * dtc, trajAcel * dtc);
  aTraj = dv / dtc; vTraj += dv; sp_ref += vTraj * dtc;
  if (fabsf(setpoint - sp_ref) < 0.5f && fabsf(vTraj) < 3.0f) { sp_ref = setpoint; vTraj = 0; aTraj = 0; }
  spBuf[spIdx] = sp_ref; spIdx = (spIdx + 1) % NB;

  int N = (int)roundf(smTheta / TS);
  float erro = dist_f - spBuf[(spIdx - 1 - N + 2 * NB) % NB];
  float uTraj = -(vTraj + ffTau * aTraj) / (10.0f * ffK);
  float u_ff = ueq;

  smV += dtc / smTau * (10.0f * smK * smUpd - smV);
  smY += dtc * smV;
  int iOld = (smIdx - N + NB) % NB;
  float dh = smY - smBufY[iOld], dvel = smV - smBufV[iOld];
  smBufY[smIdx] = smY; smBufV[smIdx] = smV; smIdx = (smIdx + 1) % NB;

  float termoP = Kp * ((dist_f - dh) - sp_ref);
  float termoD = Kd * ((deriv_f - dvel) - vTraj);
  smUpd = termoP + termoD + uTraj;

  if (aguardaCruzar) {
    int sinal = ((dist_f - dh) - setpoint > 0) ? 1 : -1;
    if (sinalErroTroca == 0) sinalErroTroca = sinal;
    else if (sinal != sinalErroTroca) { integral = iAntesTroca + (1.0f - resetPr) * (integral - iAntesTroca); aguardaCruzar = false; }
  }

  float u_bruto = u_ff + termoP + integral + termoD + uTraj;
  float uMin = fmaxf(0, u_ff - U_LIM), uMax = fminf(100, u_ff + U_LIM);
  float uc = lim(u_bruto, uMin, uMax);

  tNoAr += dtc;
  if (tNoAr > 3.0f && fabsf(vTraj) < 1.0f) {
    float uq0 = ueq;
    ueq = lim(ueq + dtc / ueqTau * (uc - u_ff), 30, 70);
    integral = lim(integral - (ueq - uq0), -I_MAX, I_MAX);
  }

  avX += dtc / (avancoA * avancoTf) * (uc - avX);
  u = lim(uc / avancoA - (1.0f / avancoA - 1.0f) * avX, 0, 100);

  bool satAlto = (u_bruto > uMax && erro > 0), satBaixo = (u_bruto < uMin && erro < 0);
  if (fabsf(erro) < BANDA_INT) { if (!satAlto && !satBaixo) integral += Ki * erro * dtc; }
  else integral *= 0.98f;
  integral = lim(integral, -I_MAX, I_MAX);
}

void setup() {
  Serial.begin(115200);
  delay(500);
  V_EQ = powf(M * G / A_F, 1.0f / N_F);
  for (int i = 0; i < NATRASO; i++) atraso[i] = U_EQ0;
  float d0 = (POS_ZERO_CM - SP_INICIAL) * 10.0f;
  setpoint = sp_ref = dist_f = dist_ant = m1 = m2 = m3 = d0;
  for (int i = 0; i < NB; i++) { spBuf[i] = d0; smBufY[i] = 0; smBufV[i] = 0; }
  Serial.printf("# Levitador simulado: carretel 10,14 g, F = %.3f v^%.2f (SimScale), v_eq = %.3f m/s\n", A_F, N_F, V_EQ);
  Serial.println("t_s,setpoint_cm,posicao_medida_cm,posicao_real_cm,pwm_pct");
}

void loop() {
  static float t = 0, proxMedida = 0;
  static int k = 0, r = 0;
  static bool fim = false;
  if (fim) { delay(1000); return; }
  while (t < proxMedida) { passoPlanta(); t += DT; }
  proxMedida += TS;

  if (r < ROT_N && t >= ROT_T[r]) {                  // troca de referencia
    setpoint = (POS_ZERO_CM - ROT_SP[r]) * 10.0f;
    iAntesTroca = integral; aguardaCruzar = true; sinalErroTroca = 0;
    r++;
  }
  float dist = (POS_ZERO_CM - 100.0f * z) * 10.0f + RUIDO_MM * gauss();
  controlar(dist);

  if (k++ % SAIDA_CADA == 0)
    Serial.printf("%.3f,%.1f,%.2f,%.2f,%.2f\n", t, POS_ZERO_CM - setpoint / 10.0f, POS_ZERO_CM - dist / 10.0f, 100.0f * z, u);
  if (t >= T_FIM) { Serial.println("# fim"); fim = true; }
}
