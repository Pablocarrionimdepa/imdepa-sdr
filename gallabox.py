"""
Integracao base com Gallabox:
- validacao de assinatura de webhook (HMAC SHA-256)
- envio de mensagens de texto via API
"""

import hashlib
import hmac
import json
import os
import base64
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
    is_outgoing: bool = False
    media_url: Optional[str] = None
    media_id: Optional[str] = None
    media_type: Optional[str] = None
    media_mime_type: Optional[str] = None
    media_filename: Optional[str] = None

    @property
    def has_audio(self) -> bool:
        values = (
            self.media_type,
            self.media_mime_type,
            self.media_filename,
            self.media_url,
        )
        return any(_looks_like_audio(value) for value in values if value)


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
    media = _find_media_data(payload) or {}
    has_audio_container = _contains_media_key(payload, ("audio", "voice"))

    text = (
        whatsapp_text.get("body")
        or _nested_text(message, ("button", "text"))
        or _nested_text(message, ("button", "title"))
        or _nested_text(message, ("button", "payload"))
        or _nested_text(message, ("interactive", "button_reply", "title"))
        or _nested_text(message, ("interactive", "button_reply", "id"))
        or _nested_text(whatsapp, ("button", "text"))
        or _nested_text(whatsapp, ("button", "title"))
        or _nested_text(whatsapp, ("button", "payload"))
        or _nested_text(whatsapp, ("interactive", "button_reply", "title"))
        or _nested_text(whatsapp, ("interactive", "button_reply", "id"))
        or message.get("text")
        or message.get("message")
        or message.get("body")
        or message.get("content")
        or _deep_first_text(
            payload,
            (
                "button_text",
                "buttonPayload",
                "button_payload",
                "body",
                "text",
                "content",
            ),
        )
    )
    from_number = (
        whatsapp.get("from")
        or message.get("from")
        or message.get("from_number")
        or message.get("phone")
        or message.get("mobile")
        or contact.get("phone")
        or contact.get("mobile")
        or _deep_first_text(
            payload,
            (
                "from_number",
                "fromNumber",
                "phone",
                "mobile",
                "phoneNumber",
                "whatsappNumber",
                "wa_id",
            ),
        )
    )
    event_type = payload.get("event") or payload.get("type") or data.get("event")
    is_outgoing = _is_outgoing_message(payload)
    media_url = (
        _nested_text(whatsapp, ("audio", "url"))
        or _nested_text(whatsapp, ("media", "url"))
        or _nested_text(whatsapp, ("file", "url"))
        or _nested_text(message, ("audio", "url"))
        or _nested_text(message, ("media", "url"))
        or _nested_text(message, ("file", "url"))
        or _media_text(
            media,
            (
                "url",
                "link",
                "href",
                "mediaUrl",
                "media_url",
                "mediaLink",
                "media_link",
                "downloadUrl",
                "download_url",
                "fileUrl",
                "file_url",
            ),
        )
        or _deep_first_text(
            payload,
            (
                "audioUrl",
                "audio_url",
                "audioLink",
                "audio_link",
                "mediaUrl",
                "media_url",
                "mediaLink",
                "media_link",
                "downloadUrl",
                "download_url",
                "fileUrl",
                "file_url",
                "link",
                "href",
            ),
        )
    )
    media_id = (
        _nested_text(whatsapp, ("audio", "id"))
        or _nested_text(whatsapp, ("media", "id"))
        or _nested_text(message, ("audio", "id"))
        or _nested_text(message, ("media", "id"))
        or _media_text(media, ("id", "mediaId", "media_id", "fileId", "file_id"))
        or _deep_first_text(payload, ("mediaId", "media_id", "fileId", "file_id"))
    )
    media_type = (
        _nested_text(whatsapp, ("audio", "type"))
        or _nested_text(whatsapp, ("media", "type"))
        or _nested_text(message, ("audio", "type"))
        or _nested_text(message, ("media", "type"))
        or _media_text(media, ("type", "mediaType", "media_type", "messageType", "message_type"))
        or _deep_first_text(payload, ("mediaType", "media_type", "messageType", "message_type"))
        or ("audio" if has_audio_container else None)
    )
    media_mime_type = (
        _nested_text(whatsapp, ("audio", "mime_type"))
        or _nested_text(whatsapp, ("audio", "mimeType"))
        or _nested_text(whatsapp, ("media", "mime_type"))
        or _nested_text(whatsapp, ("media", "mimeType"))
        or _nested_text(message, ("audio", "mime_type"))
        or _nested_text(message, ("audio", "mimeType"))
        or _nested_text(message, ("media", "mime_type"))
        or _nested_text(message, ("media", "mimeType"))
        or _media_text(media, ("mimeType", "mime_type", "mimetype", "contentType", "content_type"))
        or _deep_first_text(payload, ("mimeType", "mime_type", "mimetype", "contentType", "content_type"))
    )
    media_filename = (
        _nested_text(whatsapp, ("audio", "filename"))
        or _nested_text(whatsapp, ("media", "filename"))
        or _nested_text(message, ("audio", "filename"))
        or _nested_text(message, ("media", "filename"))
        or _media_text(media, ("filename", "fileName", "file_name", "name"))
        or _deep_first_text(payload, ("fileName", "file_name", "filename"))
    )

    if not from_number or (not text and not media_url and not media_id):
        return None

    return IncomingMessage(
        text=str(text or "").strip(),
        from_number=str(from_number).strip(),
        channel_id=_to_optional_str(
            message.get("channelId")
            or message.get("channel_id")
            or _deep_first_text(payload, ("channelId", "channel_id"))
        ),
        recipient_name=_to_optional_str(contact.get("name") or message.get("name") or _deep_first_text(payload, ("name",))),
        contact_id=_to_optional_str(
            message.get("contactId")
            or message.get("contact_id")
            or _deep_first_text(payload, ("contactId", "contact_id"))
        ),
        conversation_id=_to_optional_str(
            message.get("conversationId")
            or message.get("conversation_id")
            or _deep_first_text(payload, ("conversationId", "conversation_id"))
        ),
        message_id=_to_optional_str(
            message.get("messageId")
            or message.get("message_id")
            or message.get("id")
            or whatsapp.get("id")
            or _deep_first_text(payload, ("messageId", "message_id"))
        ),
        event_type=_to_optional_str(event_type),
        is_outgoing=is_outgoing,
        media_url=_to_optional_str(media_url),
        media_id=_to_optional_str(media_id),
        media_type=_to_optional_str(media_type),
        media_mime_type=_to_optional_str(media_mime_type),
        media_filename=_to_optional_str(media_filename),
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

    def download_media(
        self,
        *,
        media_url: Optional[str] = None,
        media_id: Optional[str] = None,
    ) -> tuple[bytes, Optional[str]]:
        if not media_url and not media_id:
            raise GallaboxError("URL ou ID da midia e obrigatorio para baixar audio.")

        errors: list[str] = []
        for url in self._media_download_urls(media_url=media_url, media_id=media_id):
            try:
                return self._download_media_url(url)
            except GallaboxError as exc:
                errors.append(str(exc))

        raise GallaboxError("Nao foi possivel baixar midia. Tentativas: " + " | ".join(errors))

    def _media_download_urls(
        self,
        *,
        media_url: Optional[str],
        media_id: Optional[str],
    ) -> list[str]:
        urls: list[str] = []
        if media_url:
            urls.append(self._absolute_media_url(media_url))

        if media_id:
            path_config = (
                os.getenv("GALLABOX_MEDIA_DOWNLOAD_PATHS", "").strip()
                or os.getenv("GALLABOX_MEDIA_DOWNLOAD_PATH", "").strip()
            )
            paths = [path.strip() for path in path_config.split("|") if path.strip()]
            if not paths:
                paths = [
                    "https://server.gallabox.com/media/{media_id}",
                    "https://server.gallabox.com/messages/media/{media_id}",
                    "https://server.gallabox.com/whatsapp/media/{media_id}",
                    "/media/{media_id}",
                    "/messages/media/{media_id}",
                    "/whatsapp/media/{media_id}",
                ]
            for path in paths:
                if not self.api_base_url:
                    continue
                formatted = path.format(media_id=quote(str(media_id or ""), safe=""))
                urls.append(self._absolute_media_url(formatted))

        return list(dict.fromkeys(urls))

    def _absolute_media_url(self, url_or_path: str) -> str:
        value = str(url_or_path or "").strip()
        if value.startswith("http://") or value.startswith("https://"):
            return value
        if not self.api_base_url:
            raise GallaboxError("Defina GALLABOX_API_BASE_URL para baixar midia relativa.")
        if not value.startswith("/"):
            value = "/" + value
        return f"{self.api_base_url}{value}"

    def _download_media_url(self, url: str) -> tuple[bytes, Optional[str]]:
        req = request.Request(url=url, method="GET")
        req.add_header("apiKey", self.api_key)
        req.add_header("apiSecret", self.api_secret)

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read()
                content_type = resp.headers.get("Content-Type")
                return self._media_bytes_from_response(raw, content_type)
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")
            raise GallaboxError(f"{url}: HTTP {exc.code} {details}") from exc
        except error.URLError as exc:
            raise GallaboxError(f"{url}: rede {exc.reason}") from exc

    def _media_bytes_from_response(
        self,
        raw: bytes,
        content_type: Optional[str],
    ) -> tuple[bytes, Optional[str]]:
        if not raw:
            raise GallaboxError("Resposta de midia vazia.")

        if content_type and "json" not in content_type.lower():
            return raw, content_type

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return raw, content_type

        nested_url = _deep_first_text(
            payload,
            (
                "url",
                "link",
                "href",
                "mediaUrl",
                "media_url",
                "downloadUrl",
                "download_url",
                "fileUrl",
                "file_url",
            ),
        )
        if nested_url:
            return self._download_media_url(self._absolute_media_url(nested_url))

        encoded = _deep_first_text(payload, ("base64", "data", "content", "file"))
        if encoded:
            if "," in encoded and encoded.strip().lower().startswith("data:"):
                encoded = encoded.split(",", 1)[1]
            try:
                return base64.b64decode(encoded), content_type
            except Exception as exc:
                raise GallaboxError("JSON de midia trouxe base64 invalido.") from exc

        raise GallaboxError("Resposta JSON de midia nao trouxe URL nem conteudo de audio.")


def _to_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _nested_text(value: Any, path: tuple[str, ...]) -> Optional[str]:
    current = value
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    if isinstance(current, (str, int, float)) and str(current).strip():
        return str(current).strip()
    return None


def _find_media_data(value: Any) -> Optional[dict[str, Any]]:
    if isinstance(value, dict):
        for key in ("audio", "media", "attachment", "file", "document", "voice"):
            candidate = value.get(key)
            if isinstance(candidate, dict):
                return candidate
            if isinstance(candidate, list) and candidate and isinstance(candidate[0], dict):
                return candidate[0]

        attachments = value.get("attachments")
        if isinstance(attachments, list) and attachments and isinstance(attachments[0], dict):
            return attachments[0]

        for child in value.values():
            nested = _find_media_data(child)
            if nested:
                return nested

    if isinstance(value, list):
        for item in value:
            nested = _find_media_data(item)
            if nested:
                return nested

    return None


def _contains_media_key(value: Any, keys: tuple[str, ...]) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in keys and isinstance(child, (dict, list, str)):
                return True
            if _contains_media_key(child, keys):
                return True

    if isinstance(value, list):
        return any(_contains_media_key(item, keys) for item in value)

    return False


def _media_text(media: dict[str, Any], keys: tuple[str, ...]) -> Optional[str]:
    if not isinstance(media, dict):
        return None
    for key in keys:
        candidate = media.get(key)
        if isinstance(candidate, (str, int, float)) and str(candidate).strip():
            return str(candidate).strip()
    return None


def _looks_like_audio(value: Any) -> bool:
    normalized = str(value or "").strip().lower()
    return any(marker in normalized for marker in ("audio", "voice", "ogg", "opus", "mpeg", "mp3", "m4a", "wav"))


def _is_outgoing_message(payload: dict[str, Any]) -> bool:
    outgoing_values = {
        "outgoing",
        "sent",
        "delivered",
        "read",
        "failed",
        "template_sent",
    }
    for key in ("direction", "messageDirection", "status", "messageStatus"):
        value = _deep_first_text(payload, (key,))
        if value and value.strip().lower() in outgoing_values:
            return True

    for key in ("fromMe", "from_me", "isFromMe", "outgoing"):
        value = _deep_first_value(payload, key)
        if isinstance(value, bool) and value:
            return True
        if isinstance(value, str) and value.strip().lower() in {"true", "1", "yes"}:
            return True

    return False


def _deep_first_text(value: Any, keys: tuple[str, ...]) -> Optional[str]:
    if isinstance(value, dict):
        for key in keys:
            candidate = value.get(key)
            if isinstance(candidate, (str, int, float)) and str(candidate).strip():
                return str(candidate).strip()
            if isinstance(candidate, dict):
                nested = _deep_first_text(candidate, keys)
                if nested:
                    return nested

        for child in value.values():
            nested = _deep_first_text(child, keys)
            if nested:
                return nested

    if isinstance(value, list):
        for item in value:
            nested = _deep_first_text(item, keys)
            if nested:
                return nested

    return None


def _deep_first_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for child in value.values():
            nested = _deep_first_value(child, key)
            if nested is not None:
                return nested

    if isinstance(value, list):
        for item in value:
            nested = _deep_first_value(item, key)
            if nested is not None:
                return nested

    return None
