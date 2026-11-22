"""
Prototipo em Python da simulacao do Wokwi (mesma planta e mesma lei de controle do sketch simulacao_wokwi_v2.ino),
para ajustar o modelo antes de rodar no Wokwi.
Planta: PWM -> atraso puro (0,48 s) -> rotor do blower (1a ordem, 1,5 s) -> velocidade do ar na entrada ->
forca do SimScale F = a (v_ar - v_carretel)^n sobre o carretel (10,14 g) -> posicao. Sensor a cada 30,8 ms com ruido.
Uso: python sim/wokwi_prototipo.py [K_ar_m_s_por_pct] [sigma_pert_pct]
"""
import sys

import numpy as np

KV = float(sys.argv[1]) if len(sys.argv) > 1 else 0.08     # m/s de ar por % de PWM (=> 8 cm/s/% no carretel)
SIG_P = float(sys.argv[2]) if len(sys.argv) > 2 else 0.3   # % de PWM equivalente (perturbacao lenta do escoamento)
rng = np.random.default_rng(1)

# ---- planta ----
M, G = 0.01014, 9.81
A_F, N_F = 0.921, 1.75
V_EQ = (M * G / A_F) ** (1 / N_F)         # 0,279 m/s
U_EQ0 = 42.4
THETA, TAU = 0.48, 1.50
TAU_P = 1.0                               # s, perturbacao
TS = 0.0308
POS_ZERO = 54.4                           # cm: distancia sensor -> centro em repouso (firmware: 57.8 - 3.4)


