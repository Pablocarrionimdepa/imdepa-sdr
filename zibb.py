"""Camada de mensageria da Zibb para WhatsApp."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib import error, request


DEFAULT_GATEWAY_URL = (
    "https://fpkfyqqbeolagvwmlxmd.supabase.co/functions/v1/"
    "chatbot-api-gateway/v2/whatsapp/messages"
)


class ZibbError(Exception):
    """Erro da integração com a Zibb."""


def verify_zibb_signature(raw_body: bytes, signature_header: str, secret: str) -> bool:
    """Valida ``X-Zibb-Signature: sha256=<hex>`` sobre o body bruto."""
    if not secret or not signature_header:
        return False

    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature_header.strip(), expected)


@dataclass(frozen=True)
class ZibbInboundMessage:
    event_id: Optional[str]
    event_type: str
    created_at: Optional[str]
    workspace_id: Optional[str]
    conversation_id: Optional[str]
    message_id: Optional[str]
    from_number: str
    to_number: str
    text: str
    contact: dict[str, Any]


def parse_zibb_inbound(payload: dict[str, Any]) -> Optional[ZibbInboundMessage]:
    """Extrai uma mensagem de texto do evento inbound documentado pela Zibb."""
    event_type = _optional_str(payload.get("type"))
    if event_type != "whatsapp.inbound_message.received":
        return None

    data = payload.get("data")
    if not isinstance(data, dict):
        data = payload.get("whatsappInboundMessage")
    if not isinstance(data, dict):
        return None

    text_data = data.get("text")
    text = text_data.get("body") if isinstance(text_data, dict) else None
    from_number = data.get("from")
    to_number = data.get("to")

    if not text or not from_number or not to_number:
        return None

    contact = data.get("contact") if isinstance(data.get("contact"), dict) else {}
    return ZibbInboundMessage(
        event_id=_optional_str(payload.get("id")),
        event_type=event_type,
        created_at=_optional_str(payload.get("created_at") or payload.get("createTime")),
        workspace_id=_optional_str(payload.get("workspace_id") or data.get("workspace_id")),
        conversation_id=_optional_str(data.get("conversation_id") or data.get("conversationId")),
        message_id=_optional_str(
            data.get("message_id") or data.get("messageId") or data.get("id")
        ),
        from_number=str(from_number).strip(),
        to_number=str(to_number).strip(),
        text=str(text).strip(),
        contact=contact,
    )


class ZibbClient:
    """Cliente mínimo do endpoint de mensagens WhatsApp da Zibb."""

    def __init__(
        self,
        api_key: str,
        gateway_url: Optional[str] = None,
        timeout_seconds: int = 15,
    ):
        if not api_key:
            raise ValueError("ZIBB_API_KEY é obrigatória.")
        self.api_key = api_key
        self.gateway_url = gateway_url or DEFAULT_GATEWAY_URL
        self.timeout_seconds = timeout_seconds

    def send_text_message(self, *, from_number: str, to_number: str, text: str) -> dict[str, Any]:
        payload = {
            "from": from_number,
            "to": to_number,
            "type": "text",
            "text": {"body": text},
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(url=self.gateway_url, data=body, method="POST")
        req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("Content-Type", "application/json")

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8") or "{}"
                return json.loads(raw)
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise ZibbError(f"Falha HTTP da Zibb: {exc.code} {details}") from exc
        except error.URLError as exc:
            raise ZibbError(f"Falha de rede ao chamar a Zibb: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise ZibbError("Resposta JSON inválida da Zibb.") from exc


class ZibbIdempotencyStore:
    """Registro SQLite separado para bloquear webhooks repetidos entre reinícios."""

    def __init__(self, db_path: Optional[str] = None):
        default_path = os.getenv("DB_PATH", "leads.db") + ".zibb"
        self.db_path = db_path or os.getenv("ZIBB_IDEMPOTENCY_DB", default_path)
        self._init_lock = threading.Lock()
        self._initialized = False

    def claim(self, key: str) -> bool:
        self._ensure_initialized()
        with sqlite3.connect(self.db_path, timeout=10) as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO zibb_webhook_messages "
                "(deduplication_key) VALUES (?)",
                (key,),
            )
            connection.commit()
            return cursor.rowcount == 1

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            path = Path(self.db_path)
            if path.parent != Path("."):
                path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS zibb_webhook_messages ("
                    "deduplication_key TEXT PRIMARY KEY, "
                    "received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"
                    ")"
                )
                connection.commit()
            self._initialized = True


def zibb_deduplication_key(incoming: ZibbInboundMessage, raw_body: bytes) -> str:
    if incoming.message_id:
        return f"message:{incoming.message_id}"
    if incoming.event_id:
        return f"event:{incoming.event_id}"
    return "body:" + hashlib.sha256(raw_body).hexdigest()


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
