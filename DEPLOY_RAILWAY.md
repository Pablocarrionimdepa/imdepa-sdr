# Deploy no Railway (FastAPI)

## 1) Subir o codigo para GitHub
O Railway faz deploy automatico a partir do repositorio.

## 2) Criar projeto no Railway
1. Acesse Railway e clique em `New Project`.
2. Escolha `Deploy from GitHub repo`.
3. Selecione este repositorio.

## 3) Configurar variaveis de ambiente
No service criado, abra `Variables` e cadastre:
- `OPENAI_API_KEY` (obrigatoria)
- `OPENAI_MODEL` (opcional, default: `gpt-4.1-mini`)
- `DB_PATH` (recomendado: `/data/leads.db`)

O `PORT` e injetado automaticamente pelo Railway.

## 4) Configurar volume persistente (recomendado para SQLite)
Para nao perder os leads a cada redeploy:
1. No service, abra `Settings` > `Volumes`.
2. Crie um volume e monte em `/data`.
3. Garanta `DB_PATH=/data/leads.db` nas variaveis.

## 5) Start command
Ja configurado em `railway.json`:
`uvicorn app:app --host 0.0.0.0 --port $PORT`

## 6) Deploy
Cada push na branch conectada gera novo deploy automaticamente.

## 7) Verificacao
- URL principal: `/`
- Healthcheck: `/health`
- Painel de leads: `/leads`
- API de leads: `/api/leads`

## 8) Endpoints para Gallabox
Dominio publico do service:

- `GET https://imdepa-sdr-production.up.railway.app/health`
- `POST https://imdepa-sdr-production.up.railway.app/start`
- `POST https://imdepa-sdr-production.up.railway.app/webhook/start`
- `POST https://imdepa-sdr-production.up.railway.app/webhook/gallabox`

Payload esperado em `POST /start`:

```json
{
  "name": "Nome do lead",
  "phone": "5511999999999",
  "channel_id": "id-do-canal-gallabox"
}
```

Use `POST /webhook/start` no bloco API Call da Gallabox quando quiser ativar o lead antes da conversa. Ele aceita `phone` e `channel_id` no payload, e tambem tenta ler formatos comuns como `contact.phone`, `data.contact.phone`, `message.contact.phone` e `message.channelId`.

Ao receber `POST /webhook/start`, o app ativa o lead e tenta enviar a primeira pergunta da Fernanda pela Gallabox. Se nao houver credenciais/API configuradas, a ativacao ainda ocorre e o log informa que o envio nao esta configurado.

O `POST /webhook/gallabox` registra o body recebido no log da aplicacao e so processa mensagens de leads com status `ACTIVE`. Quando a qualificacao termina, o status muda para `INACTIVE`.

Durante a qualificacao, cada mensagem do cliente e cada resposta da IA sao gravadas individualmente. A equipe comercial pode consultar o historico completo no painel de leads ou pela API:

- `GET https://imdepa-sdr-production.up.railway.app/api/leads/{session_id}/history`

Diagnostico seguro da integracao Gallabox:

- `GET https://imdepa-sdr-production.up.railway.app/api/debug/gallabox-status`

Quando a qualificacao termina, o app salva um resumo final em `qualification_summary`, muda o lead para `INACTIVE` e bloqueia novas mensagens desse telefone no bot.

Para encerrar a conversa na Gallabox via API, configure o path correto fornecido pela Gallabox. A documentacao oficial usa o conceito de conversa `Resolved`, e o suporte/FAQ informa que a conversa precisa estar atribuida ao usuario/agente correto para ser resolvida.

```ini
GALLABOX_RESOLVE_CONVERSATION_PATH=/devapi/accounts/{account_id}/CAMINHO-DE-RESOLVE
GALLABOX_RESOLVE_CONVERSATION_METHOD=POST
GALLABOX_ACCOUNT_ID=seu-account-id
```

Placeholders aceitos em `GALLABOX_RESOLVE_CONVERSATION_PATH`: `{account_id}`, `{conversation_id}`, `{phone}` e `{channel_id}`.

Se o endpoint exigir body especifico, configure tambem:

```ini
GALLABOX_RESOLVE_CONVERSATION_BODY={"phone":"{phone}","channelId":"{channel_id}","status":"RESOLVED"}
```

Se essas variaveis nao estiverem configuradas, o app apenas finaliza internamente o lead e registra o resumo. O envio da ultima resposta ao cliente continua funcionando normalmente.

### Validacao temporaria da assinatura Gallabox
Para confirmar o fluxo completo enquanto a secret e ajustada, configure temporariamente no Railway:

```ini
GALLABOX_SKIP_SIGNATURE_VALIDATION=true
```

Com essa variavel ligada, o app aceita o webhook mesmo que `x-gallabox-signature` nao bata. Depois do teste, remova a variavel ou altere para `false` e garanta que `GALLABOX_WEBHOOK_SECRET` seja exatamente a mesma secret configurada no webhook da Gallabox.

## Opcional: publicar versao webhook Gallabox
Se quiser subir o app de webhook (`app_gallabox.py`) em outro service, use start command:
`uvicorn app_gallabox:app --host 0.0.0.0 --port $PORT`

E configure as variaveis `GALLABOX_*` conforme `.env.gallabox.example`.
