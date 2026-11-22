# Codigo para realizar regressao polinomial de terceiro grau

import tkinter as tk
from tkinter import filedialog
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Oculta a janela principal do Tkinter
root = tk.Tk()
root.withdraw()

# Abre a janela do Windows para selecionar o arquivo Excel
print("Aguardando selecao do arquivo...")
caminho_arquivo = filedialog.askopenfilename(
    title="Selecione a planilha de dados do sensor",
    filetypes=[("Planilhas Excel", "*.xlsx *.xls"), ("Todos os arquivos", "*.*")],
)

if caminho_arquivo:
    # 1. Carregar os dados do arquivo escolhido
    df = pd.read_excel(caminho_arquivo)

    # Entrada = Distancia Medida (x) e Saida = Distancia Real (y)
    x_sensor = df["distancia medida (mm)"].values
    y_real = df["distancia real (mm)"].values

    # 2. Calcular a Regressao Polinomial de Grau 3
    p3 = np.polyfit(x_sensor, y_real, 3)
    polinomio = np.poly1d(p3)

    print("\n=== COEFICIENTES POLINOMIO DE GRAU 3 ===")
    print(f"a = {p3[0]:.10f}")
    print(f"b = {p3[1]:.8f}")
    print(f"c = {p3[2]:.6f}")
    print(f"d = {p3[3]:.6f}")

    # 3. Gerar pontos para a curva ajustada
    x_linha = np.linspace(x_sensor.min(), x_sensor.max(), 300)
    y_linha = polinomio(x_linha)

    # 4. Plotar o grafico de dispersao + curva ajustada
    plt.figure(figsize=(8, 6))
    plt.scatter(x_sensor, y_real, color="royalblue", label="Dados medidos", s=25)
    plt.plot(x_linha, y_linha, color="crimson", linewidth=2, label="Ajuste polinomial (grau 3)")

    plt.title("Distancia Medida x Distancia Real")
    plt.xlabel("Distancia Medida (mm)")
    plt.ylabel("Distancia Real (mm)")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.tight_layout()
    plt.show()

else:
    print("Nenhum arquivo foi selecionado.")
