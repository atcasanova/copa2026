# AI Agent Operating Notes

Este arquivo registra as particularidades do projeto que devem ser preservadas por qualquer agente de IA ou pessoa que altere o codigo. Quando houver conflito entre este arquivo e uma ideia de implementacao, pare e verifique a regra de negocio antes de mudar o comportamento.

## Visao Geral

- Aplicacao de bolao da Copa 2026 com backend FastAPI/SQLAlchemy, frontend React/Vite/MUI e PostgreSQL.
- Idioma da interface e mensagens: portugues brasileiro.
- Horarios internos de partidas e jobs devem ser tratados como UTC no backend. Horarios exibidos para usuarios/admin devem usar `America/Sao_Paulo`, salvo quando a UI tiver timezone do usuario explicitamente disponivel.
- Nao ha Alembic configurado. O projeto usa `Base.metadata.create_all(bind=engine)` no startup e alguns `ALTER TABLE` manuais em `backend/app/main.py`. Ao adicionar tabelas novas, preferir modelos SQLAlchemy com `create_all`. Ao adicionar colunas a tabelas existentes, seguir o padrao manual existente.
- O workspace pode ter mudancas pendentes de outros agentes/usuarios. Nao reverta arquivos fora do escopo da tarefa.

## Comandos de Validacao

Use os containers em vez de depender de ferramentas instaladas no host.

- Backend, testes focados:
  - `docker exec bolao_backend pytest app/tests/test_football_data.py`
  - `docker exec bolao_backend pytest app/tests/test_notifications.py`
  - `docker exec bolao_backend pytest app/tests/test_core.py`
- Frontend build:
  - `docker exec bolao_frontend npm run build`
- Health backend:
  - `curl -s http://127.0.0.1:3998/`

Ao alterar backend em execucao, reinicie `bolao_backend`. Ao alterar frontend, reinicie `bolao_frontend`.

## Football-data.org e Rate Limit

Arquivo principal: `backend/app/football_data.py`.

Regras que nao devem ser relaxadas sem decisao explicita:

- O job automatico roda a cada 1 minuto em `backend/app/scheduler.py`.
- O job so considera partidas sem placar a partir de `POLL_AFTER_HOURS = 2` horas apos o kickoff.
- A tolerancia de casamento por horario com a API e `KICKOFF_TOLERANCE_MINUTES = 20`.
- O limite de chamadas HTTP por execucao e controlado por `FOOTBALL_DATA_MAX_REQUESTS_PER_RUN`, default `8`. Nao aumente esse default nem crie loops que ignorem `_max_requests_per_run()`.
- O token vem de `FOOTBALL_DATA_API` ou `FOOTBALL_DATA_API_KEY`.
- A competicao default e `FOOTBALL_DATA_COMPETITION=WC`.
- Cada chamada consulta uma janela `dateFrom/dateTo` de um dia antes ate um dia depois do kickoff candidato.
- Respostas sao cacheadas por janela dentro da mesma execucao para evitar chamadas duplicadas.
- A aplicacao so aplica placares quando todos os jogos locais do mesmo horario tiverem correspondencia valida e finalizada no retorno da API.
- Se qualquer jogo do mesmo horario estiver ausente, em andamento, com status inesperado ou placar incompleto, nenhum placar daquele horario deve ser aplicado.
- Para partidas com prorrogacao, usar `score.regularTime` quando a duracao nao for `REGULAR`; para partidas normais, usar `score.fullTime`.
- O casamento de times deve continuar tolerante a acentos, caixa, pontuacao e nomes traduzidos via `translate_team_name`.

Logs da sincronizacao:

- Cada execucao manual deve criar um registro em `football_data_sync_logs` via `FootballDataSyncLog`.
- Execucoes agendadas sem horarios candidatos (partidas pendentes a partir de 2h apos kickoff) nao devem criar log para evitar armazenamento a cada minuto sem jogos a consultar.
- Execucoes agendadas com horarios candidatos devem criar log, mesmo quando nenhum placar for aplicado.
- O endpoint admin de leitura e `GET /api/admin/football-data/logs`.
- Logs devem registrar, no minimo: trigger (`manual` ou `scheduled`), status, horarios candidatos, chamadas feitas, quantidade de partidas retornadas, checagens por partida, placares aplicados e erros.
- A aba admin de Sincronizacao faz polling desses logs enquanto aberta. Nao remova sem substituir por visibilidade equivalente.

