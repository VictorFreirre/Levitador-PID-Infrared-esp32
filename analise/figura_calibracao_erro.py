"""
Erro do VL53L0X antes e depois da calibracao (mesmos 10 pontos da tabela de calibracao do relatorio).
Erro = distancia informada - distancia real (fita metrica). Gera relatorio/figuras/fig_calibracao_erro.png.
Uso: python sim/figura_calibracao_erro.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({"font.size": 10, "axes.grid": True, "grid.alpha": 0.3, "savefig.dpi": 150, "figure.dpi": 100})

real = np.array([50, 100, 150, 200, 250, 300, 350, 400, 450, 500], float)
medida = np.array([69.7, 122.9, 173.3, 227.9, 279.5, 330.1, 377.2, 422.2, 468.3, 508.6])
p3 = [7.867e-7, -3.7e-4, 1.003466, -18.386522]
calibrada = np.polyval(p3, medida)
e_sem, e_com = medida - real, calibrada - real
print("erro max sem: %.1f mm | com: %.1f mm" % (np.max(np.abs(e_sem)), np.max(np.abs(e_com))))

fig, ax = plt.subplots(figsize=(6.6, 4.2))
ax.axhspan(-2, 2, color="green", alpha=0.12, label="±2 mm")
ax.axhline(0, color="k", lw=0.8)
ax.plot(real, e_sem, "o-", color="crimson", label="leitura direta do sensor")
ax.plot(real, e_com, "s-", color="royalblue", label="leitura corrigida pelo polinômio")
ax.annotate("o sensor lê de 9 a 30 mm\na mais que a distância real", (300, e_sem[5]), xytext=(330, 12), fontsize=9,
            arrowprops=dict(arrowstyle="-", lw=0.8))
ax.annotate("depois da calibração:\nno máximo 1,5 mm de erro", (150, e_com[2]), xytext=(60, 8), fontsize=9,
            arrowprops=dict(arrowstyle="-", lw=0.8))
ax.set_xlabel("distância real, medida com a fita métrica (mm)")
ax.set_ylabel("erro = leitura − distância real (mm)")
ax.set_ylim(-5, 40)
ax.legend(fontsize=8, loc="upper center", ncol=3)
fig.tight_layout(); fig.savefig("relatorio/figuras/fig_calibracao_erro.png"); plt.close(fig)
print("gravado relatorio/figuras/fig_calibracao_erro.png")
