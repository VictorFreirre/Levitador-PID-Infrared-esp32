"""
Identificacao pelos degraus de PWM em malha aberta gravados com medir_k.py (versao de uso; em manual a coluna sp = 0).
Alinha todos os degraus no instante da troca de PWM, normaliza pelo tamanho (com sinal) e tira a media -> resposta media
em cm por % de PWM. Ajusta:
   A)  K e^(-theta s) / ( s (tau s + 1) )
   B)  K e^(-theta s) / ( s (tau1 s + 1)(tau2 s + 1) )
A media de degraus +d e -d cancela a velocidade inicial (perturbacao) e mostra quanto do atraso e TEMPO MORTO de verdade
(nao da para compensar) e quanto e constante de tempo (da para compensar com avanco / estimador).
Uso: python identificar_degraus.py saida.png dados/a.csv [dados/b.csv ...]
"""
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

args = [a for a in sys.argv[1:] if not a.startswith("--tmax=")]
TMAX = ([float(a[7:]) for a in sys.argv[1:] if a.startswith("--tmax=")] or [2.0])[0]   # duracao util do degrau (s)
OUT, ARQS = args[0], args[1:]
TG = np.arange(-0.3, TMAX + 0.01, 0.03)      # grade de tempo comum (s)

R, D = [], []
for arq in ARQS:
    d = np.genfromtxt(arq, delimiter=",", skip_header=1)
    d = d[~np.isnan(d).any(axis=1)]
    t, sp, y, u = d[:, 0] / 1000, d[:, 1], d[:, 2], d[:, 3]
    i = 1
    while i < len(t):
        if sp[i] == 0 and sp[i - 1] > 0 and u[i] > 20:           # entrou em manual (comando degrau)
            j = i
            while j + 1 < len(t) and sp[j + 1] == 0:
                j += 1
            seg = slice(i, j + 1)
            k = np.where(np.abs(u[seg] - u[i]) > 0.2)[0]
            if len(k):
                k0 = i + k[0]; dd = u[k0] - u[i]
                # instante da troca: entre a amostra k0-1 e k0 (o PWM muda na hora, a amostra vem ate 31 ms depois)
                t0 = t[k0] - 0.015
                tt = t - t0
                m = (tt > -0.5) & (tt < TMAX + 0.05)
                if tt[m].max() >= TMAX - 0.1 and y[m].max() < 50.0 and y[m].min() > 3.5:   # fim de curso ~51 cm; fundo ~1,9 cm
                    yy = np.interp(TG, tt[m], y[m])
                    y0 = yy[(TG > -0.25) & (TG <= 0)].mean()
                    R.append((yy - y0) / dd); D.append(dd)
            i = j + 1
        else:
            i += 1
R, D = np.array(R), np.array(D)
print(f"degraus aproveitados: {len(D)} (subindo {np.sum(D > 0)}, descendo {np.sum(D < 0)}), tamanho medio {np.mean(np.abs(D)):.2f} %")
# media equilibrada: media dos +d e media dos -d, depois a media das duas (cancela a deriva)
mu = [R[D > 0].mean(0), R[D < 0].mean(0)]
med = 0.5 * (mu[0] + mu[1])
ep = R.std(0) / np.sqrt(len(D))


def sim(K, th, taus, tg=TG):
    dt = 0.002; n = int((TMAX + 0.3) / dt); x = np.zeros(len(taus)); yv = 0.0; out = np.zeros(n)
    for k in range(n):
        tk = k * dt
        inp = 1.0 if tk >= th else 0.0
        for q, tau in enumerate(taus):
            x[q] += dt / tau * (inp - x[q]); inp = x[q]
        yv += dt * K * inp; out[k] = yv
    return np.interp(tg, np.arange(n) * dt, out)


def ajusta(ntau):
    best = None
    ths = np.arange(0.0, 0.9, 0.03)
    t1s = np.arange(0.1, 2.5, 0.05)
    t2s = [None] if ntau == 1 else np.arange(0.05, 1.0, 0.05)
    w = (TG >= 0)
    for th in ths:
        for t1 in t1s:
            for t2 in t2s:
                if t2 is not None and t2 > t1:
                    continue
                taus = [t1] if t2 is None else [t1, t2]
                b = sim(1.0, th, taus)
                K = float(np.sum(b[w] * med[w]) / np.sum(b[w] ** 2))
                e = float(np.sqrt(np.mean((K * b[w] - med[w]) ** 2)))
                if best is None or e < best[0]:
                    best = (e, K, th, taus)
    return best


