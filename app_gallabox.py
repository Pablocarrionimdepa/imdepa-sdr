"""
Esqueleto FastAPI para integracao com Gallabox.

Rotas:
- POST /webhooks/gallabox: recebe evento, valida assinatura e responde via Gallabox
- POST /api/gallabox/send: envio manual de mensagem
- GET /health: healthcheck
"""

import os
import uuid
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from ai_agent import get_ai_response
from cnpj_lookup import lookup_cnpj
from database import init_db, save_lead
from gallabox import GallaboxClient, GallaboxError, parse_incoming_message, verify_webhook_signature

load_dotenv()

app = FastAPI(title="Gallabox Webhook Skeleton", version="1.0.0")

conversations: dict[str, list[dict[str, str]]] = {}

SYSTEM_PROMPT = (
    "Voce e a Fernanda, assistente comercial da Imdepa, em portugues brasileiro. "
    "Responda de forma objetiva, curta, educada e conversacional. "
    "No atendimento inicial, apresente rapidamente a Imdepa antes de pedir dados. "
    "Depois, peca uma informacao por vez e nesta ordem: primeiro o CNPJ, "
    "depois seu nome, depois e-mail, depois telefone, e por fim o segmento da empresa. "
    "Se um CNPJ valido for informado e o nome da empresa for localizado em base publica, confirme o nome da empresa antes de pedir o proximo dado. "
    "Com esses cinco dados, trate o lead como qualificado. "
    "Nao peca outras informacoes antes de concluir essa sequencia."
)


@app.on_event("startup")
async def startup():
    init_db()


class GallaboxSendMessage(BaseModel):
    to: str
    message: str
    channel_id: Optional[str] = None
    recipient_name: Optional[str] = None
    conversation_id: Optional[str] = None


def get_gallabox_client() -> GallaboxClient:
    api_key = os.getenv("GALLABOX_API_KEY", "")
    api_secret = os.getenv("GALLABOX_API_SECRET", "")
    api_base_url = os.getenv("GALLABOX_API_BASE_URL", "")

    if not api_key or not api_secret:
        raise HTTPException(
            status_code=500,
            detail="Configure GALLABOX_API_KEY e GALLABOX_API_SECRET.",
        )

    try:
        return GallaboxClient(
            api_key=api_key,
            api_secret=api_secret,
            api_base_url=api_base_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def get_or_create_history(session_id: str) -> list[dict[str, str]]:
    if session_id not in conversations:
        conversations[session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    return conversations[session_id]


def run_agent_turn(session_id: str, user_message: str) -> str:
    history = get_or_create_history(session_id)
    history.append({"role": "user", "content": user_message})

    cnpj_response = handle_cnpj_lookup(session_id=session_id, user_message=user_message, history=history)
    if cnpj_response:
        return cnpj_response

    try:
        ai_response = get_ai_response(history)
    except Exception as exc:
        print(f"Erro ao gerar resposta da IA: {exc}")
        ai_response = (
            "Estou com uma instabilidade momentanea no atendimento. "
            "Pode tentar novamente em alguns instantes?"
        )

    history.append({"role": "assistant", "content": ai_response})
    return ai_response


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/gallabox/send")
async def api_gallabox_send(msg: GallaboxSendMessage):
    """Envio manual para testar credenciais/endpoint da Gallabox."""
    client = get_gallabox_client()
    try:
        result = client.send_text_message(
            to=msg.to,
            text=msg.message,
            channel_id=msg.channel_id,
            recipient_name=msg.recipient_name,
            conversation_id=msg.conversation_id,
        )
        return {"status": "sent", "provider_response": result}
    except GallaboxError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/webhooks/gallabox")
async def webhook_gallabox(request: Request):
    """
    Webhook principal:
    1) valida assinatura
    2) parseia payload
    3) gera resposta no agente
    4) envia resposta via API Gallabox
    """
    raw_body = await request.body()
    signature = request.headers.get("x-gallabox-signature", "")
    webhook_secret = os.getenv("GALLABOX_WEBHOOK_SECRET", "")

    if webhook_secret and not verify_webhook_signature(raw_body, signature, webhook_secret):
        raise HTTPException(status_code=401, detail="Assinatura de webhook invalida")

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Payload JSON invalido") from exc

    incoming = parse_incoming_message(payload)
    if not incoming:
        return {"status": "ignored", "reason": "evento sem mensagem de texto"}

    session_id = incoming.contact_id or incoming.conversation_id or incoming.from_number or str(uuid.uuid4())

    try:
        ai_response = run_agent_turn(session_id=session_id, user_message=incoming.text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar resposta da IA: {exc}") from exc

    client = get_gallabox_client()
    try:
        provider_response = client.send_text_message(
            to=incoming.from_number,
            text=ai_response,
            channel_id=incoming.channel_id,
            recipient_name=incoming.recipient_name,
            conversation_id=incoming.conversation_id,
        )
    except GallaboxError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "status": "ok",
        "session_id": session_id,
        "provider_response": provider_response,
    }


def handle_cnpj_lookup(session_id: str, user_message: str, history: list[dict[str, str]]) -> Optional[str]:
    lookup = lookup_cnpj(user_message)
    if not lookup:
        return None

    lead_info = {"cnpj": lookup["cnpj"]}
    if lookup.get("empresa"):
        lead_info["empresa"] = lookup["empresa"]
        response_text = (
            f"Localizei a empresa {lookup['empresa']}. "
            "Para dar sequencia ao seu atendimento, me informe seu nome."
        )
    else:
        response_text = (
            f"Recebi o CNPJ {lookup['formatted_cnpj']}. "
            "Nao consegui localizar o nome da empresa na base publica agora. "
            "Para seguir com seu atendimento, me informe seu nome."
        )

    save_lead(session_id, lead_info)
    history.append({"role": "assistant", "content": response_text})
    return response_text


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "9096"))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run("app_gallabox:app", host=host, port=port, reload=True)








