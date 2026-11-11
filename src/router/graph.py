"""Grafo LangGraph del agente router. Solo orquesta: nodos, aristas y estado."""

import logging
import os
from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .prompts import (
    PROMPT_AGENTE_POSTVENTA,
    PROMPT_AGENTE_PREVENTA,
    PROMPT_RESPUESTA_GENERICA,
    PROMPT_ROUTER,
    RESPUESTA_GENERICA_FALLBACK,
    RESPUESTA_PREVENTA_FALLBACK,
)
from .tools import buscar_productos, mejores_ofertas, ver_producto

load_dotenv()

MODELO = os.getenv("MODELO", "gemini-3.5-flash-lite")
logger = logging.getLogger(__name__)
_pool: ConnectionPool | None = None
tipo_memoria = "ram"


class Decision(BaseModel):
    ruta: Literal["preventa", "postventa", "generica"] = Field(description="A qué agente va el mensaje.")
    motivo: str = Field(description="Una frase: por qué esa ruta.")


def _mergear_saltos(acumulado: list[str], nuevo: list[str]) -> list[str]:
    """Acumula los nodos visitados; 'router' reinicia la cuenta en cada turno."""
    if not nuevo:
        return acumulado
    if nuevo[0] == "router":
        return list(nuevo)
    return acumulado + nuevo


class EstadoRouter(TypedDict, total=False):
    mensaje: str
    ruta: str
    motivo: str
    respuesta: str
    messages: Annotated[list[AnyMessage], lambda acc, upd: acc + upd]
    saltos: Annotated[list[str], _mergear_saltos]


def obtener_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(model=MODELO)


def obtener_contexto_tienda() -> str:
    return (Path(__file__).resolve().parents[2] / "data" / "tienda.md").read_text(encoding="utf-8")


def historial_para_agente(estado: EstadoRouter) -> list[AnyMessage]:
    """Quita el motivo interno del router para que el modelo termine en mensaje humano."""
    historial = list(estado.get("messages", []))
    if historial and isinstance(historial[-1], AIMessage) and historial[-1].content == estado.get("motivo"):
        historial.pop()
    return historial


def nodo_router(estado: EstadoRouter) -> dict[str, Any]:
    llm = ChatGoogleGenerativeAI(model=MODELO)
    chain = llm.with_structured_output(Decision)

    historial = list(estado.get("messages", []))[-4:]
    mensaje_actual = HumanMessage(content=estado.get("mensaje", ""))
    historial.append(mensaje_actual)

    prompt = ChatPromptTemplate.from_messages(
        [("system", PROMPT_ROUTER), MessagesPlaceholder(variable_name="historial")]
    )
    decision: Decision = chain.invoke(
        prompt.invoke({"historial": historial, "ruta_anterior": estado.get("ruta", "sin ruta previa")})
    )

    return {
        "ruta": decision.ruta,
        "motivo": decision.motivo,
        "messages": [mensaje_actual, AIMessage(content=decision.motivo)],
        "saltos": ["router"],
    }


def nodo_agente_preventa(estado: EstadoRouter) -> dict[str, Any]:
    mensaje_actual = HumanMessage(content=estado.get("mensaje", ""))
    agente = create_agent(
        model=obtener_llm(),
        tools=[buscar_productos, ver_producto, mejores_ofertas],
        system_prompt=PROMPT_AGENTE_PREVENTA,
    )
    resultado = agente.invoke({"messages": historial_para_agente(estado)})
    mensajes = resultado.get("messages", [])
    respuesta = str(mensajes[-1].content) if mensajes else RESPUESTA_PREVENTA_FALLBACK
    nombres_herramientas = {"buscar_productos", "ver_producto", "mejores_ofertas"}
    herramientas_usadas = [mensaje.name for mensaje in mensajes if getattr(mensaje, "name", None) in nombres_herramientas]
    return {
        "respuesta": respuesta,
        "messages": [mensaje_actual, AIMessage(content=respuesta)],
        "saltos": ["agente_preventa", *herramientas_usadas],
    }


def nodo_agente_postventa(estado: EstadoRouter) -> dict[str, Any]:
    mensaje_actual = HumanMessage(content=estado.get("mensaje", ""))
    respuesta = (
        f"Soy el agente de postventa. Recibí: {estado.get('mensaje', '')}. "
        "Pronto podré ayudarte con tu pedido."
    )
    return {
        "respuesta": respuesta,
        "messages": [mensaje_actual, AIMessage(content=respuesta)],
        "saltos": ["agente_postventa"],
    }


def nodo_respuesta_generica(estado: EstadoRouter) -> dict[str, Any]:
    mensaje_actual = HumanMessage(content=estado.get("mensaje", ""))
    prompt = ChatPromptTemplate.from_messages(
        [("system", PROMPT_RESPUESTA_GENERICA), MessagesPlaceholder(variable_name="historial")]
    )
    try:
        respuesta = str(
            obtener_llm()
            .invoke(
                prompt.invoke(
                    {"contexto_tienda": obtener_contexto_tienda(), "historial": historial_para_agente(estado)}
                )
            )
            .content
        )
    except Exception:
        logger.warning("El modelo falló al responder la ruta genérica; se usará la respuesta de respaldo.")
        respuesta = RESPUESTA_GENERICA_FALLBACK
    return {
        "respuesta": respuesta,
        "messages": [mensaje_actual, AIMessage(content=respuesta)],
        "saltos": ["respuesta_generica"],
    }


def enrutar(estado: EstadoRouter) -> str:
    return estado.get("ruta", "generica")


def construir_graph(checkpointer: Any | None = None):
    builder = StateGraph(EstadoRouter)

    builder.add_node("router", nodo_router)
    builder.add_node("agente_preventa", nodo_agente_preventa)
    builder.add_node("agente_postventa", nodo_agente_postventa)
    builder.add_node("respuesta_generica", nodo_respuesta_generica)

    builder.add_edge(START, "router")
    builder.add_conditional_edges(
        "router",
        enrutar,
        {
            "preventa": "agente_preventa",
            "postventa": "agente_postventa",
            "generica": "respuesta_generica",
        },
    )
    builder.add_edge("agente_preventa", END)
    builder.add_edge("agente_postventa", END)
    builder.add_edge("respuesta_generica", END)

    return builder.compile(checkpointer=checkpointer or MemorySaver())


def iniciar_memoria() -> str:
    """Configura Postgres si está disponible; de lo contrario usa memoria RAM."""
    global _pool, graph, tipo_memoria

    if _pool is not None:
        return tipo_memoria

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        tipo_memoria = "ram"
        graph = construir_graph()
        logger.info("Memoria del router: RAM (DATABASE_URL no está configurada).")
        return tipo_memoria

    pool = ConnectionPool(
        conninfo=database_url,
        min_size=1,
        max_size=2,
        open=False,
        check=ConnectionPool.check_connection,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    try:
        pool.open(wait=True, timeout=5)
        pool.check()
        checkpointer = PostgresSaver(pool)
        checkpointer.setup()
    except Exception as error:
        pool.close()
        tipo_memoria = "ram"
        graph = construir_graph()
        logger.warning("Memoria del router: RAM (Postgres no disponible: %s).", type(error).__name__)
        return tipo_memoria

    _pool = pool
    tipo_memoria = "postgres"
    graph = construir_graph(checkpointer)
    logger.info("Memoria del router: Postgres (pool min=1 max=2).")
    return tipo_memoria


def cerrar_memoria() -> None:
    """Cierra el pool de Postgres al terminar el proceso."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


graph = construir_graph()
