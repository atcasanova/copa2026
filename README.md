# Bolão Copa do Mundo 2026 (Prediction Pool System)

Este projeto consiste em um sistema completo de Bolão para a Copa do Mundo FIFA 2026. A aplicação foi construída em **Português Brasileiro (PT-BR)**, oferecendo uma experiência imersiva e visualmente premium baseada no **Google Material Design**.

---

## Stack Tecnológica Utilizada

- **Backend**: Python FastAPI com SQLAlchemy ORM, Pydantic para validação, e APScheduler rodando em segundo plano.
- **Frontend**: React (Vite) integrado à biblioteca de componentes Material-UI (MUI v5) para interface responsiva, com suporte a hot-reload (HMR) e temas escuros (Dark Mode).
- **Banco de Dados**: PostgreSQL 15 rodando sob Docker Compose.
- **Background Jobs**: Agendador APScheduler interno configurado para executar a sincronização automática diária às 01:00 AM (America/Sao_Paulo) e lembretes de palpites a cada 5 minutos.
- **Ambiente**: Orquestração completa de contêineres via Docker Compose.

---

## Pré-requisitos

Para executar o projeto localmente, é necessário ter instalado em sua máquina:
- **Docker**
- **Docker Compose**

---

## Como Executar o Projeto

1. Copie o arquivo de exemplo e ajuste os valores sensíveis:
   ```bash
   cp .env.example .env
   ```
2. Na pasta raiz do projeto (`Bolao/`), execute o comando para compilar e iniciar os contêineres:
   ```bash
   docker-compose up --build -d
   ```
3. O Docker Compose iniciará três serviços:
   - **Banco de Dados**: PostgreSQL acessível apenas pela rede Docker interna.
   - **Backend**: publicado localmente em `http://127.0.0.1:3998` (OpenAPI em `http://127.0.0.1:3998/docs`).
   - **Frontend**: publicado localmente em `http://127.0.0.1:3999`.

---

## Variáveis do Arquivo `.env`

O arquivo `.env` gerencia as configurações cruciais e credenciais de segurança do sistema. Segue a listagem das variáveis necessárias:

