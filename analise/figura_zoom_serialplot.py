"""
Zoom nas amostras do degrau de PWM gravado com o SerialPlot (dados/uso22_degrau_serialplot.csv, 20/11/2026).
Colunas do CSV exportado: tempo (ms), setpoint, posicao (cm), PWM (%).
Gera relatorio/figuras/fig_serialplot_zoom.png: (a) ensaio inteiro, com a regiao ampliada marcada;
(b) a transicao amostra por amostra.
Uso: python sim/figura_zoom_serialplot.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({"font.size": 10, "axes.grid": True, "grid.alpha": 0.3, "savefig.dpi": 150, "figure.dpi": 100})

d = np.genfromtxt("dados/uso22_degrau_serialplot.csv", delimiter=",", skip_header=1)
t = (d[:, 0] - d[0, 0]) / 1000.0
pos, pwm = d[:, 2], d[:, 3]

k_deg = int(np.where((pwm[1:] > 40) & (pwm[:-1] < 40))[0][0]) + 1          # 38 -> 44 %
k_volta = int(np.where((pwm[1:] < 40) & (pwm[:-1] > 40))[0][0]) + 1        # 44 -> 38 %
k_sobe = int(np.where((np.arange(len(pos)) > k_deg) & (pos > 0.5))[0][0])  # carretel comeca a subir
t0 = t[k_deg]
ts = np.diff(t)
print(f"amostragem: {1000*ts.mean():.2f} +- {1000*ts.std():.2f} ms")
print(f"degrau em t = {t0:.2f} s; carretel sobe {t[k_sobe]-t0:.2f} s depois ({k_sobe-k_deg} amostras); PWM volta em {t[k_volta]-t0:.2f} s")

# transicao: do degrau ate o carretel chegar a 90 % da altura maxima alcancada
hmax = pos[k_deg:k_volta + 40].max()
k90 = int(np.where((np.arange(len(pos)) > k_sobe) & (pos >= 0.9 * hmax))[0][0])
print(f"altura maxima {hmax:.1f} cm; 90 % em {t[k90]-t0:.2f} s; pontos do degrau ate 90 %: {k90-k_deg}")

k_topo = int(np.argmax(pos[k_deg:k_volta + 40])) + k_deg                   # carretel no ponto mais alto
_f = lambda x, n=2: f"{x:.{n}f}".replace(".", ",")
fig = plt.figure(figsize=(10, 7.6))
gs = fig.add_gridspec(2, 3, height_ratios=[1, 1.7])
a = fig.add_subplot(gs[0, :]); c = fig.add_subplot(gs[1, 0]); b = fig.add_subplot(gs[1, 1:])

# (a) ensaio completo
a.plot(t - t0, pwm, color="tab:green", lw=1.2, label="PWM (%)")
a.plot(t - t0, pos, color="navy", lw=1.2, label="posição (cm)")
a.axvspan(-0.35, 0.35, color="tab:green", alpha=0.18, label="região de (b)")
a.axvspan(t[k_sobe] - t0 - 0.3, t[k_topo] - t0 + 0.2, color="navy", alpha=0.12, label="região de (c)")
a.set_xlim(t[0] - t0, t[-1] - t0); a.set_ylabel("PWM (%) / pos. (cm)")
a.set_xlabel("tempo em relação ao degrau (s)")
a.set_title("(a) ensaio completo no SerialPlot", fontsize=10, loc="left")
a.legend(loc="upper left", fontsize=8)

def pontos(ax, j, y, cor, rotulo, ms=4.5):
    sel = (t - t0 >= j[0]) & (t - t0 <= j[1])
    ax.plot(t[sel] - t0, y[sel], "-", color=cor, lw=0.5, alpha=0.5)
    ax.plot(t[sel] - t0, y[sel], "o", ms=ms, mfc="white", mec=cor, mew=1.0)
    ax.set_xlim(*j); ax.set_xlabel("tempo depois do degrau (s)"); ax.set_ylabel(rotulo)
    return int(sel.sum())

# (b) degrau de PWM
n1 = pontos(c, (-0.35, 0.35), pwm, "tab:green", "PWM (%)")
c.set_ylim(37, 45)
c.set_title(f"(b) degrau de PWM:\n{n1} amostras em 0,7 s", fontsize=10, loc="left")

# (c) subida inteira do carretel, do fundo ao topo
J = (t[k_sobe] - t0 - 0.3, t[k_topo] - t0 + 0.2)
n2 = pontos(b, J, pos, "navy", "posição (cm)", ms=3.6)
b.set_ylim(-2, 50)
b.set_title(f"(c) subida do carretel, do fundo ao topo: {n2} amostras em {_f(J[1]-J[0], 1)} s", fontsize=10, loc="left")
fig.suptitle(f"Cada ponto em (b) e (c) é uma amostra, uma a cada {1000*ts.mean():.1f} ms. "
             f"Do degrau até 90% da altura: {k90 - k_deg} amostras".replace(".", ",", 1), fontsize=10, y=0.005, va="bottom")
fig.tight_layout(rect=(0, 0.025, 1, 1)); fig.savefig("relatorio/figuras/fig_serialplot_zoom.png"); plt.close(fig)
print("gravado relatorio/figuras/fig_serialplot_zoom.png", n1, n2)