A = ajusta(1); B = ajusta(2)
print(f"A) K {A[1]:.2f} cm/s/%  theta {A[2]:.2f} s  tau {A[3][0]:.2f} s                 erro rms {A[0]:.3f} cm/%")
print(f"B) K {B[1]:.2f} cm/s/%  theta {B[2]:.2f} s  tau1 {B[3][0]:.2f} s  tau2 {B[3][1]:.2f} s   erro rms {B[0]:.3f} cm/%")
# sensibilidade: melhor ajuste B com theta fixo
w = (TG >= 0)
for th in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7):
    bb = None
    for t1 in np.arange(0.1, 2.5, 0.05):
        for t2 in np.arange(0.05, 1.0, 0.05):
            if t2 > t1: continue
            b = sim(1.0, th, [t1, t2]); K = float(np.sum(b[w] * med[w]) / np.sum(b[w] ** 2))
            e = float(np.sqrt(np.mean((K * b[w] - med[w]) ** 2)))
            if bb is None or e < bb[0]: bb = (e, K, t1, t2)
    print(f"   theta fixo {th:.1f}: K {bb[1]:5.2f} tau1 {bb[2]:.2f} tau2 {bb[3]:.2f}  erro {bb[0]:.3f}")
# primeiro instante em que a media sai do ruido (2 erros-padrao)
k = np.where((TG > 0) & (np.abs(med) > 2 * ep + 0.05))[0]
print(f"a resposta media sai do ruido em t = {TG[k[0]]:.2f} s" if len(k) else "resposta nao saiu do ruido")
# inicio do movimento: instante em que a velocidade media passa de 20% e de 50% da velocidade final (media do ultimo 0,3 s)
velm = np.gradient(np.convolve(med, np.ones(5) / 5, mode="same"), TG)
vfim = velm[(TG > TMAX - 0.4) & (TG < TMAX - 0.1)].mean()
for fr in (0.2, 0.5):
    kk = np.where((TG > 0.05) & (velm > fr * vfim))[0]
    if len(kk): print(f"velocidade media passa de {int(fr*100)}% da final ({vfim:.1f} cm/s/%) em t = {TG[kk[0]]:.2f} s")

fig, ax = plt.subplots(1, 2, figsize=(15, 5.2))
for r in R:
    ax[0].plot(TG, r, color="silver", lw=0.5)
ax[0].plot(TG, mu[0], "r-", lw=1, label="media dos degraus para cima"); ax[0].plot(TG, mu[1], "b-", lw=1, label="media dos degraus para baixo")
ax[0].plot(TG, med, "k-", lw=2.2, label=f"media (n = {len(D)})")
ax[0].plot(TG, sim(A[1], A[2], A[3]), "g--", lw=1.5, label=f"A: K {A[1]:.1f}, atraso {A[2]:.2f} s, tau {A[3][0]:.2f} s")
ax[0].plot(TG, sim(B[1], B[2], B[3]), "m:", lw=2, label=f"B: K {B[1]:.1f}, atraso {B[2]:.2f} s, tau {B[3][0]:.2f} e {B[3][1]:.2f} s")
ax[0].axvline(0, color="k", lw=0.5); ax[0].set_xlabel("tempo depois do degrau de PWM (s)"); ax[0].set_ylabel("deslocamento por % de PWM (cm/%)")
ax[0].set_ylim(-3, max(12, med.max() * 1.5)); ax[0].grid(alpha=.3); ax[0].legend(fontsize=8); ax[0].set_title("resposta ao degrau de PWM em malha aberta")
vel = np.gradient(np.convolve(med, np.ones(5) / 5, mode="same"), TG)
ax[1].plot(TG, vel, "k-", lw=1.8, label="velocidade media (cm/s por %)")
ax[1].plot(TG, np.gradient(sim(A[1], A[2], A[3]), TG), "g--", label="modelo A"); ax[1].plot(TG, np.gradient(sim(B[1], B[2], B[3]), TG), "m:", lw=2, label="modelo B")
ax[1].axvline(0, color="k", lw=0.5); ax[1].grid(alpha=.3); ax[1].legend(); ax[1].set_xlabel("tempo depois do degrau (s)"); ax[1].set_title("velocidade")
fig.tight_layout(); fig.savefig(OUT, dpi=80)