| Variável | Descrição | Valor Padrão (Exemplo) |
| --- | --- | --- |
| `TZ` | Timezone padrão do sistema | `America/Sao_Paulo` |
| `POSTGRES_USER` | Nome do usuário do banco PostgreSQL | `bolao_user` |
| `POSTGRES_PASSWORD` | Senha de acesso ao banco PostgreSQL | `bolao_secure_password_2026` |
| `POSTGRES_DB` | Nome do banco de dados | `bolao_db` |
| `DATABASE_URL` | String de conexão para o SQLAlchemy | `postgresql://bolao_user:password@db:5432/bolao_db` |
| `JWT_SECRET` | Chave secreta de codificação dos tokens JWT | `change_me_with_a_strong_random_secret` |
| `JWT_ALGORITHM` | Algoritmo de assinatura dos tokens JWT | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Expiração da sessão do usuário (em minutos) | `1440` (24 horas) |
| `CORS_ORIGINS` | Origens permitidas para chamadas ao backend | `http://localhost:3999` |
| `FRONTEND_URL` | URL pública do frontend usada em links de reset de senha | `https://bolao.example.com` |
| `ENABLE_ADMIN_BOOTSTRAP` | Habilita criação do admin inicial no startup | `true` na primeira execução |
| `ADMIN_BOOTSTRAP_USERNAME` | Nome do usuário do primeiro administrador | `admin` |
| `ADMIN_BOOTSTRAP_EMAIL` | E-mail do usuário administrador inicial | `admin@bolao2026.com.br` |
| `ADMIN_BOOTSTRAP_PASSWORD` | Senha de login do usuário administrador | `AdminSecurePassword2026!` |
| `TEAMS_JSON_URL` | Link JSON dos times do openfootball | *(URL Raw GitHub)* |
| `STADIUMS_JSON_URL` | Link JSON dos estádios do openfootball | *(URL Raw GitHub)* |
| `MATCHES_JSON_URL` | Link JSON das partidas do openfootball | *(URL Raw GitHub)* |
| `OPENFOOTBALL_DAILY_SYNC_ENABLED` | Habilita o job diário automático de sincronização openfootball | `false` |
| `SMTP_HOST` / `SMTP_PORT` | Servidor SMTP para reset de senha | `mail.example.internal` / `25` |
| `SMTP_STARTTLS` | Habilita STARTTLS no SMTP | `false` |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | Credenciais SMTP, se necessárias | vazio |
| `SMTP_FROM` | Remetente dos e-mails do sistema | `bolao@example.com` |
| `ADMIN_REGISTRATION_NOTIFY_ENABLED` | Envia e-mail aos administradores quando um novo usuário se cadastra | `true` |
| `ADMIN_REGISTRATION_NOTIFY_TO` | Destinatários da notificação de cadastro, separados por vírgula. Se vazio, usa todos os `system_admin` ativos | vazio |
| `WHATSAPP_NOTIFY_ENABLED` | Habilita mensagens via API interna de WhatsApp | `false` |
| `WHATSAPP_NOTIFY_URL` | Endpoint de envio da API de WhatsApp | `http://whatsgo-bot-1:9999/internal/v1/send` |
| `WHATSAPP_NOTIFY_TOKEN` | Bearer token da API interna de WhatsApp | `change_me_whatsapp_internal_api_token` |
| `WHATSAPP_NOTIFY_TO` | ID do grupo/contato de destino | `120363000000000000@g.us` |
| `WHATSAPP_NOTIFY_SEND_AS` | Formato de envio da API de WhatsApp | `text` |
| `WHATSAPP_NOTIFY_TIMEOUT_SECONDS` | Timeout do envio em segundos | `5` |
| `WHATSAPP_GROUP_CHAT` | Link do grupo de WhatsApp exibido no perfil dos participantes | `https://chat.whatsapp.com/change_me_invite_code` |
| `FOOTBALL_DATA_ENABLED` | Habilita a consulta automática de placares no football-data.org | `true` |
| `FOOTBALL_DATA_API` | Token da API football-data.org enviado no header `X-Auth-Token` | `change_me_football_data_api_token` |
| `FOOTBALL_DATA_COMPETITION` | Código da competição no football-data.org | `WC` |
| `FOOTBALL_DATA_TIMEOUT_SECONDS` | Timeout da consulta de placares em segundos | `10` |
| `FOOTBALL_DATA_MAX_REQUESTS_PER_RUN` | Limite de chamadas HTTP ao football-data.org por execução do job | `8` |
| `GITHUB_AUDIT` | Habilita publicação dos blocos de auditoria dos palpites no GitHub | `false` |
| `GITHUB_REPO` | Repositório usado apenas para os blocos de auditoria | `git@github.com:seu-usuario/palpites-copa-2026-auditoria.git` |
| `GITHUB_TOKEN` | Token do GitHub com permissão de leitura/escrita em Contents no repositório | `change_me_github_token_with_contents_write` |

---

## Usuário Administrador Inicial (Bootstrap)

Na inicialização do backend FastAPI, o sistema verifica automaticamente a tabela de usuários:
- Se ela estiver vazia, ele realiza o **Bootstrap** do usuário administrador utilizando os dados fornecidos no `.env` (`ADMIN_BOOTSTRAP_USERNAME`, `ADMIN_BOOTSTRAP_PASSWORD` e `ADMIN_BOOTSTRAP_EMAIL`) e define sua permissão como `system_admin`.
- Você poderá logar imediatamente no frontend (`http://localhost:3000`) utilizando as credenciais configuradas para acessar a área administrativa.

---

## Importação dos Dados Iniciais da Copa do Mundo

No primeiro boot do contêiner backend:
1. O FastAPI executará as tarefas de **startup**.
2. Criará automaticamente todas as tabelas no PostgreSQL.
3. Consultará de forma transparente as URLs do openfootball indicadas no `.env` para carregar todos os **Times**, **Estádios** e **Partidas** da Copa do Mundo 2026.
4. Caso queira reimportar ou executar esta carga inicial novamente de forma forçada, acesse o painel **Administração > Sincronização** e clique em **Seed Carga Inicial**.

---

## Funcionamento da Sincronização Diária (Daily Sync)

