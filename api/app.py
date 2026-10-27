"""API FastAPI del router de ecommerce.

Levantar en local:
    uvicorn api.app:app --reload --port 8000

Swagger completo en http://localhost:8000/docs
"""

import asyncio
import hmac
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
import httpx
from fastapi import Body, FastAPI, HTTPException, Request, status
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.router.graph import graph

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("api.heroku")

MODELO = os.getenv("MODELO", "gemini-3.5-flash-lite")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_SECRET = os.getenv("TELEGRAM_SECRET", "")

RUTAS_VALIDAS = ("preventa", "postventa", "generica")


class ChatRequest(BaseModel):
    """Body de entrada de /chat."""

    user_id: str = Field(
        ...,
        description="Identificador del usuario. Se usa como `thread_id` para que el router recuerde la conversación.",
        examples=["user-42"],
    )
    texto: str = Field(
        ...,
        min_length=1,
        description="Mensaje del cliente que se debe clasificar y enrutar.",
        examples=["¿tienen la polera azul en talla M?"],
    )


class ChatResponse(BaseModel):
    """Body de salida de /chat."""

    ruta: Literal["preventa", "postventa", "generica"] = Field(
        ...,
        description="Agente destino: preventa (antes de comprar), postventa (pedido ya realizado) o generica (no es del ecommerce).",
        examples=["preventa"],
    )
    motivo: str = Field(
        ...,
        description="Una frase que explica por qué se eligió esa ruta.",
        examples=["El cliente pregunta por la disponibilidad y talla de un producto antes de comprar."],
    )
    respuesta: str = Field(
        ...,
        description="Texto final que devuelve el agente destino al cliente.",
        examples=["Soy el agente de preventa. Recibí: ¿tienen la polera azul en talla M?. Pronto podré ayudarte con productos y compras."],
    )


class HealthResponse(BaseModel):
    """Body de salida de /health."""

    ok: bool = Field(..., description="True si la API está viva.", examples=[True])
    modelo: str = Field(..., description="Modelo de Google GenAI que usa el router.", examples=["gemini-3.5-flash-lite"])


class DetalleValidacion(BaseModel):
    """Un error de campo de la validación de pydantic."""

    loc: list[str] = Field(..., description="Ubicación del campo que falló.", examples=[["body", "texto"]])
    msg: str = Field(..., description="Descripción del error.", examples=["Field required"])
    type: str = Field(..., description="Tipo de error de validación.", examples=["missing"])


class ErrorValidacion(BaseModel):
    """Body de la respuesta 422."""

    detail: list[DetalleValidacion] = Field(..., description="Lista de errores de validación del body.")


class ErrorModelo(BaseModel):
    """Body de la respuesta 502."""

    detail: str = Field(
        ...,
        description="Mensaje claro para el cliente. Nunca incluye credenciales ni stack trace.",
        examples=["El modelo no respondió correctamente. Inténtalo de nuevo en unos segundos."],
    )


class TelegramResponse(BaseModel):
    """Body de salida de /telegram."""

    ok: bool = Field(..., description="True si el webhook se recibió.", examples=[True])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """El grafo se compila una sola vez al importar el módulo (arranque de la app)."""
    logger.info("Router listo. modelo=%s rutas=%s", MODELO, ", ".join(RUTAS_VALIDAS))
    yield
    logger.info("API apagada.")


app = FastAPI(
    title="Ecommerce Router API",
    version="1.0.0",
    summary="Clasifica mensajes de clientes de ecommerce y los enruta a preventa, postventa o genérica.",
    description=(
        "Router de un chat de ecommerce construido con LangGraph.\n\n"
        "Recibe el mensaje de un cliente, decide a qué agente pertenece y devuelve la respuesta del agente destino.\n\n"
        "Las tres rutas posibles son:\n"
        "- **preventa**: intención de compra, preguntas por productos, precios, tallas, stock, promociones y formas de pago **antes** de comprar.\n"
        "- **postventa**: quejas, reclamos, seguimiento de un pedido **ya realizado**, devoluciones, cambios, garantía o productos dañados.\n"
        "- **generica**: saludos o cualquier mensaje ajeno al ecommerce (clima, chistes, preguntas generales).\n\n"
        "Si el modelo duda entre preventa y postventa, la clave es si el cliente **ya compró**.\n\n"
        "La memoria de la conversación se guarda por `user_id` (usado como `thread_id`)."
    ),
    lifespan=lifespan,
    openapi_tags=[
        {"name": "salud", "description": "Estado del servicio."},
        {"name": "chat", "description": "Ruteo de mensajes de clientes del ecommerce."},
        {"name": "telegram", "description": "Webhook entrante de Telegram."},
    ],
)


