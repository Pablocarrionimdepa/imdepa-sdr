"""Teste manual de envio pela Zibb (sem webhook).

Uso:
    python zibb_send_test.py <numero_da_conta_zibb> <seu_celular> ["texto"]

Exemplo:
    python zibb_send_test.py 5551988887777 5551999990000 "Teste Fernanda"

Lê ZIBB_API_KEY e ZIBB_GATEWAY_URL do .env.
"""

import json
import os
import sys

from dotenv import load_dotenv

from zibb import DEFAULT_GATEWAY_URL, ZibbClient, ZibbError

load_dotenv()


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2

    from_number, to_number = sys.argv[1], sys.argv[2]
    text = sys.argv[3] if len(sys.argv) > 3 else "Teste de envio da Fernanda via Zibb."

    client = ZibbClient(
        api_key=os.getenv("ZIBB_API_KEY", ""),
        gateway_url=os.getenv("ZIBB_GATEWAY_URL", DEFAULT_GATEWAY_URL),
    )
    try:
        result = client.send_text_message(from_number=from_number, to_number=to_number, text=text)
    except ZibbError as exc:
        print(f"ERRO: {exc}")
        return 1

    print("OK:", json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
