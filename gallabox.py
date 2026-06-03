"""
Integracao base com Gallabox:
- validacao de assinatura de webhook (HMAC SHA-256)
- envio de mensagens de texto via API
"""

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from typing import Any, Optional
from urllib import error, request
from urllib.parse import quote


class GallaboxError(Exception):
    """Erro generico de integracao Gallabox."""


def verify_webhook_signature(raw_body: bytes, signature_header: str, secret: str) -> bool:
    """
    Valida assinatura HMAC SHA-256 enviada no header x-gallabox-signature.
    Aceita formatos:
    - "<hex>"
    - "sha256=<hex>"
    """
    if not secret or not signature_header:
        return False

    provided = signature_header.strip()
    if provided.lower().startswith("sha256="):
        provided = provided.split("=", 1)[1].strip()

    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)


@dataclass
class IncomingMessage:
    text: str
    from_number: str
    channel_id: Optional[str] = None
    recipient_name: Optional[str] = None
    contact_id: Optional[str] = None
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    event_type: Optional[str] = None


def parse_incoming_message(payload: dict[str, Any]) -> Optional[IncomingMessage]:
    """
    Faz parsing tolerante para payloads comuns de webhook.
    Retorna None quando nao houver mensagem de texto recebida.
    """
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    message = data.get("message") if isinstance(data.get("message"), dict) else data
    whatsapp = message.get("whatsapp") if isinstance(message.get("whatsapp"), dict) else {}
    whatsapp_text = whatsapp.get("text") if isinstance(whatsapp.get("text"), dict) else {}
    contact = message.get("contact") if isinstance(message.get("contact"), dict) else {}

    text = (
        whatsapp_text.get("body")
        or message.get("text")
        or message.get("message")
        or message.get("body")
        or message.get("content")
    )
    from_number = (
        whatsapp.get("from")
        or message.get("from")
        or message.get("from_number")
        or message.get("phone")
        or message.get("mobile")
    )
    event_type = payload.get("event") or payload.get("type") or data.get("event")

    if not text or not from_number:
        return None

    return IncomingMessage(
        text=str(text).strip(),
        from_number=str(from_number).strip(),
        channel_id=_to_optional_str(message.get("channelId") or message.get("channel_id")),
        recipient_name=_to_optional_str(contact.get("name") or message.get("name")),
        contact_id=_to_optional_str(message.get("contactId") or message.get("contact_id")),
        conversation_id=_to_optional_str(
            message.get("conversationId") or message.get("conversation_id")
        ),
        message_id=_to_optional_str(
            message.get("messageId")
            or message.get("message_id")
            or message.get("id")
            or whatsapp.get("id")
        ),
        event_type=_to_optional_str(event_type),
    )