@app.get(
    "/health",
    tags=["salud"],
    response_model=HealthResponse,
    summary="Estado del servicio",
    description="Devuelve si la API está viva y qué modelo de Google GenAI está usando el router.",
    responses={200: {"description": "La API está viva.", "model": HealthResponse}},
)
def health() -> HealthResponse:
    return HealthResponse(ok=True, modelo=MODELO)


def ejecutar_router(texto: str, thread_id: str) -> ChatResponse:
    resultado = graph.invoke(
        {"mensaje": texto},
        config={"configurable": {"thread_id": thread_id}},
    )
    if not isinstance(resultado, dict):
        raise ValueError(f"El grafo devolvió un resultado inesperado: {type(resultado)!r}")

    ruta = resultado.get("ruta")
    if ruta not in RUTAS_VALIDAS:
        raise ValueError(f"El grafo devolvió una ruta inválida: {ruta!r}")

    return ChatResponse(
        ruta=ruta,
        motivo=str(resultado.get("motivo", "")),
        respuesta=str(resultado.get("respuesta", "")),
    )


@app.post(
    "/chat",
    tags=["chat"],
    response_model=ChatResponse,
    summary="Rutea un mensaje de cliente",
    description=(
        "Clasifica el mensaje con el modelo y lo envía al agente destino.\n\n"
        "La conversación se recuerda por `user_id`, que se usa como `thread_id`."
    ),
    responses={
        200: {"description": "Mensaje clasificado y respondido por el agente destino.", "model": ChatResponse},
        422: {
            "description": "Body inválido: falta `user_id`, falta `texto` o `texto` viene vacío.",
            "model": ErrorValidacion,
        },
        502: {
            "description": "El modelo de Google GenAI falló o devolvió una ruta no válida.",
            "model": ErrorModelo,
        },
    },
)
def chat(pedido: ChatRequest) -> ChatResponse:
    try:
        return ejecutar_router(pedido.texto, pedido.user_id)
    except Exception:
        logger.exception("Fallo el modelo al rutear el mensaje de user_id=%s", pedido.user_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="El modelo no respondió correctamente. Inténtalo de nuevo en unos segundos.",
        ) from None


async def enviar_mensaje_telegram(chat_id: int | str, texto: str) -> None:
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN no está configurado.")

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=15.0) as client:
        respuesta = await client.post(url, json={"chat_id": chat_id, "text": texto})
    respuesta.raise_for_status()

    cuerpo = respuesta.json()
    if not cuerpo.get("ok"):
        raise RuntimeError(f"Telegram rechazó sendMessage: {cuerpo!r}")


@app.post(
    "/telegram",
    tags=["telegram"],
    response_model=TelegramResponse,
    include_in_schema=False,
    summary="Webhook entrante de Telegram",
    description="Recibe updates de Telegram, verifica el secreto y responde usando el router.",
)
async def telegram(request: Request, payload: Any = Body(...)) -> TelegramResponse:
    secreto_recibido = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not TELEGRAM_SECRET or not hmac.compare_digest(secreto_recibido, TELEGRAM_SECRET):
        logger.warning("Webhook de Telegram rechazado por secreto inválido.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Secreto de Telegram inválido.")

    if not isinstance(payload, dict):
        return TelegramResponse(ok=True)

    mensaje = payload.get("message")
    if not isinstance(mensaje, dict):
        return TelegramResponse(ok=True)

    chat = mensaje.get("chat")
    chat_id = chat.get("id") if isinstance(chat, dict) else None
    texto = mensaje.get("text")
    if chat_id is None or not isinstance(texto, str) or not texto.strip():
        return TelegramResponse(ok=True)

    try:
        resultado = await asyncio.to_thread(ejecutar_router, texto, str(chat_id))
        logger.info("Telegram ruteado. chat_id=%s ruta=%s motivo=%s", chat_id, resultado.ruta, resultado.motivo)
        await enviar_mensaje_telegram(chat_id, resultado.respuesta)
    except Exception:
        logger.exception("No se pudo responder el update de Telegram para chat_id=%s", chat_id)

    return TelegramResponse(ok=True)
