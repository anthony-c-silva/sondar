# Controlador e ingestão do SONDAR

Serviços em Python (FastAPI + SQLAlchemy + Pydantic + pika) que rodam no servidor central.

- **Controlador** (`app.main`): mantém o inventário (sondas, destinos, grupos e enlaces), valida
  e expande os planos de medição em tarefas, agenda as execuções, coordena os testes de vazão e
  expõe a API usada pelo painel web.
- **Ingestão** (`app.ingestion`): consome os resultados do RabbitMQ e os grava no
  PostgreSQL/TimescaleDB, em hypertables por tipo de medição.

## Módulos

| Arquivo            | Função                                                                    |
| ------------------ | ------------------------------------------------------------------------- |
| `main.py`          | API REST e inicialização                                                  |
| `auth.py`          | login com JWT, refresh rotativo, bcrypt e limite de tentativas            |
| `models.py`        | tabelas do inventário, planos, usuários e enlaces                         |
| `schemas.py`       | modelos Pydantic dos planos e das requisições                             |
| `planning.py`      | validação dos planos e expansão em tarefas (estrela e malha `n(n-1)`)     |
| `scheduler.py`     | agendador periódico e serializador dos testes de vazão                    |
| `coordination.py`  | recursos de cada teste de vazão (sondas, enlaces) e modos de coordenação  |
| `publisher.py`     | publicação das tarefas no RabbitMQ com confirmação                        |
| `ingestion.py`     | consumo dos resultados e gravação no banco                                |
| `analytics.py`     | consultas de séries, matriz, saúde das sondas e testes de vazão           |

## API

Todas as rotas exigem autenticação, exceto `/health`, `/auth/login`, `/auth/refresh` e a documentação. A documentação interativa
fica em `/docs` (Swagger).

| Grupo           | Rotas principais                                                                    |
| --------------- | ----------------------------------------------------------------------------------- |
| Autenticação    | `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/me`, `/auth/change-password` |
| Usuários        | `/users`                                                                            |
| Inventário      | `/probes`, `/probes/status`, `/probes/{id}/health`, `/targets`, `/groups`           |
| Enlaces         | `/links`, `/probes/uplinks`, `/probes/{id}/uplinks`                                 |
| Planos          | `/plans`, `/plans/validate`, `/plans/{id}/run`, `/plans/{id}/enable`, `/plans/{id}/disable` |
| Agendador       | `/scheduler/status`, `/scheduler/coordination`, `/scheduler/coordination/check`     |
| Medições        | `/measurements/series`, `/measurements/matrix`, `/measurements/recent`, `/measurements/traceroute`, `/measurements/iperf3/runs` |
| Estatísticas    | `/stats/overview`, `/stats/activity`                                                |

## Agendamento e coordenação

Com `SCHEDULER=on` (padrão), o controlador executa sozinho os planos habilitados, respeitando o
`period_seconds` de cada job, com uma variação aleatória (`JOB_JITTER_PCT`) para evitar que as
tarefas fiquem sincronizadas.

Os testes de vazão passam por uma fila. Cada teste reserva os recursos que usa, e dois testes
que compartilham um recurso não rodam ao mesmo tempo. O modo é escolhido no painel ou em
`PUT /scheduler/coordination`.

| Modo      | Recursos reservados                                                          |
| --------- | ---------------------------------------------------------------------------- |
| `sonda`   | as duas sondas do teste                                                      |
| `trecho`  | as sondas e os enlaces cadastrados que o caminho entre elas atravessa       |
| `global`  | as sondas e um recurso comum a todos, ou seja, um teste de vazão por vez na rede |

A reserva é liberada quando o resultado do teste chega ao banco. Se o resultado não chegar, ela
é liberada depois da duração do teste somada a `TASK_TTL_SECONDS` e a `IPERF3_SLACK_SECONDS`.

## Configuração

As variáveis ficam em `.env` (ver `.env.example`) ou no `docker-compose.yml`.

| Variável                | Padrão   | Função                                                       |
| ----------------------- | -------- | ------------------------------------------------------------ |
| `DATABASE_URL`          | local    | conexão com o PostgreSQL/TimescaleDB                         |
| `AMQP_URL`              | local    | conexão com o RabbitMQ                                       |
| `SECRET_KEY`            | gerada   | chave dos tokens JWT; se vazia, é gerada e guardada no banco |
| `FRONTEND_ORIGINS`      | `*`      | origens permitidas no CORS                                   |
| `MIN_PERIOD_SECONDS`    | 10       | período mínimo aceito em um plano                            |
| `MAX_IPERF_DURATION`    | 30       | duração máxima de um teste de vazão (s)                      |
| `MAX_TASKS_PER_CYCLE`   | 500      | limite de tarefas geradas por plano                          |
| `TASK_TTL_SECONDS`      | 90       | validade de cada tarefa publicada                            |
| `SCHEDULER`             | `on`     | `off` desliga o agendador automático                         |

No primeiro início é criado o usuário `admin` com senha `admin`, e a troca de senha é
obrigatória no primeiro login.

## Execução para desenvolvimento

```bash
cd controller
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

uvicorn app.main:app --reload --port 8000   # controlador
python -m app.ingestion                     # ingestão, em outro terminal
```

O RabbitMQ e o TimescaleDB podem ser iniciados pelo `docker-compose.yml` da raiz:
`docker compose up -d rabbitmq timescaledb`.

## Testes

```bash
cd controller
python -m pytest tests
```

## Exemplos de planos

A pasta `examples/` contém planos prontos para importar, entre eles `plan-malha-ufsm.json`
(ICMP, DNS, HTTP e traceroute em malha) e `plan-malha-vazao.json` (vazão entre as sondas).
