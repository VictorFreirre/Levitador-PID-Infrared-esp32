"""
Figura da comparacao sem e com o papel furado (11/11/2026): posicao do carretel em regime com a referencia em 22 cm.
Dados: dados/uso9_base_sem_papel.csv e dados/uso9_papel_ganho3_ueqi.csv (t_ms, sp_cm, alt_cm, pwm_pct).
Gera relatorio/figuras/fig_papel.png.
Uso: python sim/figura_papel.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({"font.size": 10, "axes.grid": True, "grid.alpha": 0.3, "savefig.dpi": 150, "figure.dpi": 100})
_f = lambda x, n=2: f"{x:.{n}f}".replace(".", ",")

fig, axs = plt.subplots(2, 1, figsize=(12, 5.2), sharex=True, sharey=True)
for ax, (arq, nome, cor) in zip(axs, (("dados/uso9_base_sem_papel.csv", "Sem papel", "tab:red"),
                                      ("dados/uso9_papel_ganho3_ueqi.csv", "Com papel", "tab:blue"))):
    d = np.genfromtxt(arq, delimiter=",", skip_header=1, invalid_raise=False)
    d = d[~np.isnan(d).any(axis=1)]
    t, sp, y = d[:, 0] / 1000, d[:, 1], d[:, 2]
    i22 = np.where(sp > 1)[0]
    i22 = i22[sp[i22] == sp[i22[0]]]                     # primeiro trecho com a referencia em 22 cm
    tq = t[i22] - t[i22[0]]; yq = y[i22]; ref = sp[i22[0]]
    m = (tq > 30) & (tq < 180)                            # regime: descarta a partida
    dp = np.std(yq[m] - ref)
    ax.axhspan(ref - 1, ref + 1, color="green", alpha=0.12, label="±1 cm da referência")
    ax.axhline(ref, color="k", ls="--", lw=1, label=f"referência ({ref:.0f} cm)")
    ax.plot(tq[m] - 30, yq[m], lw=0.9, color=cor, label="posição do carretel")
    ax.set_title(f"{nome}: desvio padrão de {_f(dp)} cm em torno da referência", fontsize=10, loc="left")
    ax.set_ylabel("posição (cm)")
    ax.legend(loc="upper right", fontsize=8, ncol=3)
    print(nome, "desvio", round(dp, 2))
axs[0].set_ylim(11, 37)
axs[1].set_xlabel("tempo (s)")
fig.tight_layout(); fig.savefig("relatorio/figuras/fig_papel.png"); plt.close(fig)
print("gravado relatorio/figuras/fig_papel.png")
