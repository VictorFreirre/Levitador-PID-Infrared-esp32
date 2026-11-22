"""
Grava a serial do levitador num CSV (o Serial Monitor da Arduino IDE precisa estar FECHADO).

Uso:
  python gravar_serial.py COM4 60 dados/teste1.csv            -> so grava 60 s
  python gravar_serial.py COM4 60 dados/teste1.csv "kd 0.03"  -> manda comandos no inicio e grava

Liga "csv 1" no inicio (linhas com tempo) e "csv 0" no fim. Nao reseta a placa (DTR/RTS desligados).
"""
import os
import sys
import time

import serial

porta = sys.argv[1] if len(sys.argv) > 1 else "COM4"
duracao = float(sys.argv[2]) if len(sys.argv) > 2 else 60
saida = sys.argv[3] if len(sys.argv) > 3 else "dados/teste.csv"
comandos = sys.argv[4:]

os.makedirs(os.path.dirname(saida) or ".", exist_ok=True)

s = serial.Serial()
s.port = porta
s.baudrate = 115200
s.timeout = 0.2
s.dtr = False          # nao resetar o ESP32-C3 ao abrir a porta
s.rts = False
s.open()
time.sleep(0.3)
s.reset_input_buffer()

def enviar(cmd):
    s.write((cmd + "\n").encode())
    print(f">> {cmd}")
    time.sleep(0.15)

for c in comandos:
    enviar(c)
enviar("csv 1")

linhas = 0
t0 = time.time()
with open(saida, "w", encoding="utf-8") as f:
    f.write("t_ms,sp_cm,alt_cm,pwm_pct\n")
    while time.time() - t0 < duracao:
        ln = s.readline().decode(errors="ignore").strip()
        if not ln:
            continue
        if ln.startswith("#"):
            print(ln)                      # mensagens do programa (cortes, erros...)
            continue
        partes = ln.split(",")
        if len(partes) == 4 and partes[0].isdigit():
            f.write(ln + "\n")
            linhas += 1

enviar("csv 0")
s.close()
print(f"Gravadas {linhas} linhas em {saida} ({duracao:.0f} s)")
