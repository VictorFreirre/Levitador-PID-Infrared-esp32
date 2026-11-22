"""
Sobressinal das respostas em malha fechada com tres definicoes (20/11/2026):
  A) 1o pico: maximo entre a 1a chegada ao setpoint e o 1o retorno abaixo dele (definicao usada antes; o ruido pode
     encerrar a busca cedo demais);
  B) maior passagem nos 10 s apos a 1a chegada (posicao bruta);
  C) igual a B, com a posicao suavizada por media movel de 1 s (separa o pico da flutuacao rapida de regime).
Erro de regime: media dos ultimos 15 s do trecho.
Uso: python sim/sobressinal.py arquivo.csv [arquivo2.csv ...]   (colunas t_ms,setpoint,posicao,pwm[,...])
"""
import sys

import numpy as np

SPAN = 44.0
TS = 0.0308


def trechos(arq):
    rows = []
    with open(arq, encoding="utf-8", errors="ignore") as f:
        for ln in f:
            p = ln.strip().split(",")
            try:
                rows.append([float(x) for x in p[:4]])
            except ValueError:
                continue
    d = np.array(rows)
    t = (d[:, 0] - d[0, 0]) / 1000
    if t[-1] > 1e5:          # SerialPlot grava o tempo em ms da placa
        t = t / 1.0
    sp, y = d[:, 1], d[:, 2]
    ch = list(np.where(np.diff(sp) != 0)[0] + 1) + [len(t)]
    for k in range(len(ch) - 1):
        a, b = ch[k], ch[k + 1]
        s0, s1 = sp[a - 1], sp[a]
        if s1 <= 0 or (b - a) * TS < 20:
            continue
        yield s0, s1, t[a:b] - t[a], y[a:b]


def metricas(s0, s1, tt, yy):
    sg = np.sign(s1 - s0); passo = abs(s1 - s0)
    n = max(1, int(round(1.0 / TS)))
    ys = np.convolve(yy, np.ones(n) / n, mode="same")
    res = {}
    cr = np.where(sg * (yy - s1) >= 0)[0]
    if len(cr):
        c0 = cr[0]
        vol = np.where((np.arange(len(yy)) > c0) & (sg * (yy - s1) < 0))[0]
        c1 = min(vol[0] if len(vol) else len(yy), c0 + int(10 / TS))
        res["A"] = max(0.0, (sg * (yy[c0:c1 + 1] - s1)).max())
        w = (tt >= tt[c0]) & (tt <= tt[c0] + 10)
        res["B"] = max(0.0, (sg * (yy[w] - s1)).max())
    else:
        res["A"] = res["B"] = 0.0
    crs = np.where(sg * (ys - s1) >= 0)[0]
    crs = crs[(crs > n) & (crs < len(ys) - n)]
    if len(crs):
        w = (tt >= tt[crs[0]]) & (tt <= tt[crs[0]] + 10) & (np.arange(len(ys)) < len(ys) - n)
        res["C"] = max(0.0, (sg * (ys[w] - s1)).max())
    else:
        res["C"] = 0.0
    reg = tt > tt[-1] - 15
    err = yy[reg].mean() - s1
    return passo, res, err, yy[reg].std()


for arq in sys.argv[1:]:
    print(f"== {arq}")
    for s0, s1, tt, yy in trechos(arq):
        passo, r, err, dp = metricas(s0, s1, tt, yy)
        pc = {k: 100 * v / passo for k, v in r.items()}
        print(f"  {s0:4.0f} -> {s1:4.0f} | A {r['A']:.2f} cm ({pc['A']:4.1f}%) | B {r['B']:.2f} cm ({pc['B']:4.1f}%) | "
              f"C (1 s) {r['C']:.2f} cm ({pc['C']:4.1f}%) | erro {err:+.2f} cm = {100*err/SPAN:+.2f}% faixa | dp {dp:.2f}")