## Regras de Ranking

Arquivos principais: `backend/app/scoring.py`, `backend/app/routers/admin.py`, `backend/app/football_data.py`, `frontend/src/pages/Rankings.jsx`.

Regras intocaveis sem decisao de produto:

- O ranking so deve considerar jogos cujo grupo de mesmo kickoff esteja completo.
- Um kickoff e rankeavel apenas quando todas as partidas daquele horario, exceto `postponed`/`cancelled`, tiverem status final em `RANKING_FINAL_STATUSES` e placar preenchido.
- `RANKING_FINAL_STATUSES` atualmente inclui `finished`, `score_confirmed` e `score_pending_review`.
- Se houver mais de um jogo no mesmo horario, nao publique ranking apos o primeiro placar isolado. Aguarde todos os jogos daquele horario.
- A mensagem de WhatsApp de ranking segue a mesma regra: so enviar quando o grupo de kickoff estiver completo.
- O ranking geral deve incluir indicadores de movimento em relacao ao ultimo ranking publicado:
  - `position_change > 0`: ganhou posicoes.
  - `position_change < 0`: perdeu posicoes.
  - `None` ou `0`: nao mostrar indicador.
- Snapshots de movimento ficam em `ranking_update_snapshots` e sao criados por `capture_ranking_update_snapshot()`.
- Snapshots diarios antigos em `ranking_snapshots` continuam existindo para historico/grafico diario. Nao misture os dois conceitos.
- Depois de salvar `RankingUpdateSnapshot`, invalidar cache de ranking para que os indicadores aparecam corretamente.
- Ao criar ou editar palpites, invalidar `RankingCache`; mesmo sem pontuacao nova, campos como `predictions_count` e `missing_predictions_count` precisam refletir a interacao recente.
- Nao reintroduzir exportacao CSV de rankings. Rankings devem ser compartilhados/exportados no cliente como PNG da area visivel, sem endpoint backend dedicado.

Tie-breakers oficiais do ranking, nesta ordem:

1. Maior total de pontos.
2. Maior quantidade de placares exatos.
3. Maior quantidade de resultados corretos.
4. Maior pontuacao no mata-mata.
5. Menor quantidade de palpites faltantes em jogos rankeaveis.
6. Cadastro mais antigo.
7. Nome de exibicao em ordem alfabetica.

## Notificacoes WhatsApp

Arquivo principal: `backend/app/notifications.py`.

Configuracao:

- Envio so ocorre se `WHATSAPP_NOTIFY_ENABLED=true` ou fallback legado `PAYMENT_APPROVAL_NOTIFY_ENABLED=true`.
- Endpoint/token/destino usam `WHATSAPP_NOTIFY_URL`, `WHATSAPP_NOTIFY_TOKEN`, `WHATSAPP_NOTIFY_TO`.
- O link de convite exibido ao usuario vem de `WHATSAPP_GROUP_CHAT`.

Situacoes em que mensagens sao enviadas ao grupo:

- Aprovacao de pagamento:
  - `send_payment_approval_notification()`.
  - Mensagem informa pagamento aprovado e resumo da premiacao calculada pelo total arrecadado.
- Cobranca manual de pagamentos pendentes:
  - Endpoint `POST /api/payments/admin/charge-debtors`.
  - Envia uma mensagem com participantes nao aprovados e depois envia o Pix copia e cola.
  - Nao incluir `system_admin` nem `score_admin` na lista de devedores.
- Lembrete de palpites:
  - `send_due_prediction_reminders()`.
  - Roda a cada 5 minutos pelo scheduler.
  - Envia 2h30 antes do kickoff (`REMINDER_LEAD_MINUTES = 150`) dentro de janela de 5 minutos.
  - Envia no maximo uma vez por kickoff usando `SystemSetting` com chave `whatsapp_reminder_sent:<kickoff_iso>`.
  - Mensagem lista todos os jogos daquele horario e inclui `Nao palpitaram: N` por jogo.
  - A contagem considera usuarios ativos que nao sao `system_admin` nem `score_admin`.
