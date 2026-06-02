"""
Imdepa SDR Agent - Fernanda
Aplicacao principal FastAPI
"""

import os
import uuid
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from ai_agent import extract_lead_info, get_ai_response
from cnpj_lookup import lookup_cnpj
from database import (
    create_active_lead,
    get_all_leads,
    get_lead_by_phone,
    get_lead_by_session,
    init_db,
    is_qualified_lead_data,
    save_lead,
    set_lead_status,
)
from gallabox import GallaboxClient, GallaboxError, parse_incoming_message, verify_webhook_signature

load_dotenv()

app = FastAPI(title="Imdepa SDR Agent - Fernanda", version="1.0.0")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.on_event("startup")
async def startup():
    init_db()


class ChatMessage(BaseModel):
    session_id: Optional[str] = None
    message: str


class ChatResponse(BaseModel):
    session_id: str
    response: str
    lead_data: Optional[dict] = None


class GallaboxSendMessage(BaseModel):
    to: str
    message: str
    channel_id: Optional[str] = None
    recipient_name: Optional[str] = None
    conversation_id: Optional[str] = None


class StartLeadRequest(BaseModel):
    name: str
    phone: str
    channel_id: str


conversations: dict[str, list[dict[str, str]]] = {}

SYSTEM_PROMPT = """Voce e a Fernanda, assistente comercial virtual da Imdepa. Voce e simpatica, profissional e objetiva.

## Sobre a Imdepa
A Imdepa e uma empresa brasileira com mais de 65 anos de historia, consolidada como uma das maiores e mais respeitadas distribuidoras de pecas do pais. Fundada em Caxias do Sul (RS), atua em todo o territorio nacional.

### Portfolio (mais de 23.000 itens):
- Rolamentos, Mancais, Retentores, Correias, Correntes, Embreagens
- Esteiras Draper, Mangueiras e Terminais Hidraulicos, Molas Pneumaticas
- Graxas e Lubrificantes

### Marcas distribuidas:
SKF, Timken, Sabo, Continental, Eaton, Firestone, Grupo Schaeffler (INA, FAG, LUK).
Marca propria: GTOP-GBR (otima relacao custo-beneficio).

### Segmentos de mercado:
1. Agricola - componentes para maquinas e implementos agricolas
2. Industrial - mineracao, siderurgia, usinas de acucar e alcool, etc.
3. Automotivo - pecas para veiculos leves e pesados

### Diferenciais:
- Mais de 65 anos de experiencia e tradicao
- 10 Centros de Distribuicao em 8 estados (logistica agil nacional)
- Certificacao ISO 9001:2015 e selo OEA da Receita Federal
- Suporte tecnico especializado com engenheiros
- Plataforma E-commerce B2B (loja.imdepa.com.br) com cashback, Clube Imdepa, pedido minimo R$400
- Marca propria GTOP-GBR com preco competitivo

## Seu Objetivo
Voce deve conduzir uma conversa natural e amigavel com potenciais clientes (leads), seguindo o roteiro de SDR. Seu objetivo e:
1. Apresentar brevemente a Imdepa
2. Conduzir o atendimento inicial do lead
3. Coletar informacoes complementares, se fizer sentido
4. Apresentar solucoes conectando com os diferenciais da Imdepa

## Fluxo inicial do atendimento (faca em sequencia, com 1 pergunta por vez):
1. Peca apenas o CNPJ da empresa
2. Depois de receber o CNPJ, peca seu nome
3. Depois, peca o e-mail para contato
4. Em seguida, peca o telefone para contato
5. Por fim, peca o segmento da empresa

Se um CNPJ valido for informado e o nome da empresa for localizado em base publica, confirme o nome da empresa antes de pedir o proximo dado.
Apresente a Imdepa de forma breve antes de iniciar a coleta e mantenha o tom conversacional durante todo o atendimento.
Com CNPJ, seu nome, e-mail, telefone e segmento, o lead ja deve ser tratado como qualificado.
Nao transforme isso em formulario: conduza de forma natural, mas respeite essa ordem.
Nao peca outras informacoes antes de concluir essa sequencia.

## Informacoes opcionais (somente depois do atendimento inicial, se fizer sentido):
- Nome da empresa
- Principais produtos de interesse
- Dores e necessidades
- Decisor(es) de compra

## Regras de conduta:
- Sempre fale em portugues brasileiro
- Seja amigavel mas profissional
- Faca no maximo 1 pergunta objetiva por resposta
- Adapte a conversa conforme as respostas do cliente
- Se o cliente reclamar de prazo, destaque os 10 CDs da Imdepa
- Se buscar preco, apresente a marca GTOP-GBR
- Para revendas, mencione o e-commerce B2B com cashback e Clube Imdepa
- Ao final, proponha agendar uma conversa com um consultor comercial
- Nunca invente informacoes que nao estejam no contexto acima
- Priorize frases curtas, linguagem simples e sem repetir informacoes ja ditas
- Responda de forma curta e direta: 1 paragrafo curto ou ate 3 frases
- Use emojis com moderacao (maximo 1-2 por mensagem)

## Inicio da conversa:
Na primeira mensagem, apresente-se, apresente brevemente a Imdepa e depois solicite apenas o CNPJ. Exemplo:
"Ola! Eu sou a Fernanda, assistente comercial da Imdepa. Somos uma das maiores distribuidoras de pecas do Brasil e atendemos clientes em todo o pais. Para iniciar seu atendimento, me informe o CNPJ da empresa."""


