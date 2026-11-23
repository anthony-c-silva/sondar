# Agente do SONDAR (`ufsm-monitor-agent`)

Agente executado em cada sonda (Raspberry Pi ou outro computador Linux). É um único binário Go
que:

- recebe as tarefas do controlador pelo RabbitMQ e executa as medições (ICMP, iperf3, DNS,
  HTTP/HTTPS e traceroute) com tempo limite e **argumentos explícitos**, sem `sh -c`;
- grava cada resultado em uma **fila local SQLite (WAL)** antes de publicar, para que nada se
  perca em quedas da rede ou do broker, e só remove o registro após a confirmação do broker;
- envia a cada 60 s o **inventário e a saúde** da sonda (endereços, rota, DNS, CPU, memória,
  disco, temperatura, limitação térmica, velocidade do enlace e consumo do próprio agente);
- expõe **`/health`, `/version`, `/metadata` e `/services`**;
- **atua como destino** para as medições de outras sondas (ver abaixo);
- roda como serviço **systemd** com reinício automático.

## Serviços de destino

Cada sonda, e o servidor central quando também roda um agente, oferece serviços para ser
medida pelas demais. Isso permite as topologias em estrela e em malha.

| Serviço     | Implementação                                  | Configuração                                    |
| ----------- | ---------------------------------------------- | ----------------------------------------------- |
| **ICMP**    | respondido pelo sistema operacional            | —                                               |
| **HTTP**    | endpoint `/health` do próprio agente           | `HEALTH_ADDR` (`:8080`)                         |
| **iperf3**  | servidor `iperf3 -s` gerenciado pelo agente    | `IPERF3_SERVER`, `IPERF3_PORT` (5201)           |
| **DNS**     | servidor DNS embutido (responde consultas A)   | `DNS_SERVER`, `DNS_PORT` (53), `DNS_ANSWER_IP`  |

Para medir o DNS até a sonda B, o plano usa `resolver = IP da sonda B`. Para medir a vazão até
ela, usa `iperf3` com `target = sonda B`.

## Estrutura

```
agent/
├── cmd/
│   ├── ufsm-monitor-agent/   # executável principal e subcomandos
│   ├── publish-task/         # ferramenta de teste: publica uma tarefa no broker
│   └── sink-results/         # ferramenta de teste: consome e imprime resultados
├── internal/
│   ├── broker/               # conexão AMQP, publicação com confirmação e consumo
│   ├── config/               # variáveis de ambiente e identidade permanente da sonda
│   ├── health/               # servidor /health, /version, /metadata e /services
│   ├── measure/              # icmp, iperf3, dns, http, traceroute, sysinfo e saúde
│   ├── model/                # envelope de resultado e tarefa (espelham os JSON Schemas)
│   ├── outbox/               # fila local SQLite
│   └── targets/              # servidores iperf3 e DNS de destino
├── deploy/                   # unidade systemd e agent.env.example
└── examples/                 # tarefas de exemplo para o subcomando run-task
```

## Pré-requisitos

- Go 1.25 ou superior (apenas para compilar).
- Ferramentas na sonda: `fping`, `iperf3`, `dig` (pacote `dnsutils`) e `mtr`.
- O SQLite usa `modernc.org/sqlite`, escrito em Go puro, o que permite a compilação cruzada
  para ARM sem compilador C.

## Compilação

```bash
cd agent
go mod tidy          # baixa as dependências
go vet ./...
make build           # bin/ufsm-monitor-agent
make build-arm64     # Raspberry Pi 64 bits -> bin/arm64/
make build-armv7     # Raspberry Pi 32 bits -> bin/armv7/
```

## Subcomandos

| Subcomando            | Função                                                        |
| --------------------- | ------------------------------------------------------------- |
| `serve`               | modo de serviço (broker, destinos, inventário e `/health`)    |
| `run-task <arquivo>`  | executa uma tarefa local e imprime o envelope do resultado    |
| `inventory`           | imprime o inventário e a saúde da sonda                       |
| `version`             | imprime a versão                                              |

Exemplo de execução local, sem systemd:

```bash
PROBE_ID=probe-dev-01 SQLITE_PATH=./agent.db \
  ./bin/ufsm-monitor-agent run-task examples/task-icmp.json

PROBE_ID=probe-dev-01 SQLITE_PATH=./agent.db HEALTH_ADDR=:8080 AMQP_URL=off \
  ./bin/ufsm-monitor-agent serve
curl localhost:8080/health
```

## Instalação como serviço

```bash
sudo useradd --system --no-create-home ufsm-monitor
sudo install -m 0755 bin/arm64/ufsm-monitor-agent /usr/local/bin/
sudo mkdir -p /etc/ufsm-monitor
sudo cp deploy/agent.env.example /etc/ufsm-monitor/agent.env   # ajuste AMQP_URL e rótulos
sudo chmod 600 /etc/ufsm-monitor/agent.env
sudo cp deploy/ufsm-monitor-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ufsm-monitor-agent
journalctl -u ufsm-monitor-agent -f
```

Se o pacote `iperf3` instalou o serviço `iperf3.service` do sistema, desligue-o com
`sudo systemctl disable --now iperf3`, porque ele ocupa a porta 5201 usada pelo agente.

O passo a passo completo da implantação está em [`../docs/DEPLOY-FISICO.md`](../docs/DEPLOY-FISICO.md).

## Caminho do módulo

O módulo Go se chama `github.com/anthonycarlosp7/ufsm-monitor-agent`. O nome é usado apenas
nos imports internos, e a compilação não depende de ele existir no GitHub.