def simular(roteiro, dur):
    dt = 0.001
    z, zd = 15.0 / 100, 0.0               # m (posicao do centro acima do repouso), m/s
    w = U_EQ0; buf = [U_EQ0] * int(round(THETA / dt)); pert = 0.0
    # ---- controle (igual ao firmware, modo 7, ja em voo) ----
    Kp, Ki, Kd = 0.09, 0.006, 0.09
    smK, smTau, smTh = 2.2, 0.43, 0.60
    ffK, ffTau, acel, vmax = 3.0, 0.45, 10.0, 20.0
    ulim, imax, banda, a_av, tf_av = 9.0, 15.0, 100.0, 0.4, 0.6
    ALFA, BETA = 0.5, 0.5
    d0 = (POS_ZERO - 15.0) * 10
    m1 = m2 = m3 = d0; dist_f = dist_ant = d0; deriv_f = 0.0
    sp = sp_ref = d0; vT = aT = 0.0
    Nsm = int(round(smTh / TS)); bY = [0.0] * 64; bV = [0.0] * 64; si = 0; smY = smV = smUpd = 0.0
    spb = [d0] * 64; spi = 0
    integ = 0.0; ueq = U_EQ0; avX = U_EQ0; u = U_EQ0
    aguarda = False; iAnt = 0.0; sinal0 = 0
    t = 0.0; prox = 0.0; out = []
    nsub = 0
    while t < dur:
        # ---- planta, passo de 1 ms ----
        buf.append(u); ud = buf.pop(0)
        w += dt / TAU * (ud - w)
        pert += dt / TAU_P * (-pert) + SIG_P * np.sqrt(2 * dt / TAU_P) * rng.standard_normal()
        v_ar = V_EQ + KV * (w + pert - U_EQ0)
        vrel = v_ar - zd
        F = A_F * np.sign(vrel) * abs(vrel) ** N_F
        zdd = (F - M * G) / M
        zd += zdd * dt; z += zd * dt
        if z <= 0 and zd < 0: z, zd = 0.0, 0.0
        t += dt
        if t < prox: continue
        prox += TS
        # ---- sensor ----
        dist = (POS_ZERO - 100 * z) * 10 + 0.8 * rng.standard_normal()
        for (t0, alvo) in roteiro:
            if abs(t - t0) < TS / 2:
                sp = (POS_ZERO - alvo) * 10; iAnt = integ; aguarda = True; sinal0 = 0
        # 1. filtros
        m1, m2, m3 = m2, m3, dist
        med = sorted((m1, m2, m3))[1]
        dist_f += ALFA * (med - dist_f)
        der = (dist_f - dist_ant) / TS; dist_ant = dist_f; deriv_f += BETA * (der - deriv_f)
        # 2. trajetoria
        dif = sp - sp_ref
        vDes = np.sign(dif) * min(vmax, np.sqrt(2 * acel * abs(dif)))
        dv = np.clip(vDes - vT, -acel * TS, acel * TS); aT = dv / TS; vT += dv; sp_ref += vT * TS
        if abs(sp - sp_ref) < 0.5 and abs(vT) < 3: sp_ref, vT, aT = sp, 0.0, 0.0
        spb[spi] = sp_ref; spi = (spi + 1) % 64
        # 6. termos
        erro = dist_f - spb[(spi - 1 - Nsm) % 64]
        uT = -(vT + ffTau * aT) / (10 * ffK)
        u_ff = ueq
        smV += TS / smTau * (10 * smK * smUpd - smV); smY += TS * smV
        io = (si - Nsm) % 64; dh = smY - bY[io]; dvel = smV - bV[io]; bY[si] = smY; bV[si] = smV; si = (si + 1) % 64
        P = Kp * ((dist_f - dh) - sp_ref); D = Kd * ((deriv_f - dvel) - vT)
        smUpd = P + D + uT
        if aguarda:
            s = 1 if (dist_f - dh) - sp > 0 else -1
            if sinal0 == 0: sinal0 = s
            elif s != sinal0: integ = iAnt; aguarda = False
        ub = u_ff + P + integ + D + uT
        uMin, uMax = u_ff - ulim, u_ff + ulim
        uc = min(max(ub, uMin), uMax)
        if abs(vT) < 1:
            uq0 = ueq; ueq += TS / 30 * (uc - u_ff); integ = np.clip(integ - (ueq - uq0), -imax, imax)
        avX += TS / (a_av * tf_av) * (uc - avX); u = float(np.clip(uc / a_av - (1 / a_av - 1) * avX, 0, 100))
        satA = ub > uMax and erro > 0; satB = ub < uMin and erro < 0
        if abs(erro) < banda:
            if not satA and not satB: integ += Ki * erro * TS
        else: integ *= 0.98
        integ = float(np.clip(integ, -imax, imax))
        out.append((t, POS_ZERO - sp / 10, POS_ZERO - dist / 10, 100 * z, u))
    return np.array(out)


if __name__ == "__main__":
    rot = [(10, 33), (40, 15), (70, 33), (100, 15)]          # mesmo roteiro do sketch
    r = simular(rot, 130)
    t, sp, pm, z, u = r.T
    for (t0, alvo), (t1, _) in zip(rot, rot[1:] + [(130, 0)]):
        ini = 15 if alvo == 33 else 33
        m = (t >= t0) & (t < t1)
        zz = z[m]; y = np.convolve(np.concatenate([np.full(16, zz[0]), zz, np.full(15, zz[-1])]), np.ones(32) / 32, mode="valid")
        passo = alvo - ini; sg = np.sign(passo)
        ch = np.where(sg * (y - alvo) >= 0)[0]
        pico = max(0, np.max(sg * (y[ch[0]:ch[0] + int(10 / 0.0308)] - alvo))) if len(ch) else np.nan
        reg = m & (t > t1 - 15)
        print(f"{ini}->{alvo}: pico {pico:.2f} cm ({100*pico/abs(passo):.1f}%), erro {np.mean(z[reg])-alvo:+.2f} cm, dp {np.std(z[reg]):.2f} cm")
    reg = (t > 3) & (t < 10)
    print(f"regime inicial 15 cm: dp {np.std(z[reg]):.2f} cm, PWM {np.mean(u[reg]):.1f} +- {np.std(u[reg]):.2f} %")
