"""
Modulo de integracao com a API OpenAI para o agente SDR Fernanda.
"""

import json
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


def _get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY nao configurada.")
    return OpenAI(api_key=api_key)


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
    "segmento": "Agricola, Industrial, Automotivo, Revenda ou outro",
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
