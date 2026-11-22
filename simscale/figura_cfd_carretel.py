"""
Figura e ajuste das simulacoes do carretel v1 no SimScale (21/11/2026, projeto "PID control", rodadas 4-6).
Gera relatorio/figuras/fig_cfd_carretel.png e imprime o ajuste F = a v^n e o equilibrio.
Uso: python sim/figura_cfd_carretel.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({"font.size": 10, "axes.grid": True, "grid.alpha": 0.3, "savefig.dpi": 150, "figure.dpi": 100})
_f = lambda x, n=2: f"{x:.{n}f}".replace(".", ",")

# media das ultimas 200 de 1000 iteracoes
V = np.array([0.2, 0.4, 0.6])                 # m/s, velocidade na entrada
F = np.array([0.05581, 0.18324, 0.38135])     # N, Fz total no carretel (pressao + viscosa)
P = np.array([34.88, 113.89, 236.41])         # Pa, pressao media na entrada (saida a 0 Pa)

PESO = 0.01014 * 9.81                         # N
A_TUBO = np.pi * 0.023 ** 2                   # m2 (tubo de 46 mm internos)
A_DISCO = np.pi * 0.0223 ** 2                 # m2 (disco de 44,6 mm)
A_DISCO_ANT, N_DISCO_ANT, PESO_ANT = 1.417, 1.866, 0.02889 * 9.81   # disco de 28,89 g (simulacao anterior)

n, la = np.polyfit(np.log(V), np.log(F), 1); a = np.exp(la)
veq = (PESO / a) ** (1 / n)
m, lb = np.polyfit(np.log(V), np.log(P), 1); peq = np.exp(lb) * veq ** m
print(f"F = {a:.3f} v^{n:.3f}  (desvio maximo {100 * np.max(np.abs(a * V ** n / F - 1)):.1f} %)")
print(f"v_eq = {veq:.3f} m/s | Q = {veq * A_TUBO * 1e3:.3f} L/s = {veq * A_TUBO * 6e4:.1f} L/min")
print(f"dp no equilibrio = {peq:.1f} Pa | peso/area do disco = {PESO / A_DISCO:.1f} Pa")

vv = np.linspace(0.1, 0.7, 200)
fig, ax = plt.subplots(figsize=(6.4, 4.0))
ax.plot(vv, a * vv ** n, color="C0", label=f"Carretel: $F = {_f(a, 3)}\\,v^{{{_f(n, 2)}}}$")
ax.plot(V, F, "o", color="C0", ms=7, label="Carretel: simulações")
ax.axhline(PESO, color="C0", ls=":", lw=1)
ax.plot([veq], [PESO], "*", color="C3", ms=13, label=f"Equilíbrio do carretel: {_f(veq)} m/s")
ax.plot(vv, A_DISCO_ANT * vv ** N_DISCO_ANT, "--", color="0.5", label="Disco de 28,89 g (simulação anterior)")
ax.axhline(PESO_ANT, color="0.5", ls=":", lw=1)
ax.text(0.52, PESO + 0.008, f"peso do carretel ({_f(PESO, 4)} N)", color="C0", fontsize=8)
ax.text(0.105, PESO_ANT + 0.008, f"peso do disco ({_f(PESO_ANT, 3)} N)", color="0.4", fontsize=8)
ax.set_xlabel("Velocidade do ar na entrada (m/s)"); ax.set_ylabel("Força vertical $F_z$ (N)")
ax.set_xlim(0.1, 0.7); ax.set_ylim(0, 0.6)
ax.legend(fontsize=8, loc="upper left")
fig.tight_layout(); fig.savefig("relatorio/figuras/fig_cfd_carretel.png"); plt.close(fig)
print("gravado relatorio/figuras/fig_cfd_carretel.png")
