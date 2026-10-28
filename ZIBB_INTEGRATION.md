# Integração Zibb

Fluxo: WhatsApp → Zibb → `POST /webhooks/zibb` → Fernanda/OpenAI → Zibb (`v2/whatsapp/messages`) → WhatsApp.

A Gallabox continua ativa em paralelo (`/webhook/gallabox`, `/webhooks/gallabox`). As duas integrações
usam a mesma lógica da Fernanda (`generate_sdr_reply` e `finalize_lead_after_reply` em `app.py`).

## Variáveis de ambiente

| Variável | Descrição |
|---|---|
| `ZIBB_API_KEY` | Chave Bearer criada em Configurações > Desenvolvedor. |
| `ZIBB_GATEWAY_URL` | Endpoint de envio (`https://fpkfyqqbeolagvwmlxmd.supabase.co/functions/v1/chatbot-api-gateway/v2/whatsapp/messages`). |
| `ZIBB_WEBHOOK_SECRET` | Segredo HMAC exibido ao cadastrar o webhook na Zibb. |
| `ZIBB_IDEMPOTENCY_DB` | SQLite usado só para deduplicação (ex.: `/data/zibb_webhooks.db`). |

As credenciais ficam apenas no backend e não são enviadas à OpenAI.

## Comportamento do webhook

- Valida `X-Zibb-Signature: sha256=<hex>` (HMAC-SHA256 do corpo bruto); assinatura inválida → 401.
- Trata `whatsapp.inbound_message.received` com texto; outros eventos → 202 `ignored`.
- Deduplica por `message_id` (ou id do evento) antes de aceitar; reenvio → 202 `duplicate`.
- Responde 202 imediatamente e processa a Fernanda em segundo plano, uma mensagem por vez por telefone.
- Mesma regra comercial da Gallabox: a mensagem "Tenho interesse" (ou aliases de
  `GALLABOX_INTEREST_BUTTON_ALIASES`) ativa o lead e envia a saudação; depois disso a Fernanda conduz a
  qualificação. Telefones sem lead `ACTIVE` são ignorados.
- A resposta usa `from` = `to` recebido (número da empresa) e `to` = `from` recebido (cliente).

## Teste de envio (sem webhook)

```
python zibb_send_test.py <numero_da_conta_zibb> <celular_cliente> "Teste Fernanda"
```

## Teste ponta a ponta

1. Configure as variáveis no Railway e faça o deploy; `GET /health` deve retornar `{"status":"ok"}`.
2. Cadastre na Zibb o webhook `https://<dominio>/webhooks/zibb` com o evento
   `whatsapp.inbound_message.received` e copie o segredo para `ZIBB_WEBHOOK_SECRET`.
3. Do celular de teste, envie **Tenho interesse** para o número da Zibb: a Fernanda pede o CNPJ.
4. Continue a conversa; cada webhook deve aparecer com HTTP 202 nos logs da Zibb.
5. Reenvie um evento pelos logs da Zibb: deve retornar `status=duplicate` sem nova resposta.
