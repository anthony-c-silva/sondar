# Painel web do SONDAR (React + Vite)

Interface de administração e visualização da plataforma, com login, tema escuro, layout
responsivo, fonte Inter e ícones `lucide-react`.

## Telas

- **Login:** no primeiro acesso, `admin` / `admin`, com troca de senha obrigatória.
- **Visão geral:** contadores, estado do agendador e atividade das últimas 24 horas.
- **Probes:** cadastro das sondas, estado de conexão e saúde (temperatura, CPU, memória,
  limitação térmica, velocidade do enlace), com gráficos por sonda.
- **Destinos:** lista de destinos externos permitidos.
- **Grupos:** grupos de sondas usados nos planos.
- **Planos:** construtor visual dos planos de medição (tipo de teste, sondas, destinos,
  período, estrela ou malha), importação de JSON, validação, edição e execução imediata.
- **Enlaces:** cadastro dos enlaces compartilhados, cadeia de uplink de cada sonda e modo de
  coordenação dos testes de vazão.
- **Séries:** séries temporais por métrica (latência, perda, vazão, DNS e etapas do HTTP).
- **Matriz & status:** matriz sonda × destino e caminho (traceroute).
- **Usuários:** criação e remoção de usuários.

Os painéis se atualizam a cada 30 s quando a atualização automática está ligada.

## Autenticação

O painel guarda um token de acesso de curta duração e um token de renovação rotativo. O token
de acesso vai no cabeçalho `Authorization` e, quando expira, é renovado automaticamente. Ao
trocar a senha, as outras sessões do usuário são encerradas.

## Acesso à API

O painel chama `/api/...`. Em desenvolvimento, o Vite encaminha `/api` para o controlador em
`http://localhost:8000`. Em produção, o Nginx do contêiner faz o mesmo para
`http://controller:8000`, de modo que painel e API ficam na mesma origem.

## Desenvolvimento

```bash
cd web
npm install
npm run dev            # http://localhost:5173 (controlador em :8000)
```

## Produção (Docker)

```bash
docker compose up -d --build web
```

O painel fica em http://localhost:8080.
