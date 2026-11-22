"""
Analise da simulacao no Wokwi (versao 2, 21/11/2026): dados/uso23_wokwi_v2.csv, gravado do monitor serial do Wokwi.
Gera relatorio/figuras/fig_wokwi_v2.png e imprime as metricas com as mesmas definicoes do ensaio de bancada
(sobressinal com media movel de 1 s nos 10 s seguintes a 1a chegada; erro de regime = media dos ultimos 15 s).
Uso: python sim/wokwi_analise.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({"font.size": 10, "axes.grid": True, "grid.alpha": 0.3, "savefig.dpi": 150, "figure.dpi": 100})
SPAN = 44.0
d = np.genfromtxt("dados/uso23_wokwi_v2.csv", delimiter=",", names=True)
t, sp, pm, pr, u = d["t_s"], d["setpoint_cm"], d["posicao_medida_cm"], d["posicao_real_cm"], d["pwm_pct"]
dt = np.median(np.diff(t))
print(f"{len(t)} pontos, {t[0]:.2f} a {t[-1]:.2f} s, passo de saida {1000*dt:.1f} ms")

trocas = np.where(np.diff(sp) != 0)[0] + 1
lims = list(trocas) + [len(t)]
print("regime inicial (15 cm, 3 a 10 s): dp medida %.2f cm, real %.2f cm" % (np.std(pm[(t > 3) & (t < 10)]), np.std(pr[(t > 3) & (t < 10)])))
linhas = []
nmed = max(1, int(round(1.0 / dt)))
for i, k in enumerate(trocas):
    seg = slice(k, lims[i + 1])
    tt = t[seg] - t[k]; y = pm[seg]
    yp = np.concatenate([np.full(nmed // 2, y[0]), y, np.full(nmed - 1 - nmed // 2, y[-1])])
    ys = np.convolve(yp, np.ones(nmed) / nmed, mode="valid")          # media movel de 1 s, centrada
    a, b = sp[k - 1], sp[k]; passo = b - a; sg = np.sign(passo)
    ch = np.where(sg * (ys - b) >= 0)[0]
    j0 = ch[0]; j1 = j0 + int(10 / dt)
    pico = max(0.0, np.max(sg * (ys[j0:j1] - b)))
    pico_bruto = max(0.0, np.max(sg * (y[j0:j1] - b)))
    reg = tt > tt[-1] - 15
    erro = np.mean(y[reg]) - b
    a10 = np.where(sg * (ys - (a + 0.1 * passo)) >= 0)[0][0]; a90 = np.where(sg * (ys - (a + 0.9 * passo)) >= 0)[0][0]
    linhas.append((a, b, pico, 100 * pico / abs(passo), 100 * pico_bruto / abs(passo), 100 * erro / SPAN, 100 * erro / b,
                   tt[a90] - tt[a10], np.std(y[reg])))
    print(f"{a:.0f}->{b:.0f}: sobressinal {pico:.2f} cm = {100*pico/abs(passo):.1f}% (sem suavizar {100*pico_bruto/abs(passo):.1f}%), "
          f"erro {erro:+.2f} cm = {100*erro/SPAN:+.2f}% faixa ({100*erro/b:+.2f}% ref), subida 10-90 {tt[a90]-tt[a10]:.1f} s, dp regime {np.std(y[reg]):.2f} cm")

fig, ax = plt.subplots(2, 1, figsize=(11, 5.6), sharex=True, gridspec_kw={"height_ratios": [3, 1.3]})
ax[0].plot(t, sp, "k--", lw=1, label="referência")
ax[0].plot(t, pm, color="tab:blue", lw=0.7, alpha=0.8, label="posição medida (sensor simulado)")
ax[0].plot(t, pr, color="tab:orange", lw=1.0, label="posição real do carretel")
ax[0].set_ylabel("posição (cm)"); ax[0].set_ylim(12, 38); ax[0].legend(loc="upper right", fontsize=8, ncol=3)
ax[1].plot(t, u, color="tab:red", lw=0.6); ax[1].set_ylabel("PWM (%)"); ax[1].set_xlabel("tempo simulado (s)")
fig.tight_layout(); fig.savefig("relatorio/figuras/fig_wokwi_v2.png"); plt.close(fig)
print("gravado relatorio/figuras/fig_wokwi_v2.png")
