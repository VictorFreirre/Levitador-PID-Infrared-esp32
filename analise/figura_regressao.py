"""
Grafico da calibracao do VL53L0X: distancia medida pelo sensor x distancia real (fita metrica) e o polinomio de 3o grau.
Mesmos dados da tabela de calibracao do relatorio. Gera relatorio/figuras/regressao.png.
Uso: python sim/figura_regressao.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter

plt.rcParams.update({"font.size": 10, "axes.grid": True, "grid.alpha": 0.3, "savefig.dpi": 150, "figure.dpi": 100})

real = np.array([50, 100, 150, 200, 250, 300, 350, 400, 450, 500], float)
medida = np.array([69.7, 122.9, 173.3, 227.9, 279.5, 330.1, 377.2, 422.2, 468.3, 508.6])
p3 = [7.867e-7, -3.7e-4, 1.003466, -18.386522]           # coeficientes da Equacao de calibracao (usados no firmware)
print("erro maximo do polinomio nos 10 pontos: %.2f mm" % np.max(np.abs(np.polyval(p3, medida) - real)))

x = np.linspace(medida.min(), medida.max(), 300)
fig, ax = plt.subplots(figsize=(6.4, 4.4))
ax.plot([40, 520], [40, 520], color="gray", ls=":", lw=1, label="medida = real (sensor ideal)")
ax.plot(x, np.polyval(p3, x), color="crimson", lw=1.6, label="ajuste polinomial (grau 3)")
ax.plot(medida, real, "o", color="royalblue", ms=6, label="dados medidos")
ax.set_xlim(40, 520); ax.set_ylim(30, 520)
ax.set_xlabel("distância medida pelo sensor (mm)"); ax.set_ylabel("distância real (mm)")
ax.set_title("Distância medida × distância real", fontsize=10)
ax.legend(fontsize=8, loc="upper left")
fig.tight_layout(); fig.savefig("relatorio/figuras/regressao.png"); plt.close(fig)
print("gravado relatorio/figuras/regressao.png")
