# SONDAR

**Sistema Orquestrado de Nós Distribuídos para Avaliação de Redes.** Plataforma distribuída de
código aberto para o monitoramento ativo de redes de campus.

Sondas de baixo custo (Raspberry Pi) executam medições de latência, perda, vazão, resolução de
nomes, acesso web e caminho, definidas em planos de medição. Um controlador central valida os
planos, agenda as tarefas, coordena os testes de vazão e grava os resultados como séries
temporais, exibidas em um painel web com acesso restrito. Todos os dados ficam no servidor da
própria instituição.

Trabalho de Conclusão de Curso em Ciência da Computação, Universidade Federal de Santa Maria
(UFSM), 2026. Autor Anthony Carlos da Silva, orientador Prof. Carlos Raniery.

## Recursos

- **Medições ativas.** ICMP (`fping`), vazão (`iperf3`), DNS (`dig`), caminho (`mtr`) e acesso
  web com o tempo separado em resolução de nomes, conexão TCP, negociação TLS e espera pelo
  primeiro byte (`httptrace`, com conexão nova a cada medição).
- **Sondas homogêneas.** Cada sonda mede e também atua como destino (servidor iperf3, DNS e
  HTTP), o que permite topologias em estrela e em malha.
- **Planos de medição em JSON.** O controlador valida o plano (sondas existentes, lista de
  destinos permitidos, período mínimo e limites) e o expande nas tarefas de cada sonda.
- **Coordenação dos testes de vazão.** Cada teste reserva as sondas e, no modo por trecho, os
  enlaces compartilhados do caminho, cadastrados pelo operador. Dois testes que usam o mesmo
  recurso não rodam juntos, e a reserva é liberada quando o resultado chega ao banco. Modos
  `sonda`, `trecho` e `global`.
- **Entrega confiável.** Tarefas e resultados trafegam pelo RabbitMQ com confirmação de
  publicação. Na sonda, uma fila local em SQLite guarda o resultado até a entrega.
- **Saúde das sondas.** Temperatura, frequência e uso do processador, limitação térmica,
  memória, tempo ligado, velocidade do enlace e consumo do próprio agente, atualizados a cada
  minuto.
- **Painel web.** Login com troca de senha obrigatória, cadastro de sondas, destinos, grupos e
  enlaces, construtor de planos, séries temporais, matriz sonda × destino, traceroute e saúde
  das sondas.

## Arquitetura

A plataforma segue a divisão funcional do modelo LMAP (RFC 7594).

```
Painel web (React/Vite + Nginx)
        │  API REST com autenticação
        ▼
Controlador (Python + FastAPI)   planos, validação, agendamento, coordenação da vazão
        │
        ▼
RabbitMQ (AMQP)                  tarefas e resultados
        │
        ▼
Sondas (agente em Go)            executam as medições e atuam como destino
        │
        ▼
Ingestão (Python)                consome os resultados
        │
        ▼
PostgreSQL + TimescaleDB         inventário, planos e séries temporais
```

Os diagramas C4 e de sequência estão em [`docs/arquitetura/`](docs/arquitetura/).

## Estrutura do repositório

| Caminho              | Conteúdo                                                                       |
| -------------------- | ------------------------------------------------------------------------------ |
| `agent/`             | Agente em Go, cross-compilado para ARM e instalado como serviço `systemd`      |
| `controller/`        | Controlador e ingestão (Python/FastAPI), com testes                            |
| `web/`               | Painel web (React/Vite servido por Nginx)                                      |
| `contracts/`         | Formatos das mensagens em JSON Schema, compartilhados entre agente e controlador |
| `deploy/`            | Atualização automática do servidor a cada `git push` com CI aprovado           |
| `tools/`             | Teste de escalabilidade, experimento de interferência e análise do estudo de caso |
| `prototypes/`        | Protótipos iniciais das medições em Go                                         |
| `scripts/`           | Utilitários (validador de resultados, `demo-seed.sh`)                          |
| `docs/`              | Diagramas da arquitetura, guia de implantação física e material de referência  |

## Execução local com Docker

Pré-requisito: Docker com Docker Compose.

```bash
# Demonstração local, com duas sondas de exemplo em contêiner
docker compose --profile demo up -d --build
bash scripts/demo-seed.sh

# Servidor de produção, sem as sondas de exemplo
docker compose up -d --build
```

Endereços:

- Painel web: http://localhost:8080 (usuário inicial `admin` / `admin`, troca de senha
  obrigatória no primeiro acesso)
- API e documentação Swagger: http://localhost:8000/docs
- RabbitMQ Management: http://localhost:15672

## Implantação

- **Servidor central.** Executa os contêineres do controlador, da ingestão, do RabbitMQ, do
  TimescaleDB e do painel. A pasta [`deploy/`](deploy/README.md) traz o serviço que atualiza o
  servidor a cada `git push`.
- **Sondas.** Cada Raspberry Pi executa apenas o binário do agente (`cd agent && make
  build-arm64`) como serviço `systemd`, com o arquivo `agent.env` apontando para o RabbitMQ do
  servidor. Não precisa de Docker nem do repositório.

O passo a passo está em [`docs/DEPLOY-FISICO.md`](docs/DEPLOY-FISICO.md).

### Segurança

As credenciais do `docker-compose.yml` (`guest/guest` no RabbitMQ e `ufsm/ufsm` no banco) são
para demonstração. Em produção, troque essas senhas, defina `SECRET_KEY`, restrinja as portas
5432 e 15672 ao próprio servidor e crie no RabbitMQ um usuário próprio para as sondas.

## Avaliação

A plataforma foi implantada no Centro de Tecnologia da UFSM com três sondas e um servidor
central. Os scripts usados na avaliação do TCC estão em [`tools/`](tools/).

- [`tools/estudo-de-caso/`](tools/estudo-de-caso/) exporta os dados do banco e gera as tabelas e
  figuras do estudo de caso.
- [`tools/loadtest/`](tools/loadtest/) simula até milhares de sondas para medir a escalabilidade
  do servidor.
- [`tools/interferencia/`](tools/interferencia/) compara testes de vazão simultâneos e
  coordenados entre sondas que compartilham um enlace.

## Licença

Distribuído sob a licença MIT. Veja [`LICENSE`](LICENSE).