class GallaboxClient:
    """Client minimo para envio de mensagem de texto."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        api_base_url: Optional[str] = None,
        timeout_seconds: int = 15,
    ):
        if not api_key or not api_secret:
            raise ValueError("GALLABOX_API_KEY e GALLABOX_API_SECRET sao obrigatorios.")

        self.api_key = api_key
        self.api_secret = api_secret
        self.api_base_url = (api_base_url or os.getenv("GALLABOX_API_BASE_URL") or "").rstrip("/")
        self.timeout_seconds = timeout_seconds

    def send_text_message(
        self,
        to: str,
        text: str,
        *,
        channel_id: Optional[str] = None,
        recipient_name: Optional[str] = None,
        channel_type: str = "whatsapp",
        conversation_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Envia mensagem de texto.
        Endpoint e configuravel via env para manter o esqueleto portavel entre workspaces.
        """
        if not self.api_base_url:
            raise GallaboxError("Defina GALLABOX_API_BASE_URL para enviar mensagens.")

        endpoint_path = os.getenv("GALLABOX_MESSAGES_PATH", "/messages/whatsapp")
        url = f"{self.api_base_url}{endpoint_path}"

        resolved_channel_id = channel_id or os.getenv("GALLABOX_CHANNEL_ID", "")
        if not resolved_channel_id:
            raise GallaboxError("Defina channel_id ou GALLABOX_CHANNEL_ID para enviar mensagens.")

        payload = {
            "channelId": resolved_channel_id,
            "channelType": channel_type,
            "recipient": {
                "name": recipient_name or to,
                "phone": to,
            },
            "whatsapp": {
                "type": "text",
                "text": {
                    "body": text,
                },
            },
        }
        if conversation_id:
            payload["conversationId"] = conversation_id

        body = json.dumps(payload).encode("utf-8")
        req = request.Request(url=url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("apiKey", self.api_key)
        req.add_header("apiSecret", self.api_secret)

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8") or "{}"
                return json.loads(raw)
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")
            raise GallaboxError(f"Falha HTTP ao enviar mensagem: {exc.code} {details}") from exc
        except error.URLError as exc:
            raise GallaboxError(f"Falha de rede ao enviar mensagem: {exc.reason}") from exc
        except json.JSONDecodeError:
            return {"ok": True}

    def resolve_conversation(
        self,
        *,
        conversation_id: Optional[str] = None,
        phone: Optional[str] = None,
        channel_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """
        Marca a conversa como resolvida na Gallabox quando um endpoint for configurado.

        A documentacao publica confirma o conceito de conversas resolvidas,
        mas o path REST pode variar por conta/integracao. Configure:
        - GALLABOX_RESOLVE_CONVERSATION_PATH
        - GALLABOX_RESOLVE_CONVERSATION_METHOD (default: POST)
        - GALLABOX_RESOLVE_CONVERSATION_BODY (JSON opcional com placeholders)

        Placeholders aceitos: {conversation_id}, {phone}, {channel_id}, {account_id}
        """
        endpoint_path = (
            os.getenv("GALLABOX_RESOLVE_CONVERSATION_PATH", "").strip()
            or os.getenv("GALLABOX_CLOSE_CONVERSATION_PATH", "").strip()
        )
        if not endpoint_path:
            return None
        if not self.api_base_url:
            raise GallaboxError("Defina GALLABOX_API_BASE_URL para resolver conversas.")

        values = {
            "conversation_id": str(conversation_id or "").strip(),
            "phone": str(phone or "").strip(),
            "channel_id": str(channel_id or "").strip(),
            "account_id": os.getenv("GALLABOX_ACCOUNT_ID", "").strip(),
        }

        required_placeholders = {
            placeholder
            for placeholder in values
            if f"{{{placeholder}}}" in endpoint_path
        }
        missing = [placeholder for placeholder in required_placeholders if not values[placeholder]]
        if missing:
            raise GallaboxError(
                "Dados ausentes para resolver conversa na Gallabox: "
                + ", ".join(sorted(missing))
            )

        formatted_values = {key: quote(value, safe="") for key, value in values.items()}
        url = f"{self.api_base_url}{endpoint_path.format(**formatted_values)}"
        method = os.getenv("GALLABOX_RESOLVE_CONVERSATION_METHOD", "POST").strip().upper() or "POST"
        body_template = os.getenv("GALLABOX_RESOLVE_CONVERSATION_BODY", "").strip()
        if body_template:
            body_text = body_template.format(**values)
        else:
            body_text = json.dumps(
                {
                    "status": "RESOLVED",
                    "conversationId": values["conversation_id"],
                    "phone": values["phone"],
                    "channelId": values["channel_id"],
                }
            )

        body = body_text.encode("utf-8")
        req = request.Request(url=url, data=body, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("apiKey", self.api_key)
        req.add_header("apiSecret", self.api_secret)

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8") or "{}"
                return json.loads(raw)
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")
            raise GallaboxError(f"Falha HTTP ao encerrar conversa: {exc.code} {details}") from exc
        except error.URLError as exc:
            raise GallaboxError(f"Falha de rede ao encerrar conversa: {exc.reason}") from exc
        except json.JSONDecodeError:
            return {"ok": True}

    def close_conversation(self, conversation_id: str) -> Optional[dict[str, Any]]:
        return self.resolve_conversation(conversation_id=conversation_id)


def _to_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None
