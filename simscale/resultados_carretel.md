# SimScale — carretel v1 no tubo (projeto "PID control", rodadas 4–6, 21/11/2026)

Malha 1 (3,5 M células), k-omega SST, regime permanente, 1000 iterações. Média das últimas 200 iterações.

| v entrada (m/s) | Fz total (N) | Fz viscosa (N) | Fz/peso | p média na entrada (Pa) |
|---|---|---|---|---|
| 0,2 | 0,05581 | 0,00025 | 0,56 | 34,88 |
| 0,4 | 0,18324 | 0,00027 | 1,84 | 113,89 |
| 0,6 | 0,38135 | 0,00014 | 3,83 | 236,41 |

Ajuste: F = 0,921·v^1,746 (desvio máx. 1,6 %). Peso 0,0995 N (10,14 g).
Equilíbrio: v = 0,279 m/s, Q = 0,464 L/s (27,9 L/min), Δp = 62 Pa (peso/área do disco = 63,7 Pa).
Figura e ajuste: `python sim/figura_cfd_carretel.py` → relatorio/figuras/fig_cfd_carretel.png.
