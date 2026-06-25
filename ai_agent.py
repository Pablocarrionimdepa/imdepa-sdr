"""
Modulo de integracao com a API OpenAI para o agente SDR Fernanda.
"""

import json
import os
import tempfile

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
TRANSCRIPTION_MODEL = os.getenv("OPENAI_TRANSCRIPTION_MODEL", "whisper-1")


def _get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY nao configurada.")
    return OpenAI(api_key=api_key)


def transcribe_audio_bytes(
    audio_bytes: bytes,
    *,
    filename: str = "audio.ogg",
    content_type: str = "",
) -> str:
    """Transcreve audio recebido pela Gallabox para texto em portugues."""
    if not audio_bytes:
        return ""

    suffix = _audio_suffix(filename=filename, content_type=content_type)
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(audio_bytes)
            temp_path = temp_file.name

        with open(temp_path, "rb") as audio_file:
            response = _get_client().audio.transcriptions.create(
                model=TRANSCRIPTION_MODEL,
                file=audio_file,
                language="pt",
            )
        return str(getattr(response, "text", "") or "").strip()
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def _audio_suffix(*, filename: str = "", content_type: str = "") -> str:
    filename = str(filename or "").lower()
    content_type = str(content_type or "").lower()
    suffixes = {
        "ogg": ".ogg",
        "opus": ".ogg",
        "mpeg": ".mp3",
        "mp3": ".mp3",
        "mp4": ".m4a",
        "m4a": ".m4a",
        "wav": ".wav",
        "webm": ".webm",
    }
    for marker, suffix in suffixes.items():
        if marker in content_type or filename.endswith(suffix):
            return suffix
    return ".ogg"


def get_ai_response(messages: list) -> str:
    """Envia o historico de conversa para a API OpenAI e retorna a resposta."""
    try:
        response = _get_client().chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=220,
            top_p=0.9,
            frequency_penalty=0.3,
            presence_penalty=0.3,
        )
        return response.choices[0].message.content
    except Exception as exc:
        print(f"Erro na API OpenAI: {exc}")
        raise


EXTRACTION_PROMPT = """Analise o historico de conversa abaixo entre a assistente Fernanda (Imdepa) e um potencial cliente.
Extraia APENAS as informacoes que foram EXPLICITAMENTE mencionadas pelo cliente na conversa.
NAO invente ou suponha informacoes que nao foram ditas.

Retorne um JSON com os seguintes campos (deixe string vazia \"\" se a informacao nao foi mencionada):

{
    "empresa": "Nome da empresa do cliente",
    "contato": "Nome da pessoa de contato",
    "cnpj": "CNPJ da empresa",
    "email": "E-mail informado para contato",
    "telefone": "Telefone informado para contato",
    "segmento": "Agricola, Industrial, Automotivo ou Outro. Use Outro quando o segmento mencionado nao for um desses tres.",
    "produtos_interesse": "Produtos que o cliente demonstrou interesse",
    "volume_compra": "Volume estimado de compras mensal",
    "fornecedor_atual": "Fornecedor(es) atual(is) mencionado(s)",
    "dores_necessidades": "Problemas, dores ou necessidades mencionadas",
    "decisores": "Pessoa(s) que decide(m) sobre compras",
    "proximo_passo": "Proximo passo definido na conversa (agendamento, envio de material, etc.)"
}

Preencha email e telefone em campos separados. Se apenas um deles tiver sido informado, deixe o outro como string vazia.

IMPORTANTE: Retorne APENAS o JSON, sem markdown, sem explicacoes, sem texto adicional."""


def extract_lead_info(messages: list) -> dict:
    """Extrai informacoes do lead a partir do historico de conversa."""
    conversation_text = ""
    for msg in messages:
        if msg["role"] == "user":
            conversation_text += f"Cliente: {msg['content']}\n"
        elif msg["role"] == "assistant":
            conversation_text += f"Fernanda: {msg['content']}\n"

    user_messages = [m for m in messages if m["role"] == "user"]
    if not user_messages:
        return {}

    try:
        response = _get_client().chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {"role": "user", "content": conversation_text},
            ],
            temperature=0.1,
            max_tokens=500,
        )

        result_text = response.choices[0].message.content.strip()

        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[1] if "\n" in result_text else result_text[3:]
        if result_text.endswith("```"):
            result_text = result_text[:-3]
        result_text = result_text.strip()

        return json.loads(result_text)
    except (json.JSONDecodeError, Exception) as exc:
        print(f"Erro ao extrair informacoes do lead: {exc}")
        return {}


SUMMARY_PROMPT = """Analise o historico completo de qualificacao SDR entre a Fernanda (Imdepa) e o lead.
Gere um resumo consolidado para a equipe comercial, usando apenas informacoes explicitamente presentes na conversa ou nos dados extraidos.

Adapte o resumo ao roteiro atual da Imdepa. Inclua:
- Nome da empresa, se identificado
- CNPJ, se informado
- Nome do contato
- E-mail e telefone de contato
- Segmento da empresa
- Produtos de interesse, se mencionados
- Principais dores ou necessidades, se mencionadas
- Decisores, se mencionados
- Interesse demonstrado
- Classificacao do lead
- Observacoes relevantes e proximo passo sugerido

Classifique o lead como:
- Qualificado: informou CNPJ, nome, e-mail, telefone e segmento
- Parcial: demonstrou interesse, mas faltam dados obrigatorios
- Baixa prioridade: sem aderencia clara ou sem interesse

Retorne em portugues brasileiro, em formato objetivo para leitura comercial. Nao invente informacoes."""


def generate_qualification_summary(messages: list, lead_info: dict) -> str:
    """Gera um resumo comercial final da qualificacao."""
    conversation_text = ""
    for msg in messages:
        if msg["role"] == "user":
            conversation_text += f"Cliente: {msg['content']}\n"
        elif msg["role"] == "assistant":
            conversation_text += f"Fernanda: {msg['content']}\n"

    payload = {
        "lead_info": lead_info or {},
        "conversation": conversation_text,
    }

    try:
        response = _get_client().chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SUMMARY_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.2,
            max_tokens=700,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        print(f"Erro ao gerar resumo da qualificacao: {exc}")
        return _build_fallback_summary(lead_info)


def _build_fallback_summary(lead_info: dict) -> str:
    lead_info = lead_info or {}
    fields = [
        ("Empresa", lead_info.get("empresa")),
        ("CNPJ", lead_info.get("cnpj")),
        ("Contato", lead_info.get("contato")),
        ("E-mail", lead_info.get("email")),
        ("Telefone", lead_info.get("telefone")),
        ("Segmento", lead_info.get("segmento")),
        ("Produtos de interesse", lead_info.get("produtos_interesse")),
        ("Dores/necessidades", lead_info.get("dores_necessidades")),
        ("Decisores", lead_info.get("decisores")),
        ("Proximo passo", lead_info.get("proximo_passo")),
    ]
    lines = [f"{label}: {value}" for label, value in fields if str(value or "").strip()]
    if not lines:
        return "Resumo indisponivel: nao foram extraidas informacoes suficientes da conversa."
    return "\n".join(lines)