- Ranking atualizado:
  - `send_general_ranking_notification()`.
  - Enviar somente quando a regra de ranking por kickoff completo permitir publicacao.
  - Mensagem mostra Top 10 geral.
  - Indicadores de movimento usam emojis: subida `🟢⬆️N`, queda `🔴⬇️N`, sem mudanca nao mostra nada.

Nao adicionar novos disparos de WhatsApp sem registrar aqui e cobrir com teste.

## Pagamentos

Arquivos principais: `backend/app/routers/payments.py`, `frontend/src/pages/AdminPanel.jsx`, `frontend/src/components/Layout.jsx`.

- Participantes sem `payment_status == "approved"` nao podem dar palpites.
- O aviso global para usuarios nao aprovados deve permanecer sempre visivel no topo, com links para Meu Perfil e para o grupo de WhatsApp.
- Admin pode aprovar pagamento e tambem reverter aprovacao.
- `score_admin` tambem pode acessar a aba Pagamentos para listar/aprovar/reverter/cobrar, mas nao pode editar a configuracao global do Pix.
- Reverter aprovacao deve voltar para `submitted` se houver comprovante, senao `pending`.
- A listagem admin de pagamentos/usuarios deve ordenar nomes ignorando acentos e caixa.
- Na aba Pagamentos em mobile:
  - ocultar coluna Chave Pix;
  - status por icones;
  - comprovante por icone;
  - aprovar/reverter por icones;
  - nao reintroduzir acao de recusar sem decisao explicita.

## Palpites, Timezone e Visibilidade

Arquivos principais: `backend/app/routers/predictions.py`, `frontend/src/pages/Predictions.jsx`.

- Datas vindas da API sem timezone devem ser tratadas como UTC no frontend antes de exibir/comparar.
- A lista "Participantes que ja palpitaram" deve mostrar titulo no formato `Participantes que ja palpitaram (x/y)`.
- `x` = usuarios ativos nao admin que palpitaram naquele jogo.
- `y` = total de usuarios ativos nao admin.
- A funcionalidade antiga de importar palpites via JSON foi removida e nao deve ser reintroduzida sem decisao explicita.

## Admin e Sincronizacao Legada

- A aba Sincronizacao tem dois conceitos separados:
  - football-data.org: fluxo principal de resultados oficiais e logs em tempo real.
  - openfootball legado: seed inicial e compatibilidade/auditoria.
- O job diario openfootball so deve ser agendado quando `OPENFOOTBALL_DAILY_SYNC_ENABLED=true`.
- Diffs legados pendentes existem para nao sobrescrever placares confirmados por admin sem revisao humana.
- Nao misture logs do football-data com `sync_logs`/`sync_match_diffs`; eles tem finalidades diferentes.

## Frontend

- UI em PT-BR.
- Usar MUI e padroes existentes.
- Layouts administrativos devem ser responsivos, densos e operacionais, sem cara de landing page.
- Nao usar `window.confirm` para confirmacoes administrativas sensiveis; preferir Dialog/Modal MUI.
- Para icones, preferir `@mui/icons-material` ja usado no app.
- Exportacoes visuais de ranking devem ser processadas no navegador. O componente atual e `frontend/src/components/ExportElementImageButton.jsx`.

## Performance Preservada

- `get_unlocked_stages()` deve consultar partidas em lote e agrupar em memoria; nao voltar a fazer uma query por fase.
- Em `bulk_save_predictions`, calcular fases desbloqueadas uma vez por requisicao, nao uma vez por palpite.
- Recálculos de pontuacao devem carregar `StageMultiplier` uma vez em dicionario e repassar para `score_prediction()`.
- A otimizacao ampla de `get_rankings()` ainda esta pendente; ao faze-la, preservar kickoff completo, tie-breakers e indicadores de movimento.

## Testes Minimos por Area

- Football-data/ranking por kickoff:
  - `docker exec bolao_backend pytest app/tests/test_football_data.py`
  - testes relevantes tambem em `app/tests/test_core.py`.
- WhatsApp/notificacoes:
  - `docker exec bolao_backend pytest app/tests/test_notifications.py`
- Pagamentos:
  - `docker exec bolao_backend pytest app/tests/test_payments.py`
- Frontend:
  - `docker exec bolao_frontend npm run build`

Sempre que alterar uma constraint deste arquivo, atualize o arquivo e os testes no mesmo patch.