- O job diário do openfootball só é agendado quando `OPENFOOTBALL_DAILY_SYNC_ENABLED=true`. Por padrão ele fica desligado, pois os placares automáticos vêm do football-data.org.
- Quando habilitado, o sistema agenda um job em segundo plano (APScheduler) para executar diariamente às **01:00 AM (fuso America/Sao_Paulo)**.
- O job baixa a versão mais atualizada dos confrontos e compara com os registros locais.
- Se o placar de uma partida estiver marcado como **confirmado por um administrador** (`score_confirmed_by_admin = True`), a sincronização **NÃO** alterará o placar local. Em vez disso, salvará um alerta na tabela de diferenças (Diffs) exibido no menu administrativo, aguardando aprovação humana para evitar fraudes ou perdas.
- Se o placar local não estiver confirmado ou for nulo, a sincronização atualiza as informações e dispara automaticamente o **Recálculo de Notas e Classificações**.
- Quando a sincronização encontra os confrontos de mata-mata definidos (substituindo placeholders como "Winner Group A" por times reais como "Mexico"), ela atualiza o confronto e destrava os palpites dos usuários, caso a regra de bloqueio configurada no painel administrativo ainda não tenha expirado.

---

## Notificações via WhatsApp

O backend pode enviar mensagens para uma API interna de WhatsApp configurada pelas variáveis `WHATSAPP_NOTIFY_*`.

Eventos enviados:
- Aprovação de pagamento: informa que o pagamento do participante foi aprovado.
- Lembretes de palpites: enviados 2h30 antes de cada horário de jogos, com a lista das partidas daquele horário e a quantidade de participantes que ainda não palpitaram em cada jogo.
- Ranking atualizado: enviado quando todos os placares de um mesmo horário entram no ranking, com top 10 geral, medalhas nos três primeiros e indicadores de mudança de posição (`🟢⬆️N` para subida, `🔴⬇️N` para queda).

Recomendação de Docker:
- Se a API de WhatsApp estiver em outro Compose no mesmo host, conecte o `bolao_backend` à mesma rede Docker dessa API e use o nome do serviço na URL, por exemplo `http://whatsgo-bot-1:9999/internal/v1/send`.
- Alternativamente, publique a API no host com `ports: ["9998:9999"]` e use `http://host.docker.internal:9998/internal/v1/send`, mantendo o `extra_hosts` já configurado no backend.

---

## Placar Automático

Quando `FOOTBALL_DATA_ENABLED=true` e `FOOTBALL_DATA_API` está configurada, o backend consulta o football-data.org uma vez por minuto. A consulta só considera partidas sem placar a partir de 2 horas depois do horário de início. Se houver mais de um jogo no mesmo horário, o ranking só é recalculado quando todos os jogos daquele horário estiverem com status `FINISHED` na API. Para respeitar o plano free, cada execução faz no máximo `FOOTBALL_DATA_MAX_REQUESTS_PER_RUN` chamadas HTTP.

Para prorrogação ou pênaltis, o sistema usa `score.regularTime` quando disponível; em partidas encerradas no tempo normal, usa `score.fullTime`. O endpoint administrativo `POST /api/admin/football-data/check-scores` dispara a mesma verificação manualmente para testes.

---

## Auditoria Externa no GitHub

Além da cadeia criptográfica gravada no banco, o backend pode publicar cada bloco de auditoria em um repositório GitHub dedicado exclusivamente aos palpites. O repositório configurado para produção é:

`git@github.com:atcasanova/palpites-copa-2026-auditoria.git`

Quando `GITHUB_AUDIT=true`, cada bloco gerado após o bloqueio de uma partida é enviado para `blocks/block_XXXXXX_match_YY.json` por meio da API de Contents do GitHub. O arquivo contém partida, payload dos palpites, hash anterior, hash atual e instruções de verificação. A publicação é feita em modo best-effort: se o GitHub estiver indisponível ou o token estiver inválido, o bloco local continua sendo criado e a falha fica registrada no log do backend.

Configure:

```env
GITHUB_AUDIT=true
GITHUB_REPO=git@github.com:atcasanova/palpites-copa-2026-auditoria.git
GITHUB_TOKEN=SEU_TOKEN_COM_CONTENTS_READ_WRITE
```

