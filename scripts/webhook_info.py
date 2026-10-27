"""Muestra la configuración y los errores pendientes del webhook de Telegram."""

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def main() -> None:
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    if not token:
        raise SystemExit("Falta configurar TELEGRAM_TOKEN en .env o en las variables de entorno.")

    respuesta = httpx.get(f"https://api.telegram.org/bot{token}/getWebhookInfo", timeout=15.0)
    respuesta.raise_for_status()
    print(json.dumps(respuesta.json(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPError as error:
        print(f"No se pudo consultar el webhook: {error}", file=sys.stderr)
        sys.exit(1)
