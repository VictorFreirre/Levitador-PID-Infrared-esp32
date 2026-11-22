"""
Figuras e numeros do relatorio final (20/11/2026). Gera tudo em relatorio/figuras/ e imprime as metricas.
Usa: dados/uso21_id_degraus075.csv (identificacao), dados/uso21_relatorio.csv (degrau classico + malha fechada),
     dados/uso17_modos.csv (camadas do controle), dados/uso9_base_sem_papel.csv e uso9_papel_ganho3_ueqi.csv (papel).
Uso: python sim/figuras_relatorio.py
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import locale
for _loc in ("pt_BR.UTF-8", "pt_BR", "Portuguese_Brazil.1252", "Portuguese_Brazil"):
    try:
        locale.setlocale(locale.LC_NUMERIC, _loc); break
    except locale.Error:
        pass
plt.rcParams["axes.formatter.use_locale"] = True
_f = lambda x, n=2: f"{x:.{n}f}".replace(".", ",")   # numero com virgula nas legendas

OUT = "relatorio/figuras"
os.makedirs(OUT, exist_ok=True)
plt.rcParams.update({"font.size": 10, "axes.grid": True, "grid.alpha": 0.3, "savefig.dpi": 150, "figure.dpi": 100})
FAIXA = (2.0, 46.0)                       # faixa dinamica do setpoint (cm)
SPAN = FAIXA[1] - FAIXA[0]

# modelo identificado (sim/identificar_degraus.py, modelo A, degraus de +-0,75 %)
K_ID, TH_ID, TAU_ID = 10.03, 0.48, 1.50   # cm/s/%, s, s


def ler(arq, ncol):
    rows = []
    with open(arq, encoding="utf-8") as f:
        next(f)
        for ln in f:
            p = ln.strip().split(",")
            if len(p) == ncol and p[0].isdigit():
                rows.append(p)
    return rows


# =====================================================================================================================
# (a) degrau classico em malha aberta
# =====================================================================================================================
R = ler("dados/uso21_relatorio.csv", 5)
t = np.array([float(r[0]) for r in R]) / 1000
sp = np.array([float(r[1]) for r in R]); y = np.array([float(r[2]) if r[2] != "nan" else np.nan for r in R])
u = np.array([float(r[3]) for r in R]); fase = np.array([r[4] for r in R])
dt_all = np.diff(t)
ts_ok = dt_all[dt_all < 0.1]
print(f"(a) Ts medio {ts_ok.mean()*1000:.1f} ms, desvio {ts_ok.std()*1000:.2f} ms, min {ts_ok.min()*1000:.0f}, max {ts_ok.max()*1000:.0f} ms "
      f"(n = {len(ts_ok)})")

fig, axs = plt.subplots(1, 3, figsize=(13, 3.8), sharey=True)
for k in range(3):
    m = fase == f"a_degrau{k}"
    tk, yk, uk = t[m], y[m], u[m]
    i0 = np.where(np.diff(uk) > 1)[0]
    if not len(i0):
        print(f"(a) degrau {k}: sem troca de PWM"); continue
    i0 = i0[0] + 1
    t0 = tk[i0] - 0.015
    tt = tk - t0
    ax = axs[k]
    ax.plot(tt, yk, ".-", ms=2.5, lw=0.8, color="tab:blue", label="posição medida")
    ax.set_xlim(-2, 5.5); ax.set_xlabel("tempo após o degrau (s)")
    ax2 = ax.twinx(); ax2.step(tt, uk, where="post", color="tab:red", lw=1.2, label="PWM"); ax2.set_ylim(30, 50)
    if k == 2: ax2.set_ylabel("PWM (%)", color="tab:red")
    # inicio do movimento (sai 0,5 cm do repouso) e fim da transicao (velocidade >= 90 % da maxima antes do topo/fim)
    y0 = np.nanmean(yk[(tt > -1.5) & (tt < 0)])
    mv = np.where((tt > 0) & (yk > y0 + 0.5))[0]
    mm = (tt > 0) & (tt < 5)
    vel = np.gradient(np.convolve(np.nan_to_num(yk), np.ones(7) / 7, mode="same"), tk)
    txt = f"degrau {k+1}: {uk[i0-1]:.0f} → {uk[i0]:.0f} %"
    if len(mv):
        t_mov = tt[mv[0]]
        sub = np.where(mm & (tt > t_mov))[0]
        vmax = np.nanmax(vel[sub]) if len(sub) else np.nan
        j90 = sub[np.where(vel[sub] >= 0.9 * vmax)[0][0]] if len(sub) else None
        t90 = tt[j90] if j90 is not None else np.nan
        npts = int(np.sum((tt >= 0) & (tt <= t90)))
        print(f"(a) degrau {k+1}: {uk[i0-1]:.1f} -> {uk[i0]:.1f} %, repouso {y0:.1f} cm, comeca a subir em {t_mov:.2f} s, "
              f"velocidade chega a 90% da maxima ({vmax:.1f} cm/s) em {t90:.2f} s -> {npts} pontos na transicao; max {np.nanmax(yk[mm]):.1f} cm")
        ax.axvspan(0, t90, color="gold", alpha=0.25, label=f"transição: {npts} pontos")
    ax.set_title(txt, fontsize=10)
    if k == 0: ax.set_ylabel("posição do carretel (cm)")
    ax.legend(loc="upper left", fontsize=8)
fig.tight_layout(); fig.savefig(f"{OUT}/fig_ma_degrau.png"); plt.close(fig)

# =====================================================================================================================
# (b) identificacao: media normalizada dos degraus em voo + modelo
# =====================================================================================================================
TMAX = 2.5
TG = np.arange(-0.3, TMAX + 0.01, 0.03)
d = np.genfromtxt("dados/uso21_id_degraus075.csv", delimiter=",", skip_header=1)
d = d[~np.isnan(d).any(axis=1)]
ti, spi, yi, ui = d[:, 0] / 1000, d[:, 1], d[:, 2], d[:, 3]
Rn, Dn = [], []
i = 1
while i < len(ti):
    if spi[i] == 0 and spi[i - 1] > 0 and ui[i] > 20:
        j = i
        while j + 1 < len(ti) and spi[j + 1] == 0:
            j += 1
        k = np.where(np.abs(ui[i:j + 1] - ui[i]) > 0.2)[0]
        if len(k):
            k0 = i + k[0]; dd = ui[k0] - ui[i]; t0 = ti[k0] - 0.015; tt = ti - t0
            m = (tt > -0.5) & (tt < TMAX + 0.05)
            if tt[m].max() >= TMAX - 0.1 and yi[m].max() < 47 and yi[m].min() > 1.5:
                yy = np.interp(TG, tt[m], yi[m]); y0 = yy[(TG > -0.25) & (TG <= 0)].mean()
                Rn.append((yy - y0) / dd); Dn.append(dd)
        i = j + 1
    else:
        i += 1
Rn, Dn = np.array(Rn), np.array(Dn)
med = 0.5 * (Rn[Dn > 0].mean(0) + Rn[Dn < 0].mean(0))


def sim_degrau(K, th, tau, tg):
    dtq = 0.002; n = int((tg[-1] + 0.5) / dtq); x = 0.0; yv = 0.0; out = np.zeros(n)
    for q in range(n):
        inp = 1.0 if q * dtq >= th else 0.0
        x += dtq / tau * (inp - x); yv += dtq * K * x; out[q] = yv
    return np.interp(tg, np.arange(n) * dtq, out)


ymod = sim_degrau(K_ID, TH_ID, TAU_ID, TG)
w = TG >= 0
rms = np.sqrt(np.mean((ymod[w] - med[w]) ** 2))
print(f"(b) {len(Dn)} degraus ({np.sum(Dn>0)} subindo, {np.sum(Dn<0)} descendo), media {np.mean(np.abs(Dn)):.2f} %; "
      f"modelo K {K_ID} theta {TH_ID} tau {TAU_ID}: erro rms {rms:.3f} cm/% (resposta final {med[-1]:.2f} cm/%)")
fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
for r in Rn:
    ax[0].plot(TG, r, color="silver", lw=0.6)
ax[0].plot([], [], color="silver", label="degraus individuais")
ax[0].plot(TG, Rn[Dn > 0].mean(0), "r-", lw=1, label="média dos degraus para cima")
ax[0].plot(TG, Rn[Dn < 0].mean(0), "b-", lw=1, label="média dos degraus para baixo")
ax[0].plot(TG, med, "k-", lw=2.2, label=f"média (n = {len(Dn)})")
ax[0].plot(TG, ymod, "g--", lw=2, label=f"modelo: K = {_f(K_ID,1)} cm/(s·%), θ = {_f(TH_ID)} s, τ = {_f(TAU_ID)} s")
ax[0].axvline(0, color="k", lw=0.5); ax[0].set_xlabel("tempo após o degrau de PWM (s)")
ax[0].set_ylabel("deslocamento por % de PWM (cm/%)"); ax[0].set_ylim(-2, 16); ax[0].legend(fontsize=8)
ax[0].set_title("(a) posição")
vm = np.gradient(np.convolve(med, np.ones(5) / 5, mode="same"), TG)
ax[1].plot(TG[:-3], vm[:-3], "k-", lw=2, label="média medida")
ax[1].plot(TG, np.gradient(ymod, TG), "g--", lw=2, label="modelo")
ax[1].axvline(0, color="k", lw=0.5); ax[1].set_xlabel("tempo após o degrau de PWM (s)")
ax[1].set_ylabel("velocidade por % de PWM (cm/s/%)"); ax[1].legend(fontsize=8); ax[1].set_title("(b) velocidade")
fig.tight_layout(); fig.savefig(f"{OUT}/fig_identificacao.png"); plt.close(fig)

# =====================================================================================================================
# (c) simulacao do controlador do firmware contra o modelo identificado
# =====================================================================================================================
TS = 0.0308


def simular_troca(h0, h1, dur=30.0, K=K_ID, th=TH_ID, tau=TAU_ID):
    """Lei de controle do firmware (modo 7) em altura (mm, para cima +). Planta: K e^-th s /(s (tau s + 1)), K em cm/s/%."""
    Kp, Ki, Kd = 0.09, 0.006, 0.09
    smK, smTau, smTh = 2.2, 0.43, 0.60
    ffK, ffTau, acel, vmax = 3.0, 0.45, 10.0, 20.0
    ulim, imax, banda, a_av, tf_av = 9.0, 15.0, 100.0, 0.4, 0.6
    n = int(dur / TS); h = h0 * 10; v = 0.0; ueq = 42.0
    href, vref = h, 0.0
    Nth = int(round(th / TS)); ubuf = [ueq] * (Nth + 1)
    Nsm = int(round(smTh / TS)); smY = smV = smUpd = 0.0; bY = [0.0] * (Nsm + 1); bV = [0.0] * (Nsm + 1)
    rbuf = [href] * (Nsm + 2)
    integ = 0.0; iant = 0.0; aguarda = True; sinal0 = 0
    avX = ueq
    hs, us = [], []
    for k in range(n):
        alvo = h1 * 10
        dif = alvo - href
        vdes = np.sign(dif) * min(vmax, np.sqrt(2 * acel * abs(dif)))
        dv = np.clip(vdes - vref, -acel * TS, acel * TS); aref = dv / TS; vref += dv; href += vref * TS
        if abs(alvo - href) < 0.5 and abs(vref) < 3: href, vref, aref = alvo, 0.0, 0.0
        rbuf.append(href); rbuf.pop(0)
        # Smith (modelo interno do firmware)
        smV += TS / smTau * (10 * smK * smUpd - smV); smY += TS * smV
        bY.append(smY); bV.append(smV); dh = smY - bY.pop(0); dvel = smV - bV.pop(0)
        eP = href - (h + dh)
        P = Kp * eP; D = Kd * (vref - (v + dvel)); uT = (vref + ffTau * aref) / (10 * ffK)
        smUpd = P + D + uT
        if aguarda:
            s = 1 if (h + dh) - alvo > 0 else -1
            if sinal0 == 0: sinal0 = s
            elif s != sinal0: integ = iant; aguarda = False
        ub = ueq + P + integ + D + uT
        uo = float(np.clip(ub, ueq - ulim, ueq + ulim))
        avX += TS / (a_av * tf_av) * (uo - avX); uo2 = float(np.clip(uo / a_av - (1 / a_av - 1) * avX, 0, 100))
        e_i = rbuf[0] - h
        sat = (ub > ueq + ulim and e_i > 0) or (ub < ueq - ulim and e_i < 0)
        if abs(e_i) < banda and not sat: integ += Ki * e_i * TS
        integ = float(np.clip(integ, -imax, imax))
        ubuf.append(uo2); ud = ubuf.pop(0)
        # planta
        v += TS / tau * (10 * K * (ud - ueq) - v); h += TS * v
        hs.append(h / 10); us.append(uo2)
    return np.arange(n) * TS, np.array(hs), np.array(us)


# =====================================================================================================================
# (d) malha fechada: partidas do repouso e trocas 15 <-> 33
# =====================================================================================================================
def metricas(tt, yy, sp0, sp1, nome):
    passo = sp1 - sp0; sgn = np.sign(passo)
    reg = tt > tt[-1] - 15
    erro = np.nanmean(yy[reg]) - sp1
    cruz = np.where(sgn * (yy - sp1) >= 0)[0]
    if len(cruz):
        c0 = cruz[0]
        # 1o pico: maximo (no sentido do degrau) ate o carretel voltar a cruzar o sp ou 10 s
        vol = np.where((np.arange(len(yy)) > c0) & (sgn * (yy - sp1) < 0))[0]
        c1 = vol[0] if len(vol) else len(yy)
        c1 = min(c1, c0 + int(10 / TS))
        pico = max(0.0, np.nanmax(sgn * (yy[c0:c1 + 1] - sp1)))
        t_cruza = tt[c0]
    else:
        pico, t_cruza = 0.0, np.nan
    # acomodacao: ultima vez fora de +-2 % da faixa (0,88 cm)
    fora = np.where(np.abs(yy - sp1) > 0.02 * SPAN)[0]
    fora = fora[tt[fora] < tt[-1] - 15]
    t_acom = tt[fora[-1]] if len(fora) else 0.0
    # subida 10-90 %
    a10 = np.where(sgn * (yy - (sp0 + 0.1 * passo)) >= 0)[0]; a90 = np.where(sgn * (yy - (sp0 + 0.9 * passo)) >= 0)[0]
    t_sub = (tt[a90[0]] - tt[a10[0]]) if len(a10) and len(a90) else np.nan
    dp = np.nanstd(yy[reg])
    res = dict(nome=nome, sp0=sp0, sp1=sp1, pico=pico, pico_degrau=100 * pico / abs(passo), pico_sp=100 * pico / sp1,
               erro=erro, erro_faixa=100 * erro / SPAN, erro_sp=100 * erro / sp1, t_sub=t_sub, t_acom=t_acom, dp=dp,
               t_cruza=t_cruza)
    print(f"(d) {nome:22s} {sp0:4.0f}->{sp1:4.0f}: 1o pico {pico:4.2f} cm = {res['pico_degrau']:4.1f}% do degrau ({res['pico_sp']:4.1f}% do sp) | "
          f"erro {erro:+.2f} cm = {res['erro_faixa']:+.2f}% da faixa ({res['erro_sp']:+.2f}% do sp) | subida 10-90 {t_sub:4.1f} s | "
          f"acomod. +-2% {t_acom:4.1f} s | dp regime {dp:.2f} cm")
    return res


tab = []
fig, axs = plt.subplots(1, 2, figsize=(12, 4.2), sharey=True)
for j, spv in enumerate((15, 33)):
    ax = axs[j]; n_ok = 0
    idx = np.where(fase == f"d_partida{spv}")[0]
    blocos = np.split(idx, np.where(np.diff(idx) > 1)[0] + 1)
    for b in blocos:
        tt = t[b] - t[b][0]; yy = y[b]
        ax.plot(tt, yy, lw=1.2, label=f"partida {n_ok+1}")
        tab.append(metricas(tt, yy, 0.0, spv, f"partida do repouso {n_ok+1}"))
        n_ok += 1
    ax.axhline(spv, color="k", ls="--", lw=1, label=f"setpoint {spv} cm")
    ax.axhspan(spv - 0.02 * SPAN, spv + 0.02 * SPAN, color="green", alpha=0.12, label="±2 % da faixa")
    ax.set_xlabel("tempo após o comando (s)"); ax.set_title(f"partida do repouso para {spv} cm ({100*(spv-FAIXA[0])/SPAN:.0f} % da faixa)")
    ax.legend(fontsize=8, loc="lower right")
axs[0].set_ylabel("posição do carretel (cm)")
fig.tight_layout(); fig.savefig(f"{OUT}/fig_mf_partidas.png"); plt.close(fig)

m = np.array([f.startswith("d_troca") for f in fase])
idx = np.where(m)[0]
fig, ax = plt.subplots(2, 1, figsize=(12, 5.5), sharex=True, gridspec_kw={"height_ratios": [3, 1.2]})
tt0 = t[idx[0]]
ax[0].plot(t[idx] - tt0, sp[idx], "k--", lw=1, label="referência")
ax[0].plot(t[idx] - tt0, y[idx], lw=1.1, label="posição medida")
ax[0].set_ylabel("posição (cm)"); ax[0].legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2, fontsize=8, frameon=False)
ax[1].plot(t[idx] - tt0, u[idx], color="tab:red", lw=0.6); ax[1].set_ylabel("PWM (%)"); ax[1].set_xlabel("tempo (s)")
fig.tight_layout(); fig.savefig(f"{OUT}/fig_mf_trocas.png"); plt.close(fig)
# metricas de cada troca (o 1o bloco parte de 33 do fim das partidas)
blocos = []
cur = [idx[0]]
for q in idx[1:]:
    if fase[q] == fase[cur[-1]] and q == cur[-1] + 1: cur.append(q)
    else: blocos.append(cur); cur = [q]
blocos.append(cur)
trocas_med = {15: [], 33: []}
for bi, b in enumerate(blocos):
    b = np.array(b); spv = int(sp[b][-1]); ant = sp[b[0] - 1] if b[0] > 0 else 0
    if ant <= 0 or ant == spv:
        continue
    tt = t[b] - t[b][0]
    tab.append(metricas(tt, y[b], ant, spv, f"troca {ant:.0f}->{spv}"))
    trocas_med[spv].append((tt, y[b]))

# simulacao x medida: modelo identificado (K = 10) e K 20 % menor (8)
K_ALT = 8.0
fig, ax = plt.subplots(1, 2, figsize=(12, 4.0), sharey=False)
for j, (a, b) in enumerate(((15, 33), (33, 15))):
    for (tt, yy) in trocas_med[b]:
        ax[j].plot(tt, yy, color="tab:blue", lw=0.8, alpha=0.6)
    ts_, hs_, _ = simular_troca(a, b, 40, K=K_ID)
    ts8, hs8, _ = simular_troca(a, b, 40, K=K_ALT)
    ax[j].plot(ts_, hs_, color="tab:red", ls="--", lw=1.2, alpha=0.8, label=f"simulado, K = {K_ID:.0f} cm/(s·%) (identificado)")
    ax[j].plot(ts8, hs8, "g--", lw=2, label=f"simulado, K = {K_ALT:.0f} cm/(s·%)")
    ax[j].plot([], [], color="tab:blue", lw=0.8, label="medido (cada troca)")
    ax[j].axhline(b, color="k", ls=":", lw=1); ax[j].set_title(f"troca {a} → {b} cm"); ax[j].set_xlabel("tempo (s)")
    ax[j].set_xlim(0, 40)
    metricas(ts_, hs_, a, b, f"SIM K{K_ID:.0f} {a}->{b}"); metricas(ts8, hs8, a, b, f"SIM K{K_ALT:.0f} {a}->{b}")
ax[0].set_ylabel("posição (cm)"); ax[0].legend(fontsize=8, loc="lower right")
fig.tight_layout(); fig.savefig(f"{OUT}/fig_projeto_sim.png"); plt.close(fig)

with open(f"{OUT}/metricas_mf.csv", "w", encoding="utf-8") as f:
    f.write("ensaio,sp0,sp1,pico_cm,pico_pct_degrau,pico_pct_sp,erro_cm,erro_pct_faixa,erro_pct_sp,t_subida,t_acomod,dp_regime\n")
    for r in tab:
        f.write(f"{r['nome']},{r['sp0']:.0f},{r['sp1']:.0f},{r['pico']:.2f},{r['pico_degrau']:.1f},{r['pico_sp']:.1f},{r['erro']:.2f},"
                f"{r['erro_faixa']:.2f},{r['erro_sp']:.2f},{r['t_sub']:.1f},{r['t_acom']:.1f},{r['dp']:.2f}\n")

# =====================================================================================================================
# camadas do controle (uso17) e efeito do papel (uso9)
# =====================================================================================================================
M = ler("dados/uso17_modos.csv", 5)
tm = (np.array([float(r[0]) for r in M]) - float(M[0][0])) / 1000
spm = np.array([float(r[1]) for r in M]); ym = np.array([float(r[2]) for r in M]); mm_ = np.array([int(r[4]) for r in M])
nomes = {1: "P", 2: "PI", 3: "PID", 4: "PID + Smith", 5: "PID + Smith + Overdrive", 6: "Completo"}
cores = {1: "#ef5350", 2: "#ffa726", 3: "#ab47bc", 4: "#66bb6a", 5: "#29b6f6", 6: "#9e9e9e"}   # vermelho, laranja, roxo, verde, azul, cinza
# um painel por modo, na ordem P -> Completo. Os trechos sao os reais do ensaio (o ensaio rodou em outra ordem: P e PI,
# instaveis, ficaram por ultimo). Nos modos com troca 22 -> 36 -> 22 cm, o painel comeca 50 s antes da subida.
JAN = 130.0
def trecho(modo, ocorrencia=0):
    segs = []; ini = 0
    for q in range(1, len(tm) + 1):
        if q == len(tm) or mm_[q] != mm_[ini]:
            if mm_[ini] == modo: segs.append((ini, q))
            ini = q
    a, b = segs[ocorrencia]
    sub = np.where(np.diff(spm[a:b]) > 0)[0]
    t0 = tm[a + sub[0] + 1] - 50 if len(sub) and spm[a + sub[0] + 1] > 30 else tm[a]
    if len(sub) and spm[a + sub[0] + 1] <= 30 and len(sub) > 1:      # completo: a 1a "subida" e a decolagem; usa a troca para 36
        k = [s for s in sub if spm[a + s + 1] > 30][0]; t0 = tm[a + k + 1] - 50
    sel = (tm >= t0) & (tm <= min(t0 + JAN, tm[b - 1]))
    return tm[sel] - t0, spm[sel], ym[sel]

fig, axs = plt.subplots(2, 3, figsize=(12, 6.2), sharex=True, sharey=True)
for ax, modo in zip(axs.flat, (1, 2, 3, 4, 5, 6)):
    tt, rr, yy = trecho(modo)
    ax.set_facecolor(cores[modo] + "33")
    for s in ("left", "right", "top", "bottom"):
        ax.spines[s].set_color(cores[modo]); ax.spines[s].set_linewidth(2)
    ax.plot(tt, rr, "k--", lw=1.1, label="referência")
    ax.plot(tt, yy, color="#0d1b4c", lw=0.9, label="posição")
    dp = np.std((yy - rr)[(tt > 5) & (np.abs(np.gradient(rr)) == 0)])
    ax.set_title(f"{list(nomes).index(modo) + 1}. {nomes[modo]}", fontsize=10, color="black", loc="left",
                 bbox=dict(facecolor=cores[modo], alpha=0.6, edgecolor="none", pad=2))
    ax.set_xlim(0, JAN); ax.set_ylim(0, 50)
for ax in axs[:, 0]: ax.set_ylabel("posição (cm)")
for ax in axs[1, :]: ax.set_xlabel("tempo (s)")
axs[0, 0].legend(fontsize=8, loc="lower right")
fig.tight_layout(); fig.savefig(f"{OUT}/fig_modos.png"); plt.close(fig)

# fig_papel.png agora e gerada por sim/figura_papel.py (posicao em cm com a linha da referencia)
print("figuras em", OUT)
