"""Registra el webhook de Telegram usando PUBLIC_URL y TELEGRAM_SECRET."""

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def variable_requerida(nombre: str) -> str:
    valor = os.getenv(nombre, "").strip()
    if not valor:
        raise SystemExit(f"Falta configurar {nombre} en .env o en las variables de entorno.")
    return valor


def main() -> None:
    token = variable_requerida("TELEGRAM_TOKEN")
    secreto = variable_requerida("TELEGRAM_SECRET")
    public_url = variable_requerida("PUBLIC_URL").rstrip("/")

    respuesta = httpx.post(
        f"https://api.telegram.org/bot{token}/setWebhook",
        json={"url": f"{public_url}/telegram", "secret_token": secreto},
        timeout=15.0,
    )
    respuesta.raise_for_status()
    print(json.dumps(respuesta.json(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPError as error:
        print(f"No se pudo registrar el webhook: {error}", file=sys.stderr)
        sys.exit(1)
