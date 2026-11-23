# Modelos 3D

Todas as peças impressas do levitador, prontas para imprimir.

![Montagem completa](levitador/montagem.png)

## `levitador/stl/`: estrutura do levitador

| Arquivo | Peça |
|---|---|
| `corpo.stl` | Corpo do case do blower (com fundo e janela para a grade) |
| `tampa_case.stl` | Tampa do case, com o furo de saída do blower |
| `bocal.stl` | Bocal adaptador (saída retangular do blower → tubo Ø50 mm) |
| `grade.stl` | Grade hexagonal frontal (encaixe por pressão) |
| `suporte_sensor.stl` | Suporte do sensor VL53L0X no topo do tubo |
| `tampa_sensor.stl` | Tampa de fechamento do suporte do sensor |
| `pino.stl` | Pino de fixação do case (imprimir 4) |
| `clip.stl` | Clipe de trava do pino (imprimir 4) |
| `eletroduto.stl` | Eletroduto dos fios do sensor, em segmentos encaixáveis (todos os segmentos lado a lado; cada um tem no máximo 175 mm) |
| `regua.stl` | Régua antiga, em 4 segmentos impressos em pé (para mesa de 180 mm). Substituída pela régua abaixo |
| `marcas_regua.stl` | Linhas e números da régua antiga, para colar nos rebaixos |

Peças compradas: blower Delta BFB1012EH (9733), tubo de acrílico Ø50 mm × 500 mm, sensor VL53L0X e 2 parafusos M3 com porca.

## `levitador/stl/regua_a1/`: régua 0-50 cm para impressora de 256 mm (Bambu Lab A1)

![Pedaços da régua na mesa da A1](levitador/regua_impressao.png)

A régua é impressa **deitada**, em 2 pedaços (278 e 306 mm) na diagonal da mesa, mais uma sapata. Os números saem **na própria régua**, com o AMS, sem nada para colar.

- **Números embutidos nas duas faces:** as marcações ocupam só as 3 primeiras e as 3 últimas camadas (0,6 mm). A troca de cor acontece em ~6 camadas, não na régua inteira, então gasta pouca purga e imprime rápido.
- **Sem suporte:** a junta é de meia espessura (cada pedaço guarda, na ponta, só a metade que fica na mesa). Os pedaços se sobrepõem 30 mm e são travados por 2 pinos de filamento 1,75 mm (ou parafusos M2): encaixe, passe o filamento pelos furos e corte rente.
- **Sapata separada:** encaixa na ponta de baixo da régua e apoia na flange do bocal, ao lado do tubo.
- **Zero no meio do carretel em repouso:** a régua lê a mesma "Posicao" do firmware (centro do carretel, em cm acima do repouso). O carretel parado desce até a parte afunilada do bocal, e o meio dele fica 1,4 mm acima da base do tubo.

| Arquivo | Uso |
|---|---|
| `regua_1.3mf`, `regua_2.3mf` | **Recomendado.** Abra direto na Bambu Studio: cada um é um objeto com 2 partes, corpo no filamento 1 e números no filamento 2. Coloque azul no slot 1 e branco no 2. O aviso de "configuração inválida" é normal: ele só carrega a geometria e usa os perfis da sua impressora. |
| `regua_N_corpo.stl` + `regua_N_marcas.stl` | As mesmas peças em STL. Importe os dois **juntos**, responda "sim" para carregar como um objeto com várias partes e escolha azul para o corpo e branco para as marcas. |
| `regua_base.stl` | Sapata, impressa em pé, numa cor só, com a abertura para cima. |

Use camada de 0,2 mm e nenhum suporte. As peças já vêm giradas 45° e centradas na mesa. `levitador/ferramentas/stl_para_3mf.py` gera os 3MF a partir dos STLs.

## `carretel/`: objeto que levita

Dois discos ligados por um eixo oco. Funciona como pistão, e o disco de cima é plano para o sensor medir melhor. Imprime em duas metades, sem suporte, com 100% de preenchimento, e as metades são coladas com cola CA.

| Arquivo | Versão |
|---|---|
| `carretel.stl` | v1: usado nos ensaios do relatório e nas simulações de CFD |
| `carretel_v2.stl` | Folga menor, vão maior e discos mais grossos (piorou) |
| `carretel_v2_folga06.stl` | v2 com folga de 0,6 mm |
| `carretel_v3.stl` | Igual ao v1, só com o vão entre os discos aumentado de 30 para 45 mm |
| `carretel_v4.stl` | Borda-guia cônica (efeito Lomakin) para centralizar o carretel no tubo |
