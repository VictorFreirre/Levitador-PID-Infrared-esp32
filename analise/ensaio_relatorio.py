"""
Ensaios do relatorio final (20/11/2026), carretel v1 + papel, firmware levitador_uso_ble (modo 7):
  (a) degrau classico de PWM em malha aberta a partir de um PWM baixo (blower girando, carretel parado no fundo);
  (d) malha fechada em 30% e 70% da faixa 2-46 cm (= 15 e 33 cm): partidas do repouso e trocas entre os dois.
Uso: python sim/ensaio_relatorio.py COM4 dados/uso21_relatorio.csv [udeg_baixo=38] [udeg_alto=45]
CSV: t_ms,setpoint,posicao,pwm,fase   (fase = rotulo do trecho do roteiro)
No fim (ou em erro/Ctrl+C): setpoint 0 (blower desligado).
"""
import sys
import time

import serial

porta = sys.argv[1] if len(sys.argv) > 1 else "COM4"
saida = sys.argv[2] if len(sys.argv) > 2 else "dados/uso21_relatorio.csv"
UB = float(sys.argv[3]) if len(sys.argv) > 3 else 38.0
UA = float(sys.argv[4]) if len(sys.argv) > 4 else 45.0
SP30, SP70 = 15, 33

# (rotulo, [comandos], segundos)
roteiro = []
for k in range(3):                                   # (a) degrau classico
    roteiro += [(f"a_repouso{k}", ["0"], 8),
                (f"a_degrau{k}", [f"degrau {UB:g} {UA:g} 5 5"], 11)]
for sp in (SP30, SP30, SP70, SP70):                 # (d) partidas do repouso
    roteiro += [("d_repouso", ["0"], 10), (f"d_partida{sp}", [str(sp)], 50)]
for k in range(3):                                   # (d) trocas no ar
    roteiro += [(f"d_troca{SP30}", [str(SP30)], 40), (f"d_troca{SP70}", [str(SP70)], 40)]

s = serial.Serial()
s.port, s.baudrate, s.timeout = porta, 115200, 0.2
s.dtr = False
s.rts = False
s.open()
time.sleep(0.3)
s.reset_input_buffer()


def enviar(c):
    s.write((c + "\n").encode())
    print(f">> {c}", flush=True)
    time.sleep(0.1)


with open(saida, "w", encoding="utf-8") as f:
    f.write("t_ms,setpoint,posicao,pwm,fase\n")
    try:
        enviar("modo 7")
        enviar("csv 1")
        for fase, cmds, dur in roteiro:
            for c in cmds:
                enviar(c)
            t_fim = time.time() + dur
            while time.time() < t_fim:
                linha = s.readline().decode(errors="ignore").strip()
                if not linha:
                    continue
                if linha.startswith("#"):
                    if any(k in linha for k in ("CORTE", "ERRO", "DEGRAU", "fim do degrau")):
                        print(linha, flush=True)
                    continue
                if linha[0].isdigit() and linha.count(",") == 3:
                    f.write(f"{linha},{fase}\n")
    finally:
        enviar("0")
        enviar("csv 0")
        time.sleep(0.5)
        s.close()
        print("blower desligado (setpoint 0)", flush=True)
