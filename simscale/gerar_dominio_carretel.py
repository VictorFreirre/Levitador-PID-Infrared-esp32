"""
Gera o volume de ar (dominio de CFD) do tubo com o carretel v1 no meio, em STL ASCII com faces nomeadas:
  inlet (z = 0), outlet (z = L), tubo (parede), carretel (superficie do carretel).
As normais apontam para FORA do volume de ar (no carretel, para dentro do carretel). Unidades: mm.
Carretel v1 (bolinha/carretel.scad): discos de 44,6 mm x 2 mm, vao de 30 mm, eixo de 10 mm (o furo interno do eixo e fechado
e nao entra no escoamento). Chanfro de 0,6 mm da borda ignorado.
Uso: python sim/gerar_dominio_carretel.py saida.stl [z_centro_mm=150] [desloc_lateral_mm=0]
"""
import math
import sys

saida = sys.argv[1] if len(sys.argv) > 1 else "sim/dominio_carretel.stl"
ZC = float(sys.argv[2]) if len(sys.argv) > 2 else 150.0
DX = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0

R_TUBO = 23.0
L = 300.0
R_DISCO = 22.3
R_EIXO = 5.0
E_DISCO = 2.0
VAO = 30.0
N = 360                       # divisoes na circunferencia


def circ(r, z, cx=0.0):
    return [(cx + r * math.cos(2 * math.pi * k / N), r * math.sin(2 * math.pi * k / N), z) for k in range(N)]


def normal(a, b, c):
    u = [b[i] - a[i] for i in range(3)]; v = [c[i] - a[i] for i in range(3)]
    n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
    m = math.sqrt(sum(x * x for x in n)) or 1.0
    return [x / m for x in n]


def parede(r, z0, z1, para_fora, cx=0.0):
    """lateral de cilindro; para_fora=True -> normal radial para fora"""
    a, b = circ(r, z0, cx), circ(r, z1, cx)
    t = []
    for k in range(N):
        k2 = (k + 1) % N
        if para_fora:
            t += [(a[k], a[k2], b[k2]), (a[k], b[k2], b[k])]
        else:
            t += [(a[k], b[k2], a[k2]), (a[k], b[k], b[k2])]
    return t


def disco(r, z, para_cima, cx=0.0):
    c = (cx, 0.0, z); p = circ(r, z, cx); t = []
    for k in range(N):
        k2 = (k + 1) % N
        t.append((c, p[k], p[k2]) if para_cima else (c, p[k2], p[k]))
    return t


def anel(r0, r1, z, para_cima, cx=0.0):
    a, b = circ(r0, z, cx), circ(r1, z, cx); t = []
    for k in range(N):
        k2 = (k + 1) % N
        if para_cima:
            t += [(a[k], b[k], b[k2]), (a[k], b[k2], a[k2])]
        else:
            t += [(a[k], b[k2], b[k]), (a[k], a[k2], b[k2])]
    return t


z0 = ZC - VAO / 2 - E_DISCO          # base do disco de baixo
z1 = ZC - VAO / 2                    # topo do disco de baixo
z2 = ZC + VAO / 2                    # base do disco de cima
z3 = ZC + VAO / 2 + E_DISCO          # topo do disco de cima
regioes = {
    "inlet": disco(R_TUBO, 0.0, para_cima=False),
    "outlet": disco(R_TUBO, L, para_cima=True),
    "tubo": parede(R_TUBO, 0.0, L, para_fora=True),
    # carretel: normais para DENTRO do carretel (fora do ar)
    "carretel": (disco(R_DISCO, z0, True, DX) + parede(R_DISCO, z0, z1, False, DX) + anel(R_EIXO, R_DISCO, z1, False, DX)
                 + parede(R_EIXO, z1, z2, False, DX)
                 + anel(R_EIXO, R_DISCO, z2, True, DX) + parede(R_DISCO, z2, z3, False, DX) + disco(R_DISCO, z3, False, DX)),
}

# conferencia: volume pelo teorema da divergencia (deve dar o volume do tubo menos o do carretel)
vol = 0.0
for tris in regioes.values():
    for a, b, c in tris:
        vol += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6
v_tubo = math.pi * R_TUBO ** 2 * L
v_carr = 2 * math.pi * R_DISCO ** 2 * E_DISCO + math.pi * R_EIXO ** 2 * VAO
print(f"volume do STL {vol:.0f} mm3 | esperado {v_tubo - v_carr:.0f} mm3 (tubo {v_tubo:.0f} - carretel {v_carr:.0f})")

UNICO = True   # um solid so: o SimScale costura num volume e separa as faces pelas quinas (facet-split)
CORPOS = "--corpos" in sys.argv   # dois corpos solidos (tubo macico + carretel), normais para FORA: para subtrair no SimScale
if CORPOS:
    regioes["carretel"] = [(a, c, b) for a, b, c in regioes["carretel"]]   # inverte: normais para fora do carretel
with open(saida, "w") as f:
    grupos = [("dominio", [t for v in regioes.values() for t in v])] if UNICO else list(regioes.items())
    for nome, tris in grupos:
        f.write(f"solid {nome}\n")
        for a, b, c in tris:
            n = normal(a, b, c)
            f.write(f" facet normal {n[0]:.6e} {n[1]:.6e} {n[2]:.6e}\n  outer loop\n")
            for p in (a, b, c):
                f.write(f"   vertex {p[0]:.6f} {p[1]:.6f} {p[2]:.6f}\n")
            f.write("  endloop\n endfacet\n")
        f.write(f"endsolid {nome}\n")
print("gravado", saida, {k: len(v) for k, v in regioes.items()})
