# Análise do estudo de caso

Exporta do banco as medições do período de coleta e gera os gráficos e as
tabelas do Capítulo 5.

| Arquivo | Onde roda | Função |
|---|---|---|
| `exportar.sh` | servidor | grava os CSV do período (ICMP, HTTP, vazão, DNS, traceroute, execuções, saúde das sondas, destinos e sondas) |
| `analisar.py` | qualquer máquina com pandas e matplotlib | gera figuras (PDF e PNG), tabelas (CSV e trecho LaTeX) e `resumo.md` |
| `config.json` | — | períodos válidos de cada sonda, grupos de destinos, horário de uso e feriados |
| `simular.py` | qualquer máquina | gera dados fictícios no mesmo formato, para testar a análise |

## 1. Exportar (no servidor)

```bash
cd /opt/ufsm-monitor/tools/estudo-de-caso
bash exportar.sh 2026-11-05 2026-11-18 dados
tar czf dados.tgz dados
```

A data final é exclusiva (2026-11-18 inclui todo o dia 17). Para trazer o
arquivo para o computador (PowerShell):

```powershell
scp <usuario>@<IP-SERVIDOR>:/opt/ufsm-monitor/tools/estudo-de-caso/dados.tgz .
```

## 2. Conferir o config.json

- `sondas.*.estudo`: intervalo em que cada sonda está no ponto do estudo.
  Uma sonda que mudou de ponto deve começar no horário da instalação no ponto final.
- `sondas.*.referencia`: intervalo de comparação (a ct-01 na rede da TI, antes
  de ir para o anexo C).
- `horario_uso`: dias e horas considerados de uso (padrão: segunda a sexta,
  8 h às 18 h). `feriados` entram como fim de semana.
- `incidentes`: caminho do `registro-incidentes.csv` (separado por `;`), cujos
  horários aparecem como linhas verticais nas séries temporais.

## 3. Analisar

```bash
python3 analisar.py dados --saida resultados
# figura de um intervalo específico (ex.: pico de TLS)
python3 analisar.py dados --saida resultados --janela "2026-11-10 13:30" "2026-11-10 14:00" --destino ufsm-web
```

## O que é gerado

Figuras (`resultados/figuras`):

- `serie_rtt_infra`, `serie_rtt_externo`, `serie_rtt_malha`: RTT ao longo da
  coleta (mediana de 15 min), com noites e fins de semana sombreados e a data
  de instalação de cada sonda.
- `serie_rtt_destino_*`: o mesmo, por destino externo (para ver eventos que
  aparecem em mais de uma sonda ao mesmo tempo).
- `perfil_rtt_*` e `perfil_perda_*`: RTT e perda por hora do dia, dia útil
  contra fim de semana, uma coluna por sonda.
- `box_rtt_uso_infra`: distribuição do RTT no horário de uso e fora dele, por sonda.
- `http_etapas`: tempo mediano de cada etapa do acesso web (DNS, conexão TCP,
  TLS, espera do servidor, transferência), por destino e sonda.
- `http_horario_*`: as mesmas etapas por hora do dia, em dias úteis.
- `http_janela_*`: conexão TCP, TLS e espera do servidor num intervalo escolhido.
- `vazao_serie` e `vazao_horario`: vazão de cada fluxo ao longo da coleta e por hora do dia.
- `consumo_sondas`: CPU do agente e temperatura das sondas.

Tabelas (`resultados/tabelas`): `icmp_resumo`, `http_etapas`, `vazao_resumo`,
`dns_resumo`, `rotas_resumo`, `rotas_mudancas`, `consumo_sondas`,
`execucoes_sucesso` e `antes_depois` (a ct-01 na rede da TI e no anexo C).

## Testar com dados simulados

```bash
python3 simular.py dados_simulados
python3 analisar.py dados_simulados --saida resultados_simulados
```

Os dados simulados não são medições reais e servem apenas para testar os scripts.
