"""Consulta de CNPJ via BrasilAPI."""

import json
import os
import re
from typing import Optional
from urllib import error, request

BRASILAPI_BASE_URL = os.getenv("BRASILAPI_BASE_URL", "https://brasilapi.com.br/api")
CNPJ_PATTERN = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")


def extract_cnpj(text: str) -> Optional[str]:
    if not text:
        return None

    match = CNPJ_PATTERN.search(text)
    if match:
        digits = only_digits(match.group(0))
        return digits if len(digits) == 14 else None

    digits = only_digits(text)
    return digits if len(digits) == 14 else None


def lookup_cnpj(text: str) -> Optional[dict]:
    cnpj = extract_cnpj(text)
    if not cnpj:
        return None

    url = f"{BRASILAPI_BASE_URL.rstrip('/')}/cnpj/v1/{cnpj}"
    req = request.Request(url=url, method="GET")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "ImdepaSDR/1.0 (+https://imdepa.com.br)")

    try:
        with request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        if exc.code == 404:
            return {
                "cnpj": cnpj,
                "formatted_cnpj": format_cnpj(cnpj),
                "empresa": "",
                "found": False,
            }
        raise
    except error.URLError:
        return {
            "cnpj": cnpj,
            "formatted_cnpj": format_cnpj(cnpj),
            "empresa": "",
            "found": False,
        }

    empresa = str(payload.get("razao_social") or payload.get("nome_fantasia") or "").strip()
    return {
        "cnpj": cnpj,
        "formatted_cnpj": format_cnpj(cnpj),
        "empresa": empresa,
        "found": bool(empresa),
        "payload": payload,
    }


def only_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def format_cnpj(cnpj: str) -> str:
    digits = only_digits(cnpj)
    if len(digits) != 14:
        return digits
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"

