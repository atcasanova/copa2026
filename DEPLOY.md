# Guia de Implantação em Produção (DEPLOY.md)

Este guia descreve o procedimento passo a passo para implantar o **Bolão da Copa do Mundo 2026** em produção atrás do **Nginx Proxy Manager (NPM)** sob um único nome de domínio (ex: `bolao.meudominio.com`).

---

## 🏗️ 1. Arquitetura em Produção

Em produção, o Nginx Proxy Manager atua como o único ponto de entrada público (portas `80` e `443`). Por motivos de segurança, **nenhuma das portas do backend, frontend ou banco de dados deve ser exposta diretamente para a internet**. A comunicação ocorre internamente através de redes virtuais do Docker.

```
                         [ Internet (Portas 80 / 443) ]
                                       │
                                       ▼
                             [ Nginx Proxy Manager ]
                                       │
                ┌──────────────────────┴──────────────────────┐
                │ (Caminho padrão /)                          │ (Caminho /api)
                ▼                                             ▼
       [ Frontend (Porta 3000) ]                     [ Backend (Porta 8000) ]
                                                              │
                                                              ▼
                                                     [ Banco PostgreSQL ]
```

---

## 🔒 2. Configurações de Segurança (.env)

No servidor de produção, copie o exemplo e configure as variáveis de forma extremamente segura:

```bash
cp .env.example .env
```

```env
# Timezone padrão para exibição
TZ=America/Sao_Paulo

# Configurações do Banco de Dados PostgreSQL (Altere as senhas!)
POSTGRES_USER=bolao_prod_user
POSTGRES_PASSWORD=UMA_SENHA_MUITO_SEGURA_E_ALEATORIA
POSTGRES_DB=bolao_db
DATABASE_URL=postgresql://bolao_prod_user:UMA_SENHA_MUITO_SEGURA_E_ALEATORIA@db:5432/bolao_db

# Configurações de Segurança do Backend
# Defina um segredo forte gerado com: openssl rand -hex 32
JWT_SECRET=SEU_JWT_SECRET_SEGURO_AQUI
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Restrinja o CORS estritamente para o seu domínio de produção
CORS_ORIGINS=https://bolao.meudominio.com

# Usuário Administrador Inicial (Bootstrap)
# DICA: Defina como 'true' na primeira execução para criar a conta e depois altere para 'false'
ENABLE_ADMIN_BOOTSTRAP=true
ADMIN_BOOTSTRAP_USERNAME=admin
ADMIN_BOOTSTRAP_EMAIL=admin@bolao2026.com.br
ADMIN_BOOTSTRAP_PASSWORD=DefinaUmaSenhaForteParaOAdmin2026!

# URLs dos arquivos do openfootball (Fontes de Dados)
TEAMS_JSON_URL=https://raw.githubusercontent.com/openfootball/worldcup.json/refs/heads/master/2026/worldcup.teams.json
STADIUMS_JSON_URL=https://raw.githubusercontent.com/openfootball/worldcup.json/refs/heads/master/2026/worldcup.stadiums.json
MATCHES_JSON_URL=https://raw.githubusercontent.com/openfootball/worldcup.json/refs/heads/master/2026/worldcup.json

# SMTP para reset de senha
SMTP_HOST=mail.example.internal
SMTP_PORT=25
SMTP_STARTTLS=false
SMTP_USERNAME=
SMTP_PASSWORD=
FROM_DOMAIN=meudominio.com
SMTP_FROM=bolao@meudominio.com
FRONTEND_URL=https://bolao.meudominio.com

# Notificações WhatsApp via API interna
WHATSAPP_NOTIFY_ENABLED=false
WHATSAPP_NOTIFY_URL=http://whatsgo-bot-1:9999/internal/v1/send
WHATSAPP_NOTIFY_TOKEN=TOKEN_INTERNO_DA_API_DE_WHATSAPP
WHATSAPP_NOTIFY_TO=120363000000000000@g.us
WHATSAPP_NOTIFY_SEND_AS=text
WHATSAPP_NOTIFY_TIMEOUT_SECONDS=5
WHATSAPP_GROUP_CHAT=https://chat.whatsapp.com/SEU_CODIGO_DE_CONVITE

# Auditoria externa dos palpites no GitHub
GITHUB_AUDIT=true
GITHUB_REPO=git@github.com:atcasanova/palpites-copa-2026-auditoria.git
GITHUB_TOKEN=TOKEN_GITHUB_COM_CONTENTS_READ_WRITE
```

---

## 🐳 3. Ajuste no docker-compose.yml de Produção

Em produção, remova ou comente a seção `ports` dos serviços `db`, `backend` e `frontend` para impedir acessos diretos via IP do host. 

Substitua a estrutura de portas no `docker-compose.yml` para expor as portas apenas localmente se necessário, ou remova-as por completo:

```yaml
services:
  db:
    # ...
    # ports: (Comente esta seção em produção)
    #   - "5432:5432"

  backend:
    # ...
    # ports: (Comente esta seção em produção)
    #   - "8000:8000"

  frontend:
    # ...
    # Defina a URL da API como relativa '/' para que o Axios use o mesmo domínio de acesso
    environment:
      - VITE_API_URL=/
    # ports: (Comente esta seção em produção)
    #   - "3000:3000"
```

> [!NOTE]
> Se o **Nginx Proxy Manager** estiver rodando no mesmo host em um arquivo Compose separado, crie uma rede compartilhada externa (ex: `docker network create proxy_network`) e adicione os containers a ela para que o NPM consiga resolver os nomes de serviço `frontend` e `backend`.

