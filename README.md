# Bolão Copa do Mundo 2026 (Prediction Pool System)

Este projeto consiste em um sistema completo de Bolão para a Copa do Mundo FIFA 2026. A aplicação foi construída em **Português Brasileiro (PT-BR)**, oferecendo uma experiência imersiva e visualmente premium baseada no **Google Material Design**.

---

## Stack Tecnológica Utilizada

- **Backend**: Python FastAPI com SQLAlchemy ORM, Pydantic para validação, e APScheduler rodando em segundo plano.
- **Frontend**: React (Vite) integrado à biblioteca de componentes Material-UI (MUI v5) para interface responsiva, com suporte a hot-reload (HMR) e temas escuros (Dark Mode).
- **Banco de Dados**: PostgreSQL 15 rodando sob Docker Compose.
- **Background Jobs**: Agendador APScheduler interno configurado para executar a sincronização automática diária às 01:00 AM (America/Sao_Paulo).
- **Ambiente**: Orquestração completa de contêineres via Docker Compose.

---

## Pré-requisitos

Para executar o projeto localmente, é necessário ter instalado em sua máquina:
- **Docker**
- **Docker Compose**

---

## Como Executar o Projeto

1. Certifique-se de ter os arquivos `.env` e `docker-compose.yml` preenchidos na raiz do projeto (ambos já vêm pré-configurados para desenvolvimento local).
2. Na pasta raiz do projeto (`Bolao/`), execute o comando para compilar e iniciar os contêineres:
   ```bash
   docker-compose up --build -d
   ```
3. O Docker Compose iniciará três serviços:
   - **Banco de Dados**: Porta `5432` (PostgreSQL)
   - **Backend**: Porta `8000` (FastAPI + Documentação OpenAPI no endereço `http://localhost:8000/docs`)
   - **Frontend**: Porta `3000` (Interface Web do Bolão acessível em `http://localhost:3000`)

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
| `JWT_SECRET` | Chave secreta de codificação dos tokens JWT | `super_secret_jwt_key_world_cup_2026_change_me` |
| `JWT_ALGORITHM` | Algoritmo de assinatura dos tokens JWT | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Expiração da sessão do usuário (em minutos) | `1440` (24 horas) |
| `ADMIN_BOOTSTRAP_USERNAME` | Nome do usuário do primeiro administrador | `admin` |
| `ADMIN_BOOTSTRAP_EMAIL` | E-mail do usuário administrador inicial | `admin@bolao2026.com.br` |
| `ADMIN_BOOTSTRAP_PASSWORD` | Senha de login do usuário administrador | `AdminSecurePassword2026!` |
| `TEAMS_JSON_URL` | Link JSON dos times do openfootball | *(URL Raw GitHub)* |
| `STADIUMS_JSON_URL` | Link JSON dos estádios do openfootball | *(URL Raw GitHub)* |
| `MATCHES_JSON_URL` | Link JSON das partidas do openfootball | *(URL Raw GitHub)* |

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

- O sistema agenda um job em segundo plano (APScheduler) para executar diariamente às **01:00 AM (fuso America/Sao_Paulo)**.
- O job baixa a versão mais atualizada dos confrontos e compara com os registros locais.
- Se o placar de uma partida estiver marcado como **confirmado por um administrador** (`score_confirmed_by_admin = True`), a sincronização **NÃO** alterará o placar local. Em vez disso, salvará um alerta na tabela de diferenças (Diffs) exibido no menu administrativo, aguardando aprovação humana para evitar fraudes ou perdas.
- Se o placar local não estiver confirmado ou for nulo, a sincronização atualiza as informações e dispara automaticamente o **Recálculo de Notas e Classificações**.
- Quando a sincronização encontra os confrontos de mata-mata definidos (substituindo placeholders como "Winner Group A" por times reais como "Mexico"), ela atualiza o confronto e destrava os palpites dos usuários, caso a regra de bloqueio de 3 horas ainda não tenha expirado.

---

## Regras de Pontuação (Scoring System)

A nota base de cada palpite é avaliada contra o resultado regulamentar oficial de 120 minutos (tempo normal mais acréscimos e prorrogações), excluindo cobranças de pênaltis.
- **Placar Exato**: 8 pontos (ex: Palpite 2x1, Oficial 2x1).
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
2. Maior quantidade de placares exatos acertados (8 pontos).
3. Maior quantidade de resultados gerais corretos (3, 4 ou 6 pontos).
4. Maior pontuação obtida nas fases eliminatórias (Mata-mata).
5. Menor quantidade de palpites perdidos (missing predictions) em confrontos já iniciados/bloqueados.
6. Data de cadastro mais antiga no sistema.
7. Ordem alfabética do nome de exibição.

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
