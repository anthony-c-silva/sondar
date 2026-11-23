# infra (legado)

Infraestrutura usada nas primeiras fases do desenvolvimento, antes do `docker-compose.yml` da
raiz. Não é usada pelo servidor de produção.

- `docker-compose.yml`: RabbitMQ para desenvolvimento local do agente.
- `grafana/`: provisionamento do Grafana (fonte de dados TimescaleDB e o painel de visão
  geral) usado antes do painel web próprio, que hoje fica em [`../web/`](../web/).

Para executar a plataforma, use o `docker-compose.yml` da raiz do repositório, como descrito no
[`README.md`](../README.md) principal.

## Teste de tolerância a falhas

Este ambiente foi usado para verificar que nenhum resultado se perde quando o broker cai. Com o
agente rodando, pare o RabbitMQ (`docker compose stop rabbitmq`), gere medições, que ficam na
fila local SQLite do agente, e religue o broker (`docker compose start rabbitmq`). A tabela
`result_outbox` do agente esvazia à medida que os resultados são publicados e confirmados.