def get_conversation(session_id: str) -> list[dict[str, str]]:
    if session_id not in conversations:
        conversations[session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    return conversations[session_id]


def get_initial_message() -> str:
    return (
        "Ola! Eu sou a Fernanda, assistente comercial da Imdepa. Somos uma das maiores "
        "distribuidoras de pecas do Brasil e atendemos clientes em todo o pais. "
        "Para iniciar seu atendimento, me informe o CNPJ da empresa."
    )


def is_gallabox_send_configured(channel_id: Optional[str]) -> bool:
    return bool(
        os.getenv("GALLABOX_API_KEY", "").strip()
        and os.getenv("GALLABOX_API_SECRET", "").strip()
        and os.getenv("GALLABOX_API_BASE_URL", "").strip()
        and (channel_id or os.getenv("GALLABOX_CHANNEL_ID", "").strip())
    )


def should_skip_gallabox_signature_validation() -> bool:
    return os.getenv("GALLABOX_SKIP_SIGNATURE_VALIDATION", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


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


@app.get("/", response_class=HTMLResponse)
async def chat_page(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})


@app.get("/leads", response_class=HTMLResponse)
async def leads_page(request: Request):
    return templates.TemplateResponse("leads.html", {"request": request})


@app.post("/api/chat", response_model=ChatResponse)
async def chat(msg: ChatMessage):
    session_id = msg.session_id or str(uuid.uuid4())
    history = get_conversation(session_id)
    history.append({"role": "user", "content": msg.message})

    cnpj_response = handle_cnpj_lookup(session_id=session_id, user_message=msg.message, history=history)
    if cnpj_response:
        return cnpj_response

    try:
        ai_response = get_ai_response(history)
    except Exception as exc:
        print(f"Erro ao comunicar com a IA: {exc}")
        ai_response = (
            "Estou com uma instabilidade momentanea no atendimento. "
            "Pode tentar novamente em alguns instantes?"
        )

    history.append({"role": "assistant", "content": ai_response})

    try:
        lead_info = extract_lead_info(history)
        if lead_info and any(v for v in lead_info.values() if v):
            save_lead(session_id, lead_info)
    except Exception:
        lead_info = None

    return ChatResponse(session_id=session_id, response=ai_response, lead_data=lead_info)


@app.post("/api/chat/start")
async def chat_start():
    session_id = str(uuid.uuid4())
    history = get_conversation(session_id)

    initial_message = get_initial_message()

    history.append({"role": "assistant", "content": initial_message})

    return {"session_id": session_id, "response": initial_message}


@app.get("/api/leads")
async def api_get_leads():
    return {"leads": get_all_leads()}


@app.get("/api/leads/{session_id}")
async def api_get_lead(session_id: str):
    lead = get_lead_by_session(session_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead nao encontrado")
    return {"lead": lead}


@app.delete("/api/leads/{lead_id}")
async def api_delete_lead(lead_id: int):
    from database import delete_lead

    success = delete_lead(lead_id)
    if not success:
        raise HTTPException(status_code=404, detail="Lead nao encontrado")
    return {"message": "Lead excluido com sucesso"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/start")
async def start_lead(payload: StartLeadRequest):
    lead = activate_lead(
        name=payload.name,
        phone=payload.phone,
        channel_id=payload.channel_id,
    )

    return {
        "status": "ACTIVE",
        "session_id": lead["session_id"],
        "lead": lead,
    }


@app.post("/webhook/start")
async def webhook_start(request: Request):
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Payload JSON invalido") from exc

    print(f"Gallabox start webhook body: {payload}")

    fields = extract_start_payload(payload)
    lead = activate_lead(
        name=fields.get("name", ""),
        phone=fields.get("phone", ""),
        channel_id=fields.get("channel_id", ""),
    )

    return {
        "status": "ACTIVE",
        "session_id": lead["session_id"],
        "lead": lead,
    }


def activate_lead(name: str, phone: str, channel_id: str) -> dict:
    name = name.strip()
    phone = phone.strip()
    channel_id = channel_id.strip()

    if not phone or not channel_id:
        raise HTTPException(status_code=422, detail="phone e channel_id sao obrigatorios.")

    if not name:
        name = phone

    try:
        lead = create_active_lead(name=name, phone=phone, channel_id=channel_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    history = get_conversation(lead["session_id"])
    if len(history) == 1:
        history.append({"role": "assistant", "content": get_initial_message()})

    return lead


def extract_start_payload(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "name": _first_payload_value(
            payload,
            (
                "name",
                "customer_name",
                "contact_name",
                "recipient_name",
                "contact.name",
                "customer.name",
                "recipient.name",
                "data.name",
                "data.contact.name",
                "data.customer.name",
                "message.contact.name",
            ),
        ),
        "phone": _first_payload_value(
            payload,
            (
                "phone",
                "mobile",
                "from",
                "from_number",
                "contact.phone",
                "contact.mobile",
                "customer.phone",
                "recipient.phone",
                "data.phone",
                "data.mobile",
                "data.from",
                "data.contact.phone",
                "data.contact.mobile",
                "message.phone",
                "message.from",
                "message.from_number",
                "message.contact.phone",
                "message.whatsapp.from",
            ),
        ),
        "channel_id": _first_payload_value(
            payload,
            (
                "channel_id",
                "channelId",
                "channel.id",
                "data.channel_id",
                "data.channelId",
                "data.channel.id",
                "message.channel_id",
                "message.channelId",
                "message.channel.id",
            ),
        )
        or os.getenv("GALLABOX_CHANNEL_ID", ""),
    }


def _first_payload_value(payload: dict[str, Any], paths: tuple[str, ...]) -> str:
    for path in paths:
        value = _payload_value(payload, path)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _payload_value(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


@app.post("/api/gallabox/send")
async def api_gallabox_send(msg: GallaboxSendMessage):
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


@app.post("/webhook/gallabox")
async def webhook_gallabox(request: Request):
    return await handle_gallabox_webhook(request)


@app.post("/webhooks/gallabox")
async def webhook_gallabox_legacy(request: Request):
    return await handle_gallabox_webhook(request)


async def handle_gallabox_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("x-gallabox-signature", "")
    webhook_secret = os.getenv("GALLABOX_WEBHOOK_SECRET", "")

    if should_skip_gallabox_signature_validation():
        print("Gallabox webhook signature validation skipped by GALLABOX_SKIP_SIGNATURE_VALIDATION.")
    elif webhook_secret:
        is_valid_signature = verify_webhook_signature(raw_body, signature, webhook_secret)
        if not is_valid_signature:
            print(
                "Gallabox webhook invalid signature: "
                f"signature_present={bool(signature)}, "
                f"body_bytes={len(raw_body)}, "
                f"secret_configured={bool(webhook_secret)}"
            )
            raise HTTPException(status_code=401, detail="Assinatura de webhook invalida")
    else:
        print("Gallabox webhook signature validation disabled because GALLABOX_WEBHOOK_SECRET is empty.")

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Payload JSON invalido") from exc

    print("=== WEBHOOK RECEBIDO ===")
    print(payload)
    print(f"Gallabox webhook body: {payload}")

    incoming = parse_incoming_message(payload)
    if not incoming:
        return {"status": "ignored", "reason": "evento sem mensagem de texto"}

    lead = get_lead_by_phone(incoming.from_number)
    if not lead:
        return {"status": "ignored", "reason": "lead nao encontrado pelo telefone"}
    if lead["status"] != "ACTIVE":
        return {"status": "ignored", "reason": "lead inativo", "lead_status": lead["status"]}

    session_id = lead["session_id"]
    history = get_conversation(session_id)
    history.append({"role": "user", "content": incoming.text})

    cnpj_response = handle_cnpj_lookup(session_id=session_id, user_message=incoming.text, history=history)
    if cnpj_response:
        ai_response = cnpj_response.response
    else:
        try:
            ai_response = get_ai_response(history)
        except Exception as exc:
            print(f"Erro ao gerar resposta da IA: {exc}")
            ai_response = (
                "Estou com uma instabilidade momentanea no atendimento. "
                "Pode tentar novamente em alguns instantes?"
            )
        history.append({"role": "assistant", "content": ai_response})

    try:
        lead_info = extract_lead_info(history)
        if lead_info and any(v for v in lead_info.values() if v):
            save_lead(session_id, lead_info)
    except Exception:
        lead_info = None

    updated_lead = get_lead_by_session(session_id)
    if is_qualified_lead_data(updated_lead):
        set_lead_status(session_id, "INACTIVE")
        if updated_lead:
            updated_lead["status"] = "INACTIVE"

    provider_response = None
    channel_id = incoming.channel_id or lead.get("channel_id")
    if is_gallabox_send_configured(channel_id):
        client = get_gallabox_client()
        try:
            provider_response = client.send_text_message(
                to=incoming.from_number,
                text=ai_response,
                channel_id=channel_id,
                recipient_name=incoming.recipient_name,
                conversation_id=incoming.conversation_id,
            )
        except GallaboxError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    else:
        print(f"Gallabox send not configured. Bot response: {ai_response}")

    return {
        "status": "ok",
        "session_id": session_id,
        "response": ai_response,
        "lead_status": updated_lead["status"] if updated_lead else lead["status"],
        "provider_response": provider_response,
    }


def handle_cnpj_lookup(session_id: str, user_message: str, history: list[dict[str, str]]) -> Optional[ChatResponse]:
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
    return ChatResponse(session_id=session_id, response=response_text, lead_data=lead_info)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 9095))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run("app:app", host=host, port=port, reload=True)








