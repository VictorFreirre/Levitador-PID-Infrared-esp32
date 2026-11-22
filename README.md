# Levitador PID: Infrared + ESP32

Códigos e dados do projeto da disciplina de Instrumentação Eletrônica (TE331, UFPR): um carretel impresso em 3D levita dentro de um tubo de acrílico. A altura é medida por um sensor laser infravermelho de tempo de voo (VL53L0X) e controlada pela rotação de um *blower* Delta BFB1012EH, comandado por PWM a partir de um ESP32-C3.

O controle final combina PID, preditor de Smith, *feedforward* de equilíbrio e de trajetória, *overdrive* e *reset* do integrador. Em malha fechada, nas referências de 15 e 33 cm (30% e 70% da faixa), o erro de regime ficou abaixo de 0,31% da faixa e o sobressinal entre 1,8% e 7,0%.

Autores: Matheus Freitas dos Santos e Victor Lima Freire.

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `firmware/levitador_uso_ble/` | Programa final do ESP32-C3, usado em todos os ensaios (modos 1 a 7, do P ao controle completo). Abrir na Arduino IDE. |
| `simulacao_wokwi/levitador_wokwi_v2/` | Simulação no Wokwi com o carretel, o *blower* identificado na bancada e o mesmo controle do firmware. Para rodar: novo projeto ESP32-C3 em wokwi.com, colar o `.ino` e iniciar; a saída serial é CSV. |
| `simulacao_wokwi/levitador_wokwi/` | Primeira versão da simulação no Wokwi (disco e PID simples), feita antes da montagem. |
| `calibracao/` | Regressão polinomial de 3º grau usada na calibração do sensor. |
| `analise/` | Scripts em Python para gravar ensaios pela serial e gerar as métricas e as figuras do relatório. |
| `simscale/` | Geração da geometria do domínio de CFD (tubo com o carretel), resultados do SimScale e ajuste da força em função da velocidade do ar. |
| `cad/` | Modelos 3D (OpenSCAD + STL prontos para imprimir): estrutura completa do levitador (case do blower, bocal, grade, suporte do sensor, eletroduto, régua, pinos) e o carretel. Veja `cad/README.md`. |
| `dados/` | CSVs dos ensaios usados no relatório (colunas: tempo em ms, referência, posição em cm, PWM em %). |

## Comandos do firmware (Serial Monitor, 115200 baud)

- número (ex.: `25`): referência em cm acima do repouso (2 a 46); `0` desliga o *blower*;
- `modo 1` a `modo 7`: P, PI, PID, PID+Smith, +Overdrive, +Trajetória, Completo (padrão);
- `pwm 40`: PWM manual em %; `auto` volta ao controle;
- `csv 1`: saída em CSV (`t_ms,setpoint,posicao,pwm`) para gravar ensaios;
- a lista completa de comandos está no cabeçalho do `.ino`. A linha do monitor mostra `Setpoint`, `Posicao`, `PWM` e o nome do controle ativo.

Bibliotecas: VL53L0X (Pololu) e NimBLE-Arduino 2.x. Placa "ESP32C3 Dev Module", com USB CDC On Boot.

## Como gerar as figuras

Os scripts são executados a partir da raiz do repositório e gravam as figuras em `relatorio/figuras/`:

```
pip install numpy matplotlib pandas pyserial
mkdir relatorio\figuras
python analise/figuras_relatorio.py
python analise/figura_zoom_serialplot.py
```

## Licença

MIT (veja `LICENSE`). Parte do código foi desenvolvida com auxílio do Claude Code (Anthropic).