### Integração com API interna de WhatsApp

O sistema pode enviar mensagens quando pagamentos forem aprovados, quando placares forem salvos e 2h30 antes dos jogos para lembrar participantes de palpitar.

Para usar outro container como API de WhatsApp, prefira uma rede Docker compartilhada:

```yaml
services:
  backend:
    networks:
      - internal_net
      - whatsapp_net

networks:
  internal_net:
    driver: bridge
  whatsapp_net:
    external: true
    name: nome_da_rede_do_whatsapp
```

Com isso, configure:

```env
WHATSAPP_NOTIFY_ENABLED=true
WHATSAPP_NOTIFY_URL=http://nome_do_servico_whatsapp:9999/internal/v1/send
WHATSAPP_NOTIFY_TOKEN=TOKEN_INTERNO_DA_API_DE_WHATSAPP
WHATSAPP_NOTIFY_TO=ID_DO_GRUPO_OU_CONTATO@g.us
```

Se preferir usar a porta publicada no host, a API de WhatsApp precisa publicar em todas as interfaces:

```yaml
ports:
  - "9998:9999"
```

E o backend pode usar:

```env
WHATSAPP_NOTIFY_URL=http://host.docker.internal:9998/internal/v1/send
```

Não use `127.0.0.1:9998:9999` para esse caso, porque isso prende a porta ao loopback do host e pode impedir o acesso vindo de outros containers.

### Auditoria externa dos palpites no GitHub

O repositório `git@github.com:atcasanova/palpites-copa-2026-auditoria.git` deve ser usado apenas para registrar os blocos de auditoria dos palpites. O backend publica os arquivos via API do GitHub, então o container não precisa ter chave SSH nem cliente `git`; ele precisa apenas das variáveis `GITHUB_*` no ambiente.

Requisitos:
- `GITHUB_AUDIT=true` para habilitar a publicação.
- `GITHUB_REPO=git@github.com:atcasanova/palpites-copa-2026-auditoria.git`.
- `GITHUB_TOKEN` com permissão de leitura/escrita em **Contents** no repositório alvo.

Cada bloco será salvo em `blocks/block_XXXXXX_match_YY.json` com payload dos palpites, hash anterior, hash atual e metadados da partida. Se a publicação falhar, o sistema mantém o bloco local e registra o erro nos logs do backend.

---

## 🛠️ 4. Configuração no Nginx Proxy Manager

Acesse o painel do seu Nginx Proxy Manager e adicione um novo **Proxy Host**:

### Aba "Details"
1. **Domain Names**: `bolao.meudominio.com` (o domínio que você apontou para o servidor).
2. **Scheme**: `http`
3. **Forward Host / IP**: `frontend` (ou o IP local do servidor host do docker).
4. **Forward Port**: `3000`
5. Marque **Block Common Exploits**.
6. Marque **Websockets Support** (permite conexões persistentes necessárias).

### Aba "Custom Locations"
Precisamos criar regras específicas para direcionar as requisições de API e documentação para o container do backend. Adicione as seguintes localizações:

1. **Localização 1 (API)**:
   * **Define Location**: `/api`
   * **Scheme**: `http`
   * **Forward Host / IP**: `backend` (ou o IP local do servidor).
   * **Forward Port**: `8000`

2. **Localização 2 (Swagger Docs - Opcional)**:
   * **Define Location**: `/docs`
   * **Scheme**: `http`
   * **Forward Host / IP**: `backend` (ou o IP local do servidor).
   * **Forward Port**: `8000`

3. **Localização 3 (OpenAPI Schema - Opcional)**:
   * **Define Location**: `/openapi.json`
   * **Scheme**: `http`
   * **Forward Host / IP**: `backend` (ou o IP local do servidor).
   * **Forward Port**: `8000`

### Aba "SSL"
1. Selecione **Request a new SSL Certificate** (Let's Encrypt).
2. Marque **Force SSL** (força redirecionamento HTTP para HTTPS).
3. Insira o e-mail de recuperação e concorde com os termos do Let's Encrypt.
4. Clique em **Save**.

---

## 🚀 5. Inicialização do Sistema

Com os arquivos `.env` e `docker-compose.yml` ajustados, execute os seguintes comandos no seu terminal de produção:

1. Realize o build e suba a aplicação em segundo plano:
   ```bash
   docker compose up -d --build
   ```

2. Acompanhe a inicialização e certifique-se de que o seeder importou os dados e o administrador foi criado com sucesso:
   ```bash
   docker compose logs -f backend
   ```

3. Assim que confirmar que o administrador padrão foi criado na primeira inicialização, mude a variável no `.env` para desativar novos bootstraps (opcional, por segurança):
   ```env
   ENABLE_ADMIN_BOOTSTRAP=false
   ```
   E aplique a alteração reiniciando o serviço:
   ```bash
   docker compose up -d
   ```

4. Confirme se as notificações estão configuradas dentro do backend:
   ```bash
   docker compose exec backend python -c "import os; print(os.getenv('WHATSAPP_NOTIFY_ENABLED')); print(os.getenv('WHATSAPP_NOTIFY_URL'))"
   ```

5. Confirme se a auditoria GitHub está configurada, sem imprimir o token:
   ```bash
   docker compose exec backend python -c "import os; print(os.getenv('GITHUB_AUDIT')); print(os.getenv('GITHUB_REPO'))"
   ```

Pronto! Seu sistema de bolão está seguro, com certificados SSL ativos e rodando sob um único domínio através do Nginx Proxy Manager.
