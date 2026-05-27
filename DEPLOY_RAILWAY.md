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
- Painel de leads: `/leads`
- API de leads: `/api/leads`

## Opcional: publicar versao webhook Gallabox
Se quiser subir o app de webhook (`app_gallabox.py`) em outro service, use start command:
`uvicorn app_gallabox:app --host 0.0.0.0 --port $PORT`

E configure as variaveis `GALLABOX_*` conforme `.env.gallabox.example`.