O token nunca deve ser commitado. A tela **Auditoria Criptográfica** exibe o link do repositório para validação pública.

---

## Regras de Pontuação (Scoring System)

A nota base de cada palpite é avaliada contra o resultado regulamentar oficial de 120 minutos (tempo normal mais acréscimos e prorrogações), excluindo cobranças de pênaltis.
- **Placar Exato**: 10 pontos (ex: Palpite 2x1, Oficial 2x1).
- **Resultado Correto e Diferença de Gols (não exato)**: 6 pontos (ex: Palpite 3x2, Oficial 2x1).
- **Resultado Correto + Gols de um dos times**: 4 pontos (ex: Palpite 2x0 ou 3x1, Oficial 2x1).
- **Resultado Correto Apenas**: 3 pontos (ex: Palpite 4x2, Oficial 2x1).
- **Resultado Incorreto**: 0 pontos.

### Multiplicadores de Fase
A pontuação final é dada por: `Pontos Ganhos = Pontos Base * Multiplicador da Fase`.
Os multiplicadores padrão recomendados (editáveis por administradores) são:
- Fase de Grupos: `x1.0`
- Dezesseis-avos (Round of 32): `x2.0`
- Oitavas de Final: `x3.0`
- Quartas de Final: `x4.0`
- Semifinal: `x5.0`
- Final: `x6.0`

*Nota: Mudar o multiplicador em tempo de jogo recalcula retroativamente os pontos e atualiza o ranking de forma consistente.*

---

## Classificação e Critérios de Desempate

O ranking oficial é calculado de forma determinística utilizando os seguintes tie-breakers em ordem de prioridade:
1. Maior número de pontos totais acumulados.
2. Maior quantidade de placares exatos acertados (10 pontos).
3. Maior quantidade de resultados gerais corretos (3, 4 ou 6 pontos).
4. Maior pontuação obtida nas fases eliminatórias (Mata-mata).
5. Menor quantidade de palpites perdidos (missing predictions) em confrontos já iniciados/bloqueados.
6. Data de cadastro mais antiga no sistema.
7. Ordem alfabética do nome de exibição.

Atualizações e exportação:
- Jogos que começam no mesmo horário entram no ranking apenas quando todos os jogos daquele horário estiverem completos.
- O site mostra indicadores de ganho/perda de posição em relação ao último ranking publicado.
- Rankings não são mais exportados em CSV pelo backend. A exportação/compartilhamento de ranking é feita no frontend como PNG da área visível, com suporte a compartilhamento mobile quando o navegador disponibiliza Web Share.
- Ao criar ou editar palpites, o cache de ranking é invalidado para manter contadores e estatísticas atualizados.

## Pagamentos no Admin

- `system_admin` pode configurar Pix, listar pagamentos, aprovar, reverter aprovação e cobrar pendentes.
- `score_admin` pode listar pagamentos, aprovar, reverter aprovação e cobrar pendentes, mas não pode alterar a configuração global do Pix.
- Reverter um pagamento aprovado devolve o usuário para `submitted` quando há comprovante, ou `pending` quando não há.

---

## Integração Futura com Keycloak / OAuth2

O sistema foi preparado estruturalmente para integração com provedores de identidade externos. A tabela `users` contém os campos:
- `external_provider`: Identificador do provedor (ex: `keycloak`).
- `external_subject`: Sub (ID do usuário no Keycloak).
- `avatar_url`: Preenchido dinamicamente pelo perfil social.

Para implementar no futuro:
1. Defina `KEYCLOAK_ENABLED=true`.
2. Adicione uma biblioteca de autenticação OAuth2 no FastAPI (como `Authlib` ou use a biblioteca oficial de autenticação de tokens do Keycloak).
3. No frontend, utilize o cliente `keycloak-js` ou configure o redirecionamento OAuth2 tradicional para interceptar o fluxo de registro/login e extrair as claims (como papéis administrativos e e-mail).
4. Caso o Keycloak retorne claims de grupos, o backend poderá popular de forma correspondente a tabela `group_members` associando o usuário aos grupos automaticamente.
