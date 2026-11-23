# Atualização automática do servidor central

O servidor consulta o GitHub a cada 2 minutos e, quando há um commit novo no branch `main`
com o CI aprovado, atualiza o código e reconstrói os contêineres. Quem inicia a conexão é o
servidor, apenas com saída HTTPS, então o mecanismo funciona atrás de firewall e NAT sem abrir
portas de entrada.

## Pré-requisitos no servidor

- Ubuntu Server com **Docker**, **Docker Compose** e **git**.
- Um usuário no grupo `docker` (no exemplo, `ufsm`):
  ```bash
  sudo usermod -aG docker ufsm      # vale a partir do próximo login
  ```

## 1. Clonar o repositório

```bash
sudo mkdir -p /opt/ufsm-monitor
sudo chown ufsm:ufsm /opt/ufsm-monitor
git clone https://github.com/anthony-c-silva/sondar /opt/ufsm-monitor
cd /opt/ufsm-monitor
```

Para um repositório privado, gere uma chave somente leitura no servidor, cadastre-a no GitHub
em **Settings → Deploy keys** e clone por SSH:

```bash
ssh-keygen -t ed25519 -C "servidor-sondar" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
git clone git@github.com:anthony-c-silva/sondar /opt/ufsm-monitor
```

## 2. Testar manualmente

```bash
bash deploy/deploy.sh          # na primeira vez sobe a stack; depois só atualiza se houver commit novo
docker compose ps
```

## 3. Ativar o timer

Ajuste `User` e os caminhos no `.service` se o usuário ou a pasta forem outros.

```bash
sudo cp deploy/ufsm-monitor-deploy.service /etc/systemd/system/
sudo cp deploy/ufsm-monitor-deploy.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ufsm-monitor-deploy.timer
```

## Acompanhamento

```bash
systemctl list-timers | grep ufsm-monitor      # próxima execução
systemctl status ufsm-monitor-deploy.service   # resultado da última execução
journalctl -u ufsm-monitor-deploy.service -f   # log em tempo real
```

## Ajustes

- **Frequência:** altere `OnUnitActiveSec` no `.timer` e rode
  `sudo systemctl daemon-reload && sudo systemctl restart ufsm-monitor-deploy.timer`.
- **Branch:** altere `DEPLOY_BRANCH` no `.service` (padrão `main`).
- **Executar agora:** `sudo systemctl start ufsm-monitor-deploy.service`.
- **Pausar:** `sudo systemctl disable --now ufsm-monitor-deploy.timer`.

## Trava de CI

Com `REQUIRE_CI=1` (padrão), o `deploy.sh` só atualiza para um commit depois que o workflow
`.github/workflows/ci.yml` desse commit for aprovado, consultando a API do GitHub Actions. Se o
CI ainda estiver rodando, a atualização fica para o próximo ciclo; se falhar, o servidor espera
um commit aprovado.

- **Desligar a trava:** `Environment=REQUIRE_CI=0` no `ufsm-monitor-deploy.service`.
- **Repositório privado ou limite da API:** `Environment=GITHUB_TOKEN=<token somente leitura>`.
- O `owner/repo` é obtido do `git remote`; para fixar, use `REPO_SLUG=owner/repo`.

## Observações

- O `deploy.sh` sobe apenas os serviços do servidor (controlador, ingestão, RabbitMQ,
  TimescaleDB e painel). As sondas são instaladas à parte, como descrito em
  [`../docs/DEPLOY-FISICO.md`](../docs/DEPLOY-FISICO.md).
- A atualização reinicia o controlador. Evite publicar commits durante um experimento em
  andamento.
