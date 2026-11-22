"""
Figuras da simulacao do escoamento com o DISCO (28,89 g) e da compatibilidade com o blower:
  relatorio/figuras/fig_cfd_forca_velocidade.png  (forca x velocidade, ajuste F = a v^n e equilibrio)
  relatorio/figuras/fig_blower_curva_pq.png        (curva P-Q do blower x perda de pressao no disco)
As versoes antigas usavam um peso desatualizado (0,204 N); aqui o peso e o do disco de 28,89 g (0,283 N), como no texto.
Uso: python sim/figura_cfd_disco.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter

plt.rcParams.update({"font.size": 10, "axes.grid": True, "grid.alpha": 0.3, "savefig.dpi": 150, "figure.dpi": 100})
virg = FuncFormatter(lambda x, _: f"{x:g}".replace(".", ","))
_f = lambda x, n=2: f"{x:.{n}f}".replace(".", ",")

A_F, N_F = 1.417, 1.866                      # ajuste do SimScale (disco)
V_RUN = np.array([0.42, 0.50, 1.00]); F_RUN = np.array([0.281, 0.388, 1.418])   # Runs 6, 5 e 4
PESO = 0.02889 * 9.81                        # 0,283 N
A_TUBO = np.pi * 0.025 ** 2                  # tubo de 50 mm (usado nas contas do disco)
v_eq = (PESO / A_F) ** (1 / N_F)
Q_eq = v_eq * A_TUBO * 1e3; dp_eq = PESO / A_TUBO
print(f"disco: v_eq = {v_eq:.3f} m/s, Q = {Q_eq:.2f} L/s, dp = {dp_eq:.0f} Pa")

# ---- (1) forca x velocidade ----
fig, ax = plt.subplots(figsize=(6.2, 4.2))
vv = np.linspace(0.2, 1.15, 200)
ax.plot(vv, A_F * vv ** N_F, color="crimson", label="Ajuste $F = " + _f(A_F, 3).replace(",", "{,}") + "\\,v^{" + _f(N_F, 3).replace(",", "{,}") + "}$")
ax.plot(V_RUN, F_RUN, "o", color="royalblue", ms=8, label="SimScale (Runs 6, 5 e 4)")
ax.axhline(PESO, color="k", ls="--", lw=1, label=f"Peso do disco ({_f(PESO, 3)} N)")
ax.plot([v_eq], [PESO], "s", color="k", ms=7)
ax.annotate(f"equilíbrio:\n{_f(v_eq)} m/s", (v_eq, PESO), xytext=(v_eq * 1.15, PESO * 0.55), fontsize=9,
            arrowprops=dict(arrowstyle="-", lw=0.8))
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xticks([0.2, 0.3, 0.5, 1.0]); ax.set_yticks([0.1, 0.2, 0.5, 1.0, 2.0])
ax.xaxis.set_major_formatter(virg); ax.yaxis.set_major_formatter(virg)
ax.xaxis.set_minor_formatter(FuncFormatter(lambda x, _: "")); ax.yaxis.set_minor_formatter(FuncFormatter(lambda x, _: ""))
ax.set_xlabel("Velocidade do ar na entrada do tubo (m/s)"); ax.set_ylabel("Força vertical sobre o disco (N)")
ax.legend(fontsize=8, loc="upper left")
fig.tight_layout(); fig.savefig("relatorio/figuras/fig_cfd_forca_velocidade.png"); plt.close(fig)

# ---- (2) curva P-Q do blower x perda no disco ----
# pontos da curva a 12 V lidos do datasheet (vazao em L/s, pressao em Pa)
Q12 = np.array([0, 3.33, 10.0, 13.33, 16.67, 20.0, 21.7]); P12 = np.array([700, 665, 490, 390, 265, 100, 0])
def blower(Q, r):                            # leis dos ventiladores: Q ~ r, p ~ r^2 (r = rotacao relativa ~ tensao/12 V)
    return r ** 2 * np.interp(Q / r, Q12, P12, right=0)
def perda(Q):                                # pressao que o disco precisa para cada vazao
    v = Q / 1e3 / A_TUBO
    return A_F * v ** N_F / A_TUBO
# rotacao que passa pelo ponto de equilibrio
rr = np.linspace(0.2, 1, 4001); r_eq = rr[np.argmin(np.abs(blower(Q_eq, rr) - dp_eq))]
print(f"blower no equilibrio: {100*r_eq:.0f}% da rotacao (~{12*r_eq:.1f} V)")

# carretel (SimScale, tubo de 46 mm): pressao na entrada x vazao, ajuste p = c Q^m pelos 3 pontos
A46 = np.pi * 0.023 ** 2
Qc = np.array([0.2, 0.4, 0.6]) * A46 * 1e3; Pc = np.array([34.88, 113.89, 236.41])
mc, lc = np.polyfit(np.log(Qc), np.log(Pc), 1); cc = np.exp(lc)
perda_c = lambda Q: cc * Q ** mc
Qc_eq = 0.279 * A46 * 1e3; dpc_eq = perda_c(Qc_eq)
rc_eq = rr[np.argmin(np.abs(blower(Qc_eq, rr) - dpc_eq))]
print(f"carretel: Q = {Qc_eq:.2f} L/s, dp = {dpc_eq:.0f} Pa, blower a {100*rc_eq:.0f}% da rotacao")

fig, axs = plt.subplots(1, 2, figsize=(11, 4.2))
QQ = np.linspace(0, 22, 600)
for ax, xmax, ymax, tit in ((axs[0], 22, 760, "(a) Curva completa"), (axs[1], 2.5, 250, "(b) Ampliação na região de equilíbrio")):
    q = np.linspace(0, xmax, 600)
    ax.plot(q, blower(q, 1.0), color="royalblue", label="Blower a 12 V (100%)")
    ax.plot(q, blower(q, 0.6), color="royalblue", ls="--", label="Blower a 7,2 V (60%)")
    ax.plot(q, blower(q, r_eq), color="royalblue", ls="-.", label=f"Blower a {100*r_eq:.0f}% da rotação")
    ax.plot(q, blower(q, rc_eq), color="seagreen", ls="-.", label=f"Blower a {100*rc_eq:.0f}% da rotação")
    ax.plot(q, perda(q), color="crimson", lw=2, label="Pressão necessária: disco (28,89 g)")
    ax.plot(q, perda_c(q), color="darkorange", lw=2, label="Pressão necessária: carretel (10,14 g)")
    ax.plot([Q_eq], [dp_eq], "o", color="k"); ax.plot([Qc_eq], [dpc_eq], "o", color="k")
    ax.set_xlim(0, xmax); ax.set_ylim(0, ymax); ax.set_title(tit, fontsize=10)
    ax.set_xlabel("Vazão (L/s)"); ax.set_ylabel("Pressão (Pa)")
    ax.xaxis.set_major_formatter(virg)
axs[1].annotate(f"disco: {_f(Q_eq)} L/s, {dp_eq:.0f} Pa\n→ {100*r_eq:.0f}% da rotação", (Q_eq, dp_eq), xytext=(Q_eq + 0.45, dp_eq + 35), fontsize=9,
                arrowprops=dict(arrowstyle="-", lw=0.8))
axs[1].annotate(f"carretel: {_f(Qc_eq)} L/s, {dpc_eq:.0f} Pa\n→ {100*rc_eq:.0f}% da rotação", (Qc_eq, dpc_eq), xytext=(Qc_eq + 0.75, dpc_eq - 45), fontsize=9,
                arrowprops=dict(arrowstyle="-", lw=0.8))
axs[0].legend(fontsize=8, loc="upper right")
fig.tight_layout(); fig.savefig("relatorio/figuras/fig_blower_curva_pq.png"); plt.close(fig)
print("gravados fig_cfd_forca_velocidade.png e fig_blower_curva_pq.png")
